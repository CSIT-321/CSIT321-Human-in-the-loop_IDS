"""Explicit Tier 2 cases. Findings are investigation records, never response authorization."""
from datetime import datetime, timedelta
import json
import sqlite3
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import Field, field_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract, OperationalAlertV2, OperationalTriageStateV2
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.routing import RoutingAudit, decode_audit, state_version

Finding = Literal['confirmed_malicious','suspicious','inconclusive','expected_activity']
CaseAction = Literal['create','link','note','finding','start']
EVENTS = dict(create='V2_TIER2_CASE_CREATED', link='V2_TIER2_ALERT_LINKED',
    note='V2_TIER2_NOTE_ADDED', finding='V2_TIER2_FINDING_RECORDED', start='V2_TIER2_INVESTIGATION_STARTED')


class CaseConflict(ValueError):
    pass


class CaseCommand(V2Contract):
    request_id: UUID
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(strict=True, ge=1)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('a nonblank reason or note is required')
        return value.strip()


class CreateCaseRequest(V2Contract):
    request_id: UUID
    expected_state_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    title: str = Field(min_length=1, max_length=200)
    tier1_handoff_summary: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('title', 'tier1_handoff_summary', 'reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('case title, handoff and reason must be nonblank')
        return value.strip()


class LinkCaseRequest(CaseCommand):
    operational_alert_ref: UUID


class FindingRequest(CaseCommand):
    finding: Finding


class CaseSnapshot(V2Contract):
    detector: OperationalAlertV2
    triage: OperationalTriageStateV2
    routing_decision: RoutingAudit
    escalation_reason: str
    tier1_handoff_summary: str
    creation_reason: str


class CaseView(V2Contract):
    case_ref: UUID
    primary_operational_alert_ref: UUID
    title: str
    owner_actor_id: int
    created_by_actor_id: int
    created_at: str
    updated_at: str
    status: Literal['open','investigating']
    revision: int
    snapshot: CaseSnapshot


class CaseEvent(V2Contract):
    id: int
    case_ref: UUID
    actor_id: int
    action: CaseAction
    event_type: str
    reason: str
    finding: Finding | None
    linked_alert_ref: UUID | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    created_at: str


class CaseMutation(V2Contract):
    case: CaseView
    event_id: int
    replayed: bool


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _actor(conn, actor_id):
    actor = db.get(conn, m.User, actor_id)
    if actor is None or actor.status != 'active' or actor.role not in ('security_analyst','system_admin'):
        raise PermissionError('case actions require an active operational analyst or administrator')


def _start(conn):
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('case action requires foreign keys and no existing transaction')
    conn.execute('BEGIN IMMEDIATE')


def _case(conn, ref):
    row = conn.execute('SELECT * FROM tier2_cases WHERE case_ref=?', (str(ref),)).fetchone()
    if row is None:
        raise LookupError('Tier 2 case not found')
    return row


def read_case(conn, ref):
    row = _case(conn, ref)
    state = conn.execute('SELECT * FROM tier2_case_state WHERE case_id=?', (row['id'],)).fetchone()
    snapshot = CaseSnapshot.model_validate_json(row['snapshot'])
    return CaseView(case_ref=row['case_ref'], primary_operational_alert_ref=snapshot.detector.operational_alert_ref,
        title=row['title'], owner_actor_id=row['owner_actor_id'], created_by_actor_id=row['created_by_actor_id'],
        created_at=row['created_at'], updated_at=state['updated_at'], status=state['status'],
        revision=state['revision'], snapshot=snapshot)


def _retry(conn, actor_id, action, payload, request_id):
    row = conn.execute('SELECT * FROM tier2_case_events WHERE request_id=?', (str(request_id),)).fetchone()
    if row is not None and (row['actor_id'] != actor_id or row['action'] != action or row['request_payload'] != payload):
        raise CaseConflict('requestId belongs to another case decision')
    return row


def _event(conn, case_id, actor_id, action, request, payload, before, after, moment,
           linked_id=None, finding=None):
    return conn.execute('INSERT INTO tier2_case_events (case_id,actor_id,request_id,action,event_type,'
        'request_payload,reason,finding,linked_alert_id,before_state,after_state,created_at) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (case_id,actor_id,str(request.request_id),action,EVENTS[action],
        payload,request.reason,finding,linked_id,_json(before),_json(after),moment)).lastrowid


