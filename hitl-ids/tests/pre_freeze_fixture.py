"""Disposable synthetic scenarios using real domain commands; no collection or route SQL."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from packages.contracts import models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.external_admission import review_eligibility, admit_external, EligibilityRequest, AdmissionRequest
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.triage_policy import TriageContext
from packages.detection import triage_memory as memory, selective_review as review
from packages.detection.routing import state_version


def event(flow=1, signature='SSH brute force', category='Attempted Information Leak', severity=3):
    raw = json.loads((Path(__file__).parent/'fixtures/suricata-correlated.json').read_text(encoding='utf-8'))[0]
    raw.update(flow_id=flow)
    raw['alert'].update(signature=signature, category=category, severity=severity)
    return raw


class Events:
    def __init__(self, events): self.events = events
    def read_text(self, **_): return json.dumps(self.events)


def stage(conn, events, scope='review-fixture', sensor='review-sensor'):
    return stage_file(conn, Events(events), sensor, capture_scope=scope)


def admit_all(conn, actor=1):
    alerts = []
    for row in conn.execute('SELECT id FROM external_alert_inbox WHERE id NOT IN (SELECT external_inbox_id FROM external_operational_admission) ORDER BY id').fetchall():
        accepted = review_eligibility(conn, row[0], actor_id=actor, request=EligibilityRequest(
            request_id=uuid4(), expected_review_id=None, decision='accepted', reason='SYNTHETIC evidence acceptance'))
        receipt, _ = admit_external(conn, row[0], actor_id=actor, request=AdmissionRequest(
            request_id=uuid4(), expected_review_id=accepted['id'], reason='SYNTHETIC admission; no Tier 2 approval'))
        alerts.append(read_projection(conn, receipt['operational_alert_id']))
    return alerts


def safe_context():
    return TriageContext(asset_criticality='low', repeated_campaign=False, correlated_alert_count=1,
        response_required=False, known_malicious_indicator=False, analyst_escalated=False,
        unresolved_by_tier1=False, evidence_conflict=False, confirmed_malicious=False)


def review_request(conn, alert, outcome='expected_activity'):
    return memory.MemoryReviewRequest(request_id=uuid4(), reason='SYNTHETIC authorized scanner assessment',
        outcome=outcome, scope='exact', expected_state_version=state_version(read_triage(conn, alert.id)))


def defer(conn, alert, actor=1):
    view = review.read_review(conn, alert.operational_alert_ref)
    return review.decide_review(conn, alert.operational_alert_ref, actor_id=actor, action='apply',
        request=review.ReviewCommand(request_id=uuid4(), expected_version=view.version, reason='SYNTHETIC evaluate current safety evidence')).view


def review_scenario(conn, actor=1, scope='effective-review'):
    # Select deterministic non-sampled identities; the real 10% audit policy is unchanged.
    events, flow = [], 800000
    while len(events) < 6:
        raw = event(flow, 'SYNTHETIC selective SSH scan', severity=1)
        raw['timestamp'] = f'2026-10-{len(events)+1:02d}T03:00:00Z'
        ref = build_bundle([parse_record(raw, 'review-sensor', scope)]).canonical_alert_id
        flow += 1
        if int(sha256(str(ref).encode()).hexdigest()[:8], 16) % 100 < 10: continue
        events.append(raw)
    stage(conn, events, scope)
    alerts = admit_all(conn, actor)
    for alert in alerts: seed_synthetic_facts(conn, alert, safe_context(), m.utc_now())
    for alert in alerts[:3]:
        lesson = contribute_review(conn,alert,actor_id=actor,request=review_request(conn,alert)).memory
    memory.decide_memory(conn, lesson.lesson.lesson_ref, actor_id=actor, action='activate', request=memory.MemoryDecisionRequest(
        request_id=uuid4(), expected_revision=lesson.revision, reason='SYNTHETIC evidence activation'))
    for alert in alerts[3:]: assert defer(conn, alert, actor).disposition == 'no_immediate_review'
    return alerts


def contribute_review(conn,alert,actor_id,request):
    from packages.detection.analyst_verdict import read_verdict,record_verdict,VerdictCommand
    view=read_verdict(conn,alert.operational_alert_ref,actor_id)
    verdict=record_verdict(conn,alert.operational_alert_ref,actor_id=actor_id,request=VerdictCommand(
        request_id=uuid4(),expected_revision=view.revision,expected_state_version=view.source_state_version,
        outcome=request.outcome,reason=request.reason)).verdict
    return memory.contribute_verdict(conn,alert.operational_alert_ref,actor_id=actor_id,request=memory.VerdictMemoryRequest(
        request_id=request.request_id,expected_state_version=request.expected_state_version,verdict_ref=verdict.verdict_ref,scope=request.scope))
