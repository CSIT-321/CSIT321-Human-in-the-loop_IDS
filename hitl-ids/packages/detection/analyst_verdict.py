"""Canonical human conclusions, independent of policy, memory and routing mutations."""
import json
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import Field, field_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.routing import state_version

VerdictOutcome = Literal['confirmed_malicious','suspicious','expected_activity','false_positive']

class VerdictCommand(V2Contract):
    request_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    expected_state_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    outcome: VerdictOutcome
    reason: str = Field(min_length=1,max_length=4000)

    @field_validator('reason')
    @classmethod
    def reason_required(cls,value):
        if not value.strip(): raise ValueError('a nonblank verdict reason is required')
        return value.strip()

class AnalystVerdict(V2Contract):
    verdict_ref: UUID
    operational_alert_ref: UUID
    actor_id: int
    actor_name: str
    decision_source: Literal['analyst'] = 'analyst'
    revision: int
    supersedes_ref: UUID | None
    outcome: VerdictOutcome
    reason: str
    created_at: str
    source_state_version: str
    evidence_snapshot: dict[str,Any]

class VerdictView(V2Contract):
    operational_alert_ref: UUID
    revision: int
    source_state_version: str
    can_record: bool
    latest: AnalystVerdict | None

class VerdictHistory(V2Contract):
    items: list[AnalystVerdict]
    total: int
    limit: int
    offset: int

class VerdictMutation(V2Contract):
    verdict: AnalystVerdict
    replayed: bool

class VerdictConflict(ValueError): pass

def _alert(conn,ref):
    row=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(ref),)).fetchone()
    if row is None: raise LookupError('operational alert not found')
    return read_projection(conn,row[0])

def _eligible(conn,alert):
    state=read_triage(conn,alert.id)
    return ((state.handling_route,state.workflow_stage)==('tier1_review','triage') and
            conn.execute('SELECT 1 FROM operational_system_routing WHERE operational_alert_id=?',(alert.id,)).fetchone() is not None)

def _decode(row):
    return AnalystVerdict.model_validate_json(row['snapshot']) if row else None

def latest_verdict(conn,alert_id):
    """Read the authoritative append-only Verdict revision without changing state."""
    return _decode(conn.execute('SELECT snapshot FROM analyst_verdict_events WHERE operational_alert_id=? ORDER BY revision DESC LIMIT 1',(alert_id,)).fetchone())


def read_verdict(conn,ref,actor_id):
    alert=_alert(conn,ref);actor=db.get(conn,m.User,actor_id)
    latest=latest_verdict(conn,alert.id)
    return VerdictView(operational_alert_ref=ref,revision=latest.revision if latest else 0,
        source_state_version=state_version(read_triage(conn,alert.id)),latest=latest,
        can_record=bool(actor and actor.status=='active' and actor.role in ('security_analyst','system_admin') and _eligible(conn,alert)))

def verdict_history(conn,ref,limit=50,offset=0):
    alert=_alert(conn,ref)
    rows=conn.execute('SELECT snapshot FROM analyst_verdict_events WHERE operational_alert_id=? ORDER BY revision DESC LIMIT ? OFFSET ?',(alert.id,limit,offset)).fetchall()
    total=conn.execute('SELECT count(*) FROM analyst_verdict_events WHERE operational_alert_id=?',(alert.id,)).fetchone()[0]
    return VerdictHistory(items=[_decode(row) for row in rows],total=total,limit=limit,offset=offset)

def record_verdict(conn,ref,*,actor_id,request):
    request=VerdictCommand.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('verdict requires foreign keys and no open transaction')
    payload=json.dumps(dict(alertRef=str(ref),actorId=actor_id,command=request.model_dump(mode='json')),sort_keys=True)
    try:
        conn.execute('BEGIN IMMEDIATE')
        actor=db.get(conn,m.User,actor_id)
        if actor is None or actor.status!='active' or actor.role not in ('security_analyst','system_admin'):
            raise PermissionError('verdict requires an active analyst or administrator')
        previous=conn.execute('SELECT * FROM analyst_verdict_events WHERE request_id=?',(str(request.request_id),)).fetchone()
        if previous:
            if previous['request_payload']!=payload: raise VerdictConflict('requestId belongs to another actor or payload')
            conn.commit();return VerdictMutation(verdict=_decode(previous),replayed=True)
        alert=_alert(conn,ref);view=read_verdict(conn,ref,actor_id)
        if not view.can_record: raise VerdictConflict('Tier 1 Verdict requires a current system-routed Tier 1 review; Tier 2 uses Investigation Finding')
        if view.revision!=request.expected_revision or view.source_state_version!=request.expected_state_version:
            raise VerdictConflict('verdict or workflow changed; refresh before recording')
        system=conn.execute('SELECT classification,routing_decision FROM operational_system_routing WHERE operational_alert_id=?',(alert.id,)).fetchone()
        verdict=AnalystVerdict(verdict_ref=uuid4(),operational_alert_ref=ref,actor_id=actor_id,actor_name=actor.display_name,
            revision=view.revision+1,supersedes_ref=view.latest.verdict_ref if view.latest else None,
            outcome=request.outcome,reason=request.reason,created_at=db.format_timestamp(m.utc_now()),
            source_state_version=view.source_state_version,evidence_snapshot=dict(detector=alert.model_dump(mode='json',by_alias=True),
                classification=json.loads(system['classification']),systemRouting=json.loads(system['routing_decision']),
                triage=read_triage(conn,alert.id).model_dump(mode='json',by_alias=True)))
        conn.execute('INSERT INTO analyst_verdict_events(verdict_ref,operational_alert_id,actor_id,revision,supersedes_ref,request_id,request_payload,snapshot) VALUES (?,?,?,?,?,?,?,?)',
            (str(verdict.verdict_ref),alert.id,actor_id,verdict.revision,str(verdict.supersedes_ref) if verdict.supersedes_ref else None,str(request.request_id),payload,verdict.model_dump_json(by_alias=True)))
        from packages.detection.triage_memory import automatic_evidence
        automatic_evidence(conn,ref,verdict=verdict)
        conn.commit();return VerdictMutation(verdict=verdict,replayed=False)
    except Exception:
        conn.rollback();raise
