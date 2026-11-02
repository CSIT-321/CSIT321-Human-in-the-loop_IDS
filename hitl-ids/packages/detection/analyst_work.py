"""Exclusive Tier 1 work. Pending contention rounds are not ownership leases.

Writers register intents under BEGIN IMMEDIATE, commit, then wait outside the
transaction. Any worker may finalize a due round. Only distinct actors count;
multiple contenders produce no owner. Reads never register or finalize rounds.
"""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import time
from typing import Literal
from uuid import UUID, uuid4
from pydantic import Field
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.adapters.operational_v2 import read_triage

Status = Literal['available','in_review','completed','escalated']
Scope = Literal['all','active','completed','escalated']

class ClaimCommand(V2Contract):
    request_id: UUID
    expected_revision: int = Field(ge=0,strict=True)

class WorkView(V2Contract):
    status: Status | None
    revision: int
    owner_actor_id: int | None = None
    owner_name: str | None = None
    claimed_at: str | None = None
    round_ref: str | None = None
    finished_at: str | None = None
    finished_by_actor_id: int | None = None
    finished_by_name: str | None = None
    verdict_ref: str | None = None
    verdict_outcome: str | None = None
    is_owner: bool = False
    can_claim: bool = False
    can_mutate: bool = False
    explanation: str

class ClaimResult(V2Contract):
    round_ref: str
    outcome: Literal['claimed','contended','ineligible']
    replayed: bool
    work: WorkView

class WorkEvent(V2Contract):
    id: int
    event_type: str
    actor_id: int | None
    decision_source: str
    round_ref: str | None
    created_at: str
    detail: dict

class WorkConflict(ValueError):
    pass

def now():
    return datetime.now(timezone.utc)

def policy():
    value=json.loads((Path(__file__).resolve().parents[2]/'config/analyst-work-claim-v1.json').read_text(encoding='utf-8'))
    if value['version']!='analyst-work-claim-v1' or not 1<=value['claimArbitrationWindowMs']<=5000:
        raise ValueError('invalid claim arbitration policy')
    return value

def _id(conn,ref):
    row=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(ref),)).fetchone()
    if row is None: raise LookupError('Operational alert not found')
    return row[0]

def _actor(conn,actor_id):
    actor=db.get(conn,m.User,actor_id)
    if actor is None or actor.status!='active' or actor.role not in ('security_analyst','system_admin'):
        raise PermissionError('active analyst or administrator required')
    return actor

def row(conn,alert_id):
    return conn.execute('SELECT * FROM analyst_work WHERE operational_alert_id=?',(alert_id,)).fetchone()

def is_tier1_work(conn,alert_id):
    state=read_triage(conn,alert_id)
    return ((state.handling_route,state.workflow_stage)==('tier1_review','triage') and
        conn.execute('SELECT 1 FROM operational_system_routing WHERE operational_alert_id=?',(alert_id,)).fetchone() is not None)

def read_work(conn,alert_id,actor_id=None,review=None):
    work=row(conn,alert_id);tier1=is_tier1_work(conn,alert_id)
    status=work['status'] if work else ('available' if tier1 else None)
    actor=db.get(conn,m.User,actor_id) if actor_id is not None else None
    permitted=bool(actor and actor.status=='active' and actor.role in ('security_analyst','system_admin'))
    owned=bool(work and status=='in_review' and work['owner_actor_id']==actor_id)
    deferred=False
    if tier1 and status=='available':
        if review is None:
            from packages.detection.selective_review import effective_review
            ref=conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2 WHERE id=?',(alert_id,)).fetchone()[0]
            review=effective_review(conn,ref)
        deferred=review.disposition=='no_immediate_review'
    claimable=tier1 and status=='available' and not deferred
    if deferred: status=None  # unowned deferral is not active Tier 1 work
    explanation=('Tier 1 work completed; historical Verdict corrections remain explicit.' if status=='completed' else
        'Tier 1 work transferred to the existing Tier 2 Case.' if status=='escalated' else
        'In Review — You' if owned else f"This alert is currently being reviewed by {work['owner_name']}." if status=='in_review' else
        'Require Human Review before starting work on a No Immediate Review alert.' if deferred else
        'Available for Review. Selecting this alert starts your review.' if claimable else 'Tier 1 claiming does not apply to this workflow.')
    fields={k:work[k] for k in ('revision','owner_actor_id','owner_name','claimed_at','round_ref','finished_at','finished_by_actor_id','finished_by_name','verdict_ref')} if work else {'revision':0}
    latest=conn.execute('SELECT snapshot FROM analyst_verdict_events WHERE operational_alert_id=? ORDER BY revision DESC LIMIT 1',(alert_id,)).fetchone()
    return WorkView(status=status,**fields,is_owner=owned,can_claim=permitted and claimable,
        can_mutate=permitted and owned and tier1,verdict_outcome=json.loads(latest[0])['outcome'] if latest else None,explanation=explanation)

