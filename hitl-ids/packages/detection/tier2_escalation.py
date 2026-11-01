"""One authenticated command: audited escalation and automatic case, committed together."""
import json
from typing import Literal
from uuid import UUID

from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.routing import RoutingRequest, RoutingConflict, route_alert, state_version
from packages.detection.tier2_cases import (
    CaseConflict, CaseMutation, CreateCaseRequest, create_case, read_case, _actor, _start, _retry,
)


class EscalateCaseRequest(RoutingRequest):
    action: Literal['manual_escalate', 'approve_tier2', 'recover_case'] = 'manual_escalate'


def escalate_case(conn, alert_ref: UUID, *, actor_id: int, request: EscalateCaseRequest) -> CaseMutation:
    request = EscalateCaseRequest.model_validate(request.model_dump())
    # Store the original logical command in the immutable creation event. Retries must not
    # regenerate metadata from a state that may already have advanced into investigation.
    payload = json.dumps(dict(command='escalate-case-v1', alertRef=str(alert_ref),
                              request=request.model_dump(mode='json')), sort_keys=True, allow_nan=False)
    _start(conn)  # BEGIN IMMEDIATE serializes competing writers before checking state/retry identity.
    try:
        _actor(conn, actor_id)
        retry = _retry(conn, actor_id, 'create', payload, request.request_id)
        if retry:
            ref = conn.execute('SELECT case_ref FROM tier2_cases WHERE id=?', (retry['case_id'],)).fetchone()[0]
            result = CaseMutation(case=read_case(conn, ref), event_id=retry['id'], replayed=True)
            conn.commit()
            return result
        if conn.execute('SELECT 1 FROM operational_routing_audit WHERE request_id=?', (str(request.request_id),)).fetchone():
            raise RoutingConflict('requestId already belongs to a different routing command')
        row = conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (str(alert_ref),)).fetchone()
        if row is None:
            raise LookupError('Operational alert not found')
        alert = read_projection(conn, row['id'])
        before = read_triage(conn, alert.id)
        if state_version(before) != request.expected_state_version:
            raise RoutingConflict('V2 state changed; refresh and review before deciding again')
        if request.action == 'recover_case':
            if (before.handling_route, before.workflow_stage) != ('tier2_candidate', 'assessment'):
                raise CaseConflict('only a historical incomplete escalation can be recovered')
        else:
            route_alert(conn, alert.id, actor_id=actor_id, action=request.action,
                        request=RoutingRequest.model_validate(request.model_dump(exclude={'action'})),
                        _case_transaction=True)
        candidate = read_triage(conn, alert.id)
        # Bound each fact independently so the original analyst reason is never truncated.
        # The snapshot also retains the complete, unabridged detector and triage evidence.
        handoff = '\n'.join((
            f'Detector: {alert.detector_name[:200]} / {alert.detector_version or "Not provided"}'[:300],
            f'Detection: {alert.detection_title[:500]}',
            f'Operational priority: {before.priority_band or "Not assigned"} / {before.operational_priority if before.operational_priority is not None else "Not assigned"}',
            f'Review reason: {before.review_reason[:400]}',
            'Tier 2 recommendation: ' + '; '.join(before.tier2_recommendation_reasons)[:400],
            'Analyst escalation reason: ' + request.reason,
        ))
        suffix = ' — Tier 2 Investigation'
        result = create_case(conn, alert_ref, actor_id=actor_id, request=CreateCaseRequest(
            request_id=request.request_id, expected_state_version=state_version(candidate),
            title=alert.detection_title[:200-len(suffix)] + suffix,
            tier1_handoff_summary=handoff,
            reason=('Recover historical escalation: ' if request.action == 'recover_case' else 'Authenticated Tier 2 escalation: ') + request.reason,
        ), _escalation_transaction=True, _command_payload=payload)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
