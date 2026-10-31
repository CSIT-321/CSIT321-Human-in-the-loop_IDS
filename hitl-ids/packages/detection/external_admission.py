"""Explicit eligibility decisions and atomic admission of immutable Suricata evidence."""
import hashlib
import json
import sqlite3
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import Field, field_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.adapters.admission_policy import AdmissionPolicy
from packages.detection.adapters.operational_v2 import project_external, materialize_source, read_triage
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput
from packages.detection.routing import RoutingRequest, route_alert, state_version
from packages.detection.triage_policy import TriageContext, evaluate_triage
from packages.detection.triage_policy_service import apply_triage_policy


class AdmissionConflict(ValueError):
    pass


class AdmissionRequest(V2Contract):
    request_id: UUID
    expected_review_id: int | None = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('a reason is required')
        return value.strip()


class EligibilityRequest(AdmissionRequest):
    decision: Literal['accepted', 'held']


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _actor(conn, actor_id):
    actor = db.get(conn, m.User, actor_id)
    if actor is None or actor.status != 'active' or actor.role not in ('security_analyst', 'system_admin'):
        raise PermissionError('admission requires an active operational analyst or administrator')


def _source(conn, inbox_id):
    row = conn.execute('SELECT * FROM external_alert_inbox WHERE id=?', (inbox_id,)).fetchone()
    if row is None:
        raise LookupError('external inbox row not found')
    return dict(row)


def _digest(row):
    return hashlib.sha256(_json(row).encode()).hexdigest()


def validate_source(row):
    """Revalidate canonical/raw identity, staging policy snapshot and every restriction."""
    try:
        alert = project_external(row)
        canonical = alert.detector_evidence
        raw = canonical.model_dump(mode='json')['original_detector_fields']
        reference = 'eve-sha256:' + hashlib.sha256(_json(raw).encode()).hexdigest()
        reconstructed = SuricataEveAdapter().adapt(SuricataOutput(
            raw, reference, detector_version=canonical.detector_version, sensor_id=row['sensor_id']))
        if reconstructed != canonical:
            raise ValueError('raw evidence does not match canonical evidence')
        policy = AdmissionPolicy.model_validate_json(row['policy_snapshot'])
        decision = policy.decide(canonical)
        if (row['admission_policy_version'] != decision.policy_version
                or row['proposed_operational_priority'] != decision.initial_operational_priority
                or row['admission_decision'] != 'hold_for_review'):
            raise ValueError('staging policy provenance disagrees')
        # Validate support in the effective operational policy, independently of staging priority.
        evaluate_triage(alert)
        return alert
    except (ValueError, TypeError, KeyError) as exc:
        raise AdmissionConflict('Source evidence or staging policy is invalid; admission is blocked') from exc


def latest_review(conn, inbox_id):
    row = conn.execute('SELECT * FROM external_eligibility_review WHERE external_inbox_id=? '
                       'ORDER BY id DESC LIMIT 1', (inbox_id,)).fetchone()
    return dict(row) if row else None


def admission_record(conn, inbox_id):
    row = conn.execute('SELECT * FROM external_operational_admission WHERE external_inbox_id=?',
                       (inbox_id,)).fetchone()
    return dict(row) if row else None