def require_owner(conn,alert_id,actor_id):
    work=row(conn,alert_id)
    if not work or work['status']!='in_review' or work['owner_actor_id']!=actor_id:
        raise WorkConflict('Start Review and obtain ownership before performing this Tier 1 action.')

def protect_owner(conn,alert_id,actor_id):
    """Guard ancillary human mutations without making policy evaluation an implicit claim."""
    work=row(conn,alert_id)
    if work and work['status']=='in_review' and work['owner_actor_id']!=actor_id:
        raise WorkConflict(f"This alert is currently being reviewed by {work['owner_name']}.")

def _event(conn,alert_id,kind,actor_id=None,round_ref=None,**detail):
    conn.execute('INSERT INTO analyst_work_events(operational_alert_id,event_type,actor_id,decision_source,round_ref,created_at,detail) VALUES (?,?,?,?,?,?,?)',
        (alert_id,kind,actor_id,'analyst' if actor_id is not None else 'system_policy',round_ref,db.format_timestamp(now()),json.dumps(detail,sort_keys=True)))

def _finalize(conn,round_row):
    if round_row['status']!='pending' or now()<datetime.fromisoformat(round_row['closes_at']): return
    alert_id=round_row['operational_alert_id'];ref=round_row['round_ref']
    contenders=conn.execute('SELECT DISTINCT actor_id,actor_name FROM analyst_claim_intents WHERE round_ref=?',(ref,)).fetchall()
    actor_ids={r['actor_id'] for r in contenders}
    owner=next(iter(actor_ids)) if len(actor_ids)==1 else None
    eligible=read_work(conn,alert_id,owner).can_claim if owner is not None else False
    outcome='contended' if len(actor_ids)>1 else 'claimed' if eligible else 'ineligible'
    stamp=db.format_timestamp(now())
    conn.execute('UPDATE analyst_claim_rounds SET status=?,finalized_at=?,owner_actor_id=? WHERE round_ref=?',
        (outcome,stamp,owner if outcome=='claimed' else None,ref))
    work=row(conn,alert_id)
    if work['status']=='available':
        if outcome=='claimed':
            name=next(r['actor_name'] for r in contenders if r['actor_id']==owner)
            conn.execute("UPDATE analyst_work SET status='in_review',revision=revision+1,owner_actor_id=?,owner_name=?,claimed_at=?,round_ref=? WHERE operational_alert_id=?",
                (owner,name,stamp,ref,alert_id))
        else:
            conn.execute('UPDATE analyst_work SET revision=revision+1 WHERE operational_alert_id=?',(alert_id,))
    _event(conn,alert_id,'CLAIM_FINALIZED' if outcome=='claimed' else 'CLAIM_CONTENTION' if outcome=='contended' else 'CLAIM_INELIGIBLE',
        round_ref=ref,contenderActorIds=sorted(actor_ids),ownerActorId=owner if outcome=='claimed' else None,policyVersion=round_row['policy_version'])