def create_case(conn: sqlite3.Connection, alert_ref: UUID, *, actor_id: int, request: CreateCaseRequest):
    request = CreateCaseRequest.model_validate(request.model_dump())
    payload = _json(dict(alertRef=str(alert_ref), request=request.model_dump(mode='json')))
    _start(conn)
    try:
        _actor(conn, actor_id)
        retry = _retry(conn, actor_id, 'create', payload, request.request_id)
        if retry:
            ref = conn.execute('SELECT case_ref FROM tier2_cases WHERE id=?', (retry['case_id'],)).fetchone()[0]
            result = CaseMutation(case=read_case(conn,ref), event_id=retry['id'], replayed=True)
            conn.commit()
            return result
        row = conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (str(alert_ref),)).fetchone()
        if row is None:
            raise LookupError('Operational alert not found')
        alert = read_projection(conn, row['id'])
        before = read_triage(conn, alert.id)
        if state_version(before) != request.expected_state_version:
            raise CaseConflict('alert state changed; refresh before creating a case')
        if (before.handling_route, before.workflow_stage) != ('tier2_candidate','assessment'):
            raise CaseConflict('only an explicitly escalated Tier 2 candidate can create a case')
        prior = conn.execute('SELECT * FROM operational_routing_audit WHERE operational_alert_id=? '
                             'ORDER BY id DESC LIMIT 1', (alert.id,)).fetchone()
        decision = decode_audit(prior) if prior else None
        if decision is None or decision.action not in ('approve_tier2','manual_escalate') or decision.after_state != before:
            raise CaseConflict('candidate lacks a matching authenticated escalation decision')
        if conn.execute('SELECT 1 FROM tier2_cases WHERE primary_operational_alert_id=?', (alert.id,)).fetchone():
            raise CaseConflict('a case already exists for this primary alert')
        moment = max(m.utc_now(), before.updated_at + timedelta(microseconds=1))
        stamp = db.format_timestamp(moment)
        ref = uuid4()
        snapshot = CaseSnapshot(detector=alert,triage=before,routing_decision=decision,
            escalation_reason=decision.reason,tier1_handoff_summary=request.tier1_handoff_summary,
            creation_reason=request.reason)
        case_id = conn.execute('INSERT INTO tier2_cases (case_ref,primary_operational_alert_id,title,owner_actor_id,'
            'created_by_actor_id,snapshot,created_at) VALUES (?,?,?,?,?,?,?)',
            (str(ref),alert.id,request.title,actor_id,actor_id,snapshot.model_dump_json(by_alias=True),stamp)).lastrowid
        conn.execute('INSERT INTO tier2_case_state (case_id,status,revision,updated_at) VALUES (?,?,1,?)',
                     (case_id,'open',stamp))
        conn.execute("UPDATE operational_triage_state_v2 SET handling_route='tier2_case',workflow_stage='investigation',"
                     "decision_source='analyst',review_required=1,updated_at=? WHERE operational_alert_id=?", (stamp,alert.id))
        after = read_triage(conn, alert.id)
        event_id = _event(conn,case_id,actor_id,'create',request,payload,
                         before.model_dump(mode='json',by_alias=True),after.model_dump(mode='json',by_alias=True),stamp)
        result = CaseMutation(case=read_case(conn,ref),event_id=event_id,replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def mutate_case(conn, ref: UUID, *, actor_id: int, action: Literal['link','note','finding','start'],
                request: CaseCommand):
    model = LinkCaseRequest if action == 'link' else FindingRequest if action == 'finding' else CaseCommand
    request = model.model_validate(request.model_dump())
    payload = _json(dict(caseRef=str(ref),request=request.model_dump(mode='json')))
    _start(conn)
    try:
        _actor(conn, actor_id)
        case = _case(conn, ref)
        retry = _retry(conn, actor_id,action,payload,request.request_id)
        if retry:
            result = CaseMutation(case=read_case(conn,ref),event_id=retry['id'],replayed=True)
            conn.commit()
            return result
        before = dict(conn.execute('SELECT * FROM tier2_case_state WHERE case_id=?',(case['id'],)).fetchone())
        if before['revision'] != request.expected_revision:
            raise CaseConflict('case changed; refresh before recording another decision')
        if action not in ('link','note','finding','start'):
            raise CaseConflict('unsupported case action')
        if action == 'start' and before['status'] != 'open':
            raise CaseConflict('investigation has already started')
        linked_id = None
        if action == 'link':
            linked = conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',
                                   (str(request.operational_alert_ref),)).fetchone()
            if linked is None:
                raise LookupError('Linked operational alert not found')
            linked_id = linked[0]
            if linked_id == case['primary_operational_alert_id'] or conn.execute(
                    'SELECT 1 FROM tier2_case_events WHERE case_id=? AND linked_alert_id=?', (case['id'],linked_id)).fetchone():
                raise CaseConflict('alert is already part of this case')
        previous_time = datetime.fromisoformat(before['updated_at'].replace('Z','+00:00'))
        stamp = db.format_timestamp(max(m.utc_now(),previous_time+timedelta(microseconds=1)))
        status = 'investigating' if action == 'start' else before['status']
        conn.execute('UPDATE tier2_case_state SET status=?,revision=revision+1,updated_at=? WHERE case_id=?',
                     (status,stamp,case['id']))
        after = dict(conn.execute('SELECT * FROM tier2_case_state WHERE case_id=?',(case['id'],)).fetchone())
        event_id = _event(conn,case['id'],actor_id,action,request,payload,before,after,stamp,linked_id,
                          request.finding if action == 'finding' else None)
        result = CaseMutation(case=read_case(conn,ref),event_id=event_id,replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def read_events(conn, ref, limit, offset, action=None):
    case = _case(conn,ref)
    where = 'e.case_id=?' + (' AND e.action=?' if action else '')
    values = [case['id']] + ([action] if action else [])
    total = conn.execute('SELECT count(*) FROM tier2_case_events e WHERE '+where,values).fetchone()[0]
    rows = conn.execute('SELECT e.*,a.operational_alert_ref FROM tier2_case_events e LEFT JOIN operational_alerts_v2 a '
        'ON a.id=e.linked_alert_id WHERE '+where+' ORDER BY e.id DESC LIMIT ? OFFSET ?',[*values,limit,offset])
    items = [CaseEvent(id=row['id'],case_ref=ref,actor_id=row['actor_id'],action=row['action'],
        event_type=row['event_type'],reason=row['reason'],finding=row['finding'],linked_alert_ref=row['operational_alert_ref'],
        before_state=json.loads(row['before_state']),after_state=json.loads(row['after_state']),created_at=row['created_at'])
        for row in rows]
    return items,total