def review_eligibility(conn, inbox_id, *, actor_id: int, request: EligibilityRequest):
    request = EligibilityRequest.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('eligibility requires no open transaction')
    try:
        conn.execute('BEGIN IMMEDIATE')
        _actor(conn, actor_id)
        source = _source(conn, inbox_id)
        prior = conn.execute('SELECT * FROM external_eligibility_review WHERE request_id=?',
                             (str(request.request_id),)).fetchone()
        if prior is not None:
            expected = dict(external_inbox_id=inbox_id, actor_id=actor_id,
                expected_review_id=request.expected_review_id, decision=request.decision, reason=request.reason)
            if any(prior[k] != v for k, v in expected.items()):
                raise AdmissionConflict('requestId belongs to another eligibility decision')
            conn.commit()
            return dict(prior)
        if admission_record(conn, inbox_id) or conn.execute(
                'SELECT 1 FROM operational_alerts_v2 WHERE external_inbox_id=?', (inbox_id,)).fetchone():
            raise AdmissionConflict('already materialized; eligibility cannot be rewritten')
        previous = latest_review(conn, inbox_id)
        if (previous['id'] if previous else None) != request.expected_review_id:
            raise AdmissionConflict('eligibility review changed; refresh before deciding')
        if request.decision == 'accepted':
            validate_source(source)
        cursor = conn.execute('INSERT INTO external_eligibility_review '
            '(external_inbox_id,actor_id,request_id,expected_review_id,decision,reason,evidence_digest,created_at) '
            'VALUES (?,?,?,?,?,?,?,?)', (inbox_id, actor_id, str(request.request_id), request.expected_review_id,
            request.decision, request.reason, _digest(source), db.format_timestamp(m.utc_now())))
        result = dict(conn.execute('SELECT * FROM external_eligibility_review WHERE id=?', (cursor.lastrowid,)).fetchone())
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def admit_external(conn: sqlite3.Connection, inbox_id: int, *, actor_id: int,
                   request: AdmissionRequest, trusted_context: TriageContext | None = None):
    """One write transaction. HTTP never accepts caller-supplied evidence or policy context."""
    request = AdmissionRequest.model_validate(request.model_dump())
    context = TriageContext.model_validate((trusted_context or TriageContext()).model_dump())
    context_json = _json(context.model_dump(mode='json', by_alias=True))
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('admission requires foreign keys and no open transaction')
    try:
        conn.execute('BEGIN IMMEDIATE')
        _actor(conn, actor_id)
        source = _source(conn, inbox_id)
        prior_key = conn.execute('SELECT * FROM external_operational_admission WHERE request_id=?',
                                 (str(request.request_id),)).fetchone()
        if prior_key is not None and any(prior_key[k] != v for k, v in dict(
                external_inbox_id=inbox_id, actor_id=actor_id, review_id=request.expected_review_id,
                reason=request.reason, context_snapshot=context_json).items()):
            raise AdmissionConflict('requestId belongs to another admission')
        existing = admission_record(conn, inbox_id)
        if existing:
            if existing['context_snapshot'] != context_json or existing['review_id'] != request.expected_review_id:
                raise AdmissionConflict('admission already completed with different review/context')
            conn.commit()
            return existing, True
        review = latest_review(conn, inbox_id)
        if not review or review['decision'] != 'accepted' or review['id'] != request.expected_review_id:
            raise AdmissionConflict('a current explicit accepted eligibility review is required')
        validate_source(source)
        if review['evidence_digest'] != _digest(source):
            raise AdmissionConflict('source changed since eligibility review')
        if conn.execute('SELECT 1 FROM operational_alerts_v2 WHERE external_inbox_id=?', (inbox_id,)).fetchone():
            raise AdmissionConflict('pre-existing projection is outside this admission workflow; manual reconciliation required')
        alert = materialize_source(conn, 'external_nids_alert', inbox_id, _admission_transaction=True)
        policy = apply_triage_policy(conn, alert.id, actor_id=actor_id,
            expected_state=read_triage(conn, alert.id), context=context, _admission_transaction=True)
        routing, replayed = route_alert(conn, alert.id, actor_id=actor_id, action='admit_tier1',
            request=RoutingRequest(request_id=uuid5(NAMESPACE_URL, 'external-admission:' + str(request.request_id)),
                expected_state_version=state_version(policy.state), reason=request.reason),
            _admission_transaction=True)
        if replayed:
            raise AdmissionConflict('unexpected routing identity collision')
        state = read_triage(conn, alert.id)
        cursor = conn.execute('INSERT INTO external_operational_admission '
            '(external_inbox_id,operational_alert_id,canonical_alert_id,actor_id,review_id,request_id,reason,'
            'event_type,policy_audit_id,routing_audit_id,context_snapshot,resulting_state,created_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (inbox_id, alert.id, str(alert.canonical_alert_id), actor_id,
            review['id'], str(request.request_id), request.reason, 'V2_EXTERNAL_ALERT_ADMITTED',
            policy.audit_id, routing.id, context_json, state.model_dump_json(by_alias=True),
            db.format_timestamp(state.updated_at)))
        result = dict(conn.execute('SELECT * FROM external_operational_admission WHERE id=?', (cursor.lastrowid,)).fetchone())
        conn.commit()
        return result, False
    except Exception:
        conn.rollback()
        raise
