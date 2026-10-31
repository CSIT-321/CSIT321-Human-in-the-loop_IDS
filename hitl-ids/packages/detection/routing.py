"""Authenticated, optimistic V2 routing. Detector and policy records are never written."""
from datetime import timedelta
import hashlib
import json
import sqlite3
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from packages.contracts import db, models as m
from packages.contracts.operational_v2 import OperationalTriageStateV2, V2Contract
from packages.detection.adapters.operational_v2 import read_triage

RoutingAction = Literal['admit_tier1', 'approve_tier2', 'reject_tier2', 'manual_escalate']
EVENTS = {'admit_tier1': 'V2_TIER1_ADMITTED', 'approve_tier2': 'V2_TIER2_APPROVED',
          'reject_tier2': 'V2_TIER2_REJECTED', 'manual_escalate': 'V2_MANUAL_ESCALATION'}


class RoutingRequest(V2Contract):
    request_id: UUID
    expected_state_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('a nonblank decision reason is required')
        return value.strip()


class RoutingAudit(V2Contract):
    id: int
    operational_alert_id: int
    actor_id: int
    request_id: UUID
    action: RoutingAction
    event_type: str
    expected_state_version: str
    reason: str
    before_state: OperationalTriageStateV2
    after_state: OperationalTriageStateV2
    created_at: str


class RoutingConflict(ValueError):
    pass


def state_version(state: OperationalTriageStateV2) -> str:
    return hashlib.sha256(_json(state).encode()).hexdigest()


def _json(model) -> str:
    return json.dumps(model.model_dump(mode='json', by_alias=True), sort_keys=True, allow_nan=False)


def decode_audit(row) -> RoutingAudit:
    values = dict(row)
    for key in ('before_state', 'after_state'):
        values[key] = json.loads(values[key])
    return RoutingAudit.model_validate(values)


def allowed_actions(state: OperationalTriageStateV2) -> tuple[RoutingAction, ...]:
    if (state.handling_route, state.workflow_stage) == ('unassigned', 'staged'):
        return ('admit_tier1',)
    if (state.handling_route, state.workflow_stage) == ('tier1_review', 'triage'):
        return (('approve_tier2', 'reject_tier2', 'manual_escalate') if state.tier2_recommended
                else ('manual_escalate',))
    return ()


def route_alert(conn: sqlite3.Connection, alert_id: int, *, actor_id: int,
                action: RoutingAction, request: RoutingRequest) -> tuple[RoutingAudit, bool]:
    """The HTTP boundary binds actor_id to the verified principal, never request data.

    Retry identity is global and actor/payload-bound. Replays return the original audit without
    replaying its state, even if a later decision has since advanced the alert.
    """
    request = RoutingRequest.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('routing requires foreign keys and no open transaction')
    try:
        conn.execute('BEGIN IMMEDIATE')
        actor = db.get(conn, m.User, actor_id)
        if actor is None or actor.status != 'active' or actor.role not in ('security_analyst', 'system_admin'):
            raise PermissionError('routing requires an active analyst or administrator')
        prior = conn.execute('SELECT * FROM operational_routing_audit WHERE request_id=?',
                             (str(request.request_id),)).fetchone()
        if prior is not None:
            if any(prior[key] != value for key, value in {
                'actor_id': actor_id, 'operational_alert_id': alert_id, 'action': action,
                'expected_state_version': request.expected_state_version, 'reason': request.reason,
            }.items()):
                raise RoutingConflict('requestId already belongs to a different decision')
            conn.commit()
            return decode_audit(prior), True
        before = read_triage(conn, alert_id)
        if state_version(before) != request.expected_state_version:
            raise RoutingConflict('V2 state changed; refresh and review before deciding again')
        if action not in allowed_actions(before):
            raise RoutingConflict('action is not allowed for the current route, stage and recommendation')
        moment = max(m.utc_now(), before.updated_at + timedelta(microseconds=1))
        route, stage = (('tier1_review', 'triage') if action in ('admit_tier1', 'reject_tier2')
                        else ('tier2_candidate', 'assessment'))
        # Admission preserves policy ownership; human escalation/rejection protects the decision
        # from subsequent policy reapplication. Every action is independently attributed in audit.
        source = before.decision_source if action == 'admit_tier1' else 'analyst'
        after = OperationalTriageStateV2.model_validate({**before.model_dump(),
            'handling_route': route, 'workflow_stage': stage, 'review_required': True,
            'decision_source': source, 'updated_at': moment})
        conn.execute('UPDATE operational_triage_state_v2 SET handling_route=?,workflow_stage=?, '
                     'review_required=1,decision_source=?,updated_at=? WHERE operational_alert_id=?',
                     (route, stage, source, db.format_timestamp(moment), alert_id))
        result = conn.execute('INSERT INTO operational_routing_audit '
            '(operational_alert_id,actor_id,request_id,action,event_type,expected_state_version,'
            'reason,before_state,after_state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (alert_id, actor_id, str(request.request_id), action, EVENTS[action], request.expected_state_version,
             request.reason, _json(before), _json(after), db.format_timestamp(moment)))
        if read_triage(conn, alert_id) != after:
            raise ValueError('routing storage round-trip mismatch')
        audit = decode_audit(conn.execute('SELECT * FROM operational_routing_audit WHERE id=?',
                                         (result.lastrowid,)).fetchone())
        conn.commit()
        return audit, False
    except Exception:
        conn.rollback()
        raise