def register(conn,ref,actor_id,request):
    """Commit an intent before waiting, so another process can join the same round."""
    request=ClaimCommand.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]: raise ValueError('claim requires foreign keys and no open transaction')
    payload=json.dumps({'alertRef':str(ref),'actorId':actor_id,'request':request.model_dump(mode='json')},sort_keys=True)
    try:
        conn.execute('BEGIN IMMEDIATE');actor=_actor(conn,actor_id)
        previous=conn.execute('SELECT * FROM analyst_claim_intents WHERE request_id=?',(str(request.request_id),)).fetchone()
        if previous:
            if previous['request_payload']!=payload: raise WorkConflict('requestId belongs to another actor or payload')
            conn.commit();return previous['round_ref'],True
        alert_id=_id(conn,ref)
        pending=conn.execute("SELECT * FROM analyst_claim_rounds WHERE operational_alert_id=? AND status='pending'",(alert_id,)).fetchone()
        if pending and now()>=datetime.fromisoformat(pending['closes_at']):
            _finalize(conn,pending);conn.commit()
            # Persist the old round's outcome even when this later caller is rejected.
            conn.execute('BEGIN IMMEDIATE');_actor(conn,actor_id)
        work=read_work(conn,alert_id,actor_id)
        if work.is_owner:
            conn.execute('INSERT INTO analyst_claim_intents VALUES (?,?,?,?,?,?)',
                (str(request.request_id),work.round_ref,actor_id,actor.display_name,payload,db.format_timestamp(now())))
            conn.commit();return work.round_ref,True
        if not work.can_claim: raise WorkConflict(work.explanation)
        if work.revision!=request.expected_revision: raise WorkConflict('Work changed; refresh the shared queue and select again.')
        pending=conn.execute("SELECT * FROM analyst_claim_rounds WHERE operational_alert_id=? AND status='pending'",(alert_id,)).fetchone()
        if not row(conn,alert_id):
            conn.execute("INSERT INTO analyst_work(operational_alert_id,status) VALUES (?,'available')",(alert_id,))
        if not pending:
            config=policy();stamp=now();round_ref=str(uuid4())
            conn.execute('INSERT INTO analyst_claim_rounds(round_ref,operational_alert_id,work_revision,policy_version,window_ms,started_at,closes_at,status) VALUES (?,?,?,?,?,?,?,?)',
                (round_ref,alert_id,work.revision,config['version'],config['claimArbitrationWindowMs'],db.format_timestamp(stamp),db.format_timestamp(stamp+timedelta(milliseconds=config['claimArbitrationWindowMs'])),'pending'))
            _event(conn,alert_id,'CLAIM_ROUND_STARTED',round_ref=round_ref,policyVersion=config['version'],windowMs=config['claimArbitrationWindowMs'])
        else: round_ref=pending['round_ref']
        conn.execute('INSERT INTO analyst_claim_intents VALUES (?,?,?,?,?,?)',
            (str(request.request_id),round_ref,actor_id,actor.display_name,payload,db.format_timestamp(now())))
        _event(conn,alert_id,'CLAIM_INTENT',actor_id,round_ref,requestId=str(request.request_id),actorName=actor.display_name)
        conn.commit();return round_ref,False
    except Exception:
        conn.rollback();raise

def finish_round(conn,round_ref,actor_id,replayed=False):
    try:
        conn.execute('BEGIN IMMEDIATE');_actor(conn,actor_id)
        current=conn.execute('SELECT * FROM analyst_claim_rounds WHERE round_ref=?',(round_ref,)).fetchone()
        if current is None: raise LookupError('Claim round not found')
        _finalize(conn,current)
        current=conn.execute('SELECT * FROM analyst_claim_rounds WHERE round_ref=?',(round_ref,)).fetchone()
        if current['status']=='pending':
            conn.commit();return None
        result=ClaimResult(round_ref=round_ref,outcome=current['status'],replayed=replayed,work=read_work(conn,current['operational_alert_id'],actor_id))
        conn.commit();return result
    except Exception:
        conn.rollback();raise

def claim(conn,ref,*,actor_id,request):
    round_ref,replayed=register(conn,ref,actor_id,request)
    while True:
        current=conn.execute('SELECT closes_at FROM analyst_claim_rounds WHERE round_ref=?',(round_ref,)).fetchone()
        delay=(datetime.fromisoformat(current[0])-now()).total_seconds()
        if delay>0: time.sleep(min(delay,5))  # no transaction/lock is held while waiting
        result=finish_round(conn,round_ref,actor_id,replayed)
        if result is not None: return result

def complete(conn,alert_id,actor_id,verdict):
    require_owner(conn,alert_id,actor_id)
    actor=_actor(conn,actor_id);work=row(conn,alert_id)
    conn.execute("UPDATE analyst_work SET status='completed',revision=revision+1,owner_actor_id=NULL,finished_at=?,finished_by_actor_id=?,finished_by_name=?,verdict_ref=? WHERE operational_alert_id=?",
        (verdict.created_at,actor_id,actor.display_name,str(verdict.verdict_ref),alert_id))
    _event(conn,alert_id,'WORK_COMPLETED',actor_id,work['round_ref'],verdictRef=str(verdict.verdict_ref),outcome=verdict.outcome)

def escalated(conn,alert_id,actor_id,case_ref):
    require_owner(conn,alert_id,actor_id)
    actor=_actor(conn,actor_id);work=row(conn,alert_id)
    conn.execute("UPDATE analyst_work SET status='escalated',revision=revision+1,owner_actor_id=NULL,finished_at=?,finished_by_actor_id=?,finished_by_name=? WHERE operational_alert_id=?",
        (db.format_timestamp(now()),actor_id,actor.display_name,alert_id))
    _event(conn,alert_id,'WORK_ESCALATED',actor_id,work['round_ref'],caseRef=str(case_ref))

def history(conn,alert_id,limit=50,offset=0):
    return [WorkEvent(**{k:r[k] for k in ('id','event_type','actor_id','decision_source','round_ref','created_at')},detail=json.loads(r['detail']))
        for r in conn.execute('SELECT * FROM analyst_work_events WHERE operational_alert_id=? ORDER BY id DESC LIMIT ? OFFSET ?',(alert_id,limit,offset))]
