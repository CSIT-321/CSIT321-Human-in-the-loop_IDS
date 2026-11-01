"""Case-scoped response plans. Human approval records authorization, never execution."""
from datetime import datetime,timedelta
from ipaddress import ip_address
import json
from typing import Literal
from uuid import UUID,uuid4
from pydantic import Field,field_validator
from packages.contracts import db,models as m
from packages.contracts.operational_v2 import V2Contract,OperationalAlertV2
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.tier2_cases import read_case
from packages.detection.response_policy import ResponseFinding,ResponseType,TargetType,recommend_response


class ResponseConflict(ValueError):
    pass


class ResponseRequest(V2Contract):
    request_id: UUID
    expected_case_revision: int = Field(strict=True,ge=1)
    reason: str = Field(min_length=1,max_length=4000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():
            raise ValueError('a nonblank reason is required')
        return value.strip()


class ManualResponseRequest(ResponseRequest):
    recommendation_type: ResponseType
    target_type: TargetType
    target_value: str = Field(min_length=1,max_length=500)

    @field_validator('target_value')
    @classmethod
    def target_nonblank(cls,value):
        if not value.strip():
            raise ValueError('an explicit target is required')
        return value.strip()


class ResponseDecisionRequest(ResponseRequest):
    expected_revision: int = Field(strict=True,ge=1)


class ResponseEvidence(V2Contract):
    case_ref: UUID
    case_revision: int
    finding: ResponseFinding | None
    target_basis: Literal['primary_source_ip','linked_source_ip','case_scope','primary_alert','linked_alert']
    target_alert: OperationalAlertV2 | None
    link_event_id: int | None


class ResponseProposal(V2Contract):
    recommendation_ref: UUID
    case_ref: UUID
    proposed_by_actor_id: int
    proposal_source: Literal['system_policy','analyst']
    recommendation_type: ResponseType
    target_type: TargetType
    target_value: str
    rationale: str
    proposal_reason: str
    case_revision: int
    policy_version: str | None
    evidence_snapshot: ResponseEvidence
    event_type: str
    created_at: str


class ResponseDecision(V2Contract):
    actor_id: int
    decision: Literal['approved','rejected']
    reason: str
    event_type: str
    created_at: str
    proposal_snapshot: ResponseProposal


class ResponseView(V2Contract):
    proposal: ResponseProposal
    status: Literal['pending','approved','rejected']
    revision: int
    decision: ResponseDecision | None
    execution_status: Literal['not_executed'] = 'not_executed'


class ResponseMutation(V2Contract):
    response: ResponseView
    replayed: bool


def _json(value):
    return json.dumps(value,sort_keys=True,allow_nan=False)


def _begin(conn,actor_id):
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('response actions require foreign keys and no existing transaction')
    conn.execute('BEGIN IMMEDIATE')
    actor = db.get(conn,m.User,actor_id)
    if actor is None or actor.status != 'active' or actor.role not in ('security_analyst','system_admin'):
        conn.rollback()
        raise PermissionError('response actions require an active operational analyst or administrator')


def _case_id(conn,ref):
    row = conn.execute('SELECT id FROM tier2_cases WHERE case_ref=?',(str(ref),)).fetchone()
    if row is None:
        raise LookupError('Formal Tier 2 case not found')
    return row[0]


def _finding(conn,case_id):
    row = conn.execute("SELECT * FROM tier2_case_events WHERE case_id=? AND action='finding' ORDER BY id DESC LIMIT 1",
                       (case_id,)).fetchone()
    return ResponseFinding(event_id=row['id'],finding=row['finding'],actor_id=row['actor_id'],
        reason=row['reason'],created_at=row['created_at']) if row else None


def resolve_target(conn,case,case_id,recommendation_type,target_type,target_value):
    """No extraction from prose and no account/host inferred from an IP address."""
    if recommendation_type in ('isolate_host','disable_account'):
        raise ResponseConflict('Structured host/account identity evidence is unavailable; this target-specific proposal is blocked')
    primary = case.snapshot.detector
    if recommendation_type == 'block_source_ip':
        if target_type != 'ip':
            raise ResponseConflict('block_source_ip requires an evidence-backed source IP')
        try:
            target_value = str(ip_address(target_value))
        except ValueError as exc:
            raise ResponseConflict('invalid source IP target') from exc
        if target_value == primary.source_ip:
            return target_value,'primary_source_ip',primary,None
        linked = conn.execute("SELECT e.id,e.linked_alert_id FROM tier2_case_events e JOIN operational_alerts_v2 a "
            "ON a.id=e.linked_alert_id WHERE e.case_id=? AND e.action='link' AND a.source_ip=? ORDER BY e.id LIMIT 1",
            (case_id,target_value)).fetchone()
        if linked:
            return target_value,'linked_source_ip',read_projection(conn,linked['linked_alert_id']),linked['id']
        raise ResponseConflict('source IP is not present in primary or explicitly linked case evidence')
    if recommendation_type not in ('monitor','further_investigation','notify_security_team'):
        raise ResponseConflict('unsupported response type')
    if target_type == 'case' and target_value == str(case.case_ref):
        return target_value,'case_scope',None,None
    if recommendation_type == 'monitor' and target_type == 'operational_alert':
        if target_value == str(primary.operational_alert_ref):
            return target_value,'primary_alert',primary,None
        linked = conn.execute("SELECT e.id,e.linked_alert_id FROM tier2_case_events e JOIN operational_alerts_v2 a "
            "ON a.id=e.linked_alert_id WHERE e.case_id=? AND e.action='link' AND a.operational_alert_ref=?",
            (case_id,target_value)).fetchone()
        if linked:
            return target_value,'linked_alert',read_projection(conn,linked['linked_alert_id']),linked['id']
    raise ResponseConflict('target must match the case or a supported explicitly linked operational alert')


def _view(conn,row,case_ref):
    proposal = ResponseProposal(
        recommendation_ref=row['recommendation_ref'],case_ref=case_ref,proposed_by_actor_id=row['proposed_by_actor_id'],
        proposal_source=row['proposal_source'],recommendation_type=row['recommendation_type'],
        target_type=row['target_type'],target_value=row['target_value'],rationale=row['rationale'],
        proposal_reason=row['proposal_reason'],case_revision=row['case_revision'],policy_version=row['policy_version'],
        evidence_snapshot=ResponseEvidence.model_validate_json(row['evidence_snapshot']),event_type=row['event_type'],
        created_at=row['created_at'])
    decided = conn.execute('SELECT * FROM response_decisions WHERE recommendation_id=?',(row['id'],)).fetchone()
    decision = ResponseDecision(actor_id=decided['actor_id'],decision=decided['decision'],reason=decided['reason'],
        event_type=decided['event_type'],created_at=decided['created_at'],
        proposal_snapshot=ResponseProposal.model_validate_json(decided['proposal_snapshot'])) if decided else None
    return ResponseView(proposal=proposal,status=decision.decision if decision else 'pending',
                        revision=2 if decision else 1,decision=decision)


def list_responses(conn,case_ref,limit,offset):
    case_id = _case_id(conn,case_ref)
    total = conn.execute('SELECT count(*) FROM response_recommendations WHERE case_id=?',(case_id,)).fetchone()[0]
    rows = conn.execute('SELECT * FROM response_recommendations WHERE case_id=? ORDER BY id DESC LIMIT ? OFFSET ?',
                        (case_id,limit,offset)).fetchall()
    return [_view(conn,row,case_ref) for row in rows],total,read_case(conn,case_ref).revision


def propose_response(conn,case_ref: UUID,*,actor_id:int,request:ResponseRequest,manual:bool=False):
    model = ManualResponseRequest if manual else ResponseRequest
    request = model.model_validate(request.model_dump())
    source = 'analyst' if manual else 'system_policy'
    payload = _json(dict(caseRef=str(case_ref),source=source,request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        case_id = _case_id(conn,case_ref)
        retry = conn.execute('SELECT * FROM response_recommendations WHERE request_id=?',(str(request.request_id),)).fetchone()
        if retry:
            if retry['proposed_by_actor_id'] != actor_id or retry['request_payload'] != payload:
                raise ResponseConflict('requestId belongs to another response proposal')
            result = ResponseMutation(response=_view(conn,retry,case_ref),replayed=True)
            conn.commit()
            return result
        case = read_case(conn,case_ref)
        if case.status=='resolved':
            raise ResponseConflict('Case is resolved; new response proposals are closed')
        if case.revision != request.expected_case_revision:
            raise ResponseConflict('case changed; refresh before proposing a response')
        finding = _finding(conn,case_id)
        if manual:
            kind,target_type,target_value = request.recommendation_type,request.target_type,request.target_value
            rationale,version = request.reason,None
        else:
            suggestion = recommend_response(finding,case.case_ref,case.snapshot.detector.source_ip)
            kind,target_type,target_value = suggestion.recommendation_type,suggestion.target_type,suggestion.target_value
            rationale,version = suggestion.rationale,suggestion.policy_version
        target,basis,alert,link_id = resolve_target(conn,case,case_id,kind,target_type,target_value)
        evidence = ResponseEvidence(case_ref=case_ref,case_revision=case.revision,finding=finding,
            target_basis=basis,target_alert=alert,link_event_id=link_id)
        ref = uuid4()
        event = 'V2_RESPONSE_MANUAL_RECOMMENDATION' if manual else 'V2_RESPONSE_RECOMMENDED'
        stamp = db.format_timestamp(m.utc_now())
        cursor = conn.execute('INSERT INTO response_recommendations (recommendation_ref,case_id,proposed_by_actor_id,proposal_source,'
            'recommendation_type,target_type,target_value,rationale,proposal_reason,case_revision,policy_version,'
            'evidence_snapshot,request_id,request_payload,event_type,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (str(ref),case_id,actor_id,source,kind,target_type,target,rationale,request.reason,case.revision,version,
             evidence.model_dump_json(by_alias=True),str(request.request_id),payload,event,stamp))
        row = conn.execute('SELECT * FROM response_recommendations WHERE id=?',(cursor.lastrowid,)).fetchone()
        result = ResponseMutation(response=_view(conn,row,case_ref),replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def decide_response(conn,case_ref:UUID,recommendation_ref:UUID,*,actor_id:int,
                    decision:Literal['approved','rejected'],request:ResponseDecisionRequest):
    request = ResponseDecisionRequest.model_validate(request.model_dump())
    if decision not in ('approved','rejected'):
        raise ValueError('unsupported human response decision')
    payload = _json(dict(caseRef=str(case_ref),recommendationRef=str(recommendation_ref),decision=decision,
                        request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        case_id = _case_id(conn,case_ref)
        row = conn.execute('SELECT * FROM response_recommendations WHERE case_id=? AND recommendation_ref=?',
                           (case_id,str(recommendation_ref))).fetchone()
        if row is None:
            raise LookupError('Case response recommendation not found')
        retry = conn.execute('SELECT * FROM response_decisions WHERE request_id=?',(str(request.request_id),)).fetchone()
        if retry:
            if retry['actor_id'] != actor_id or retry['request_payload'] != payload:
                raise ResponseConflict('requestId belongs to another response decision')
            result = ResponseMutation(response=_view(conn,row,case_ref),replayed=True)
            conn.commit()
            return result
        current = _view(conn,row,case_ref)
        case = read_case(conn,case_ref)
        if case.status=='resolved':
            raise ResponseConflict('Case is resolved; new response decisions are closed')
        if case.revision != request.expected_case_revision or current.revision != request.expected_revision:
            raise ResponseConflict('case or recommendation changed; refresh before deciding')
        if current.status != 'pending':
            raise ResponseConflict('response already decided; create a new recommendation instead')
        if decision == 'approved':
            if current.proposal.case_revision != case.revision:
                raise ResponseConflict('case evidence changed since proposal; create a fresh recommendation before approval')
            if current.proposal.evidence_snapshot.finding != _finding(conn,case_id):
                raise ResponseConflict('finding changed since proposal; a fresh recommendation is required')
            resolve_target(conn,case,case_id,current.proposal.recommendation_type,
                           current.proposal.target_type,current.proposal.target_value)
        created = datetime.fromisoformat(current.proposal.created_at.replace('Z','+00:00'))
        stamp = db.format_timestamp(max(m.utc_now(),created+timedelta(microseconds=1)))
        event = 'V2_RESPONSE_APPROVED' if decision == 'approved' else 'V2_RESPONSE_REJECTED'
        conn.execute('INSERT INTO response_decisions (recommendation_id,actor_id,decision,reason,request_id,request_payload,'
            'proposal_snapshot,event_type,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (row['id'],actor_id,decision,request.reason,str(request.request_id),payload,
             current.proposal.model_dump_json(by_alias=True),event,stamp))
        result = ResponseMutation(response=_view(conn,row,case_ref),replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
