"""Opt-in collection ledger. No policy, detector or human-outcome automation."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.selective_review import ReviewSnapshot, ReviewConflict
from packages.detection.selective_review_policy import SelectivePolicy, load_policy
from packages.detection.trusted_context import ContextPolicy, load_context_policy


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def code_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[3], text=True).strip()


def clean_code_tree():
    return not subprocess.check_output(['git','--no-optional-locks','status','--porcelain','--untracked-files=normal'],
        cwd=Path(__file__).resolve().parents[3],text=True).strip()


class CollectionConflict(ReviewConflict):
    pass


class RunCreate(V2Contract):
    request_id: UUID
    protocol_version: str = Field(min_length=1, max_length=100)
    evidence_basis: Literal['synthetic/demo', 'historical-inputs-unverified']
    participant_class: Literal['professional_analyst', 'proxy_student_analyst']
    holdout_start: AwareDatetime | None = None
    holdout_end: AwareDatetime | None = None
    outcome_cutoff: AwareDatetime | None = None
    minimum_eligible_alerts: int = Field(default=100, strict=True, ge=1)
    minimum_outcome_completeness: float = Field(default=.95, gt=0, le=1)
    readiness_review_reference: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode='after')
    def window(self):
        dates = (self.holdout_start, self.holdout_end, self.outcome_cutoff)
        if any(v is not None for v in dates) and (any(v is None for v in dates) or not dates[0] < dates[1] <= dates[2]):
            raise ValueError('supply start < end <= outcome cutoff, or leave all dates unset')
        if self.readiness_review_reference is not None and not self.readiness_review_reference.strip():
            raise ValueError('readiness review reference cannot be blank')
        return self


class FrozenProtocol(V2Contract):
    registration: RunCreate
    registered_at: AwareDatetime
    code_commit_sha: str = Field(pattern=r'^[a-f0-9]{40}$')
    source_tree_clean: bool
    evaluation_mode: Literal['prospective_recorded'] = 'prospective_recorded'
    selective_policy: SelectivePolicy
    context_policy: ContextPolicy
    selective_policy_hash: str
    context_policy_hash: str
    safety_metrics: list[str] = ['unsafeDeferrals', 'outcomeCompleteness', 'contextCoverage', 'recalls']
    workload_metrics: list[str] = ['reviewVolumeReduction', 'analystReviewSeconds', 'totalTaskSeconds', 'errors', 'rework']


class RunView(V2Contract):
    run_ref: UUID
    protocol: FrozenProtocol
    protocol_hash: str
    status: Literal['draft', 'open', 'closed', 'evaluated']
    revision: int
    decision_count: int
    created_by_actor_id: int
    opened_at: AwareDatetime | None
    opened_by_actor_id: int | None
    closed_at: AwareDatetime | None
    closed_by_actor_id: int | None


class RunPage(V2Contract):
    items: list[RunView]


class RunCommand(V2Contract):
    request_id: UUID
    expected_revision: int = Field(strict=True, ge=1)


class RecordedDecision(V2Contract):
    decision_ref: UUID
    review_event_id: int
    run_ref: UUID
    operational_alert_ref: UUID
    alert_occurred_at: AwareDatetime
    operational_admitted_at: AwareDatetime
    review_eligible_at: AwareDatetime
    decision_at: AwareDatetime
    availability_boundary: dict[str, AwareDatetime]
    actor_id: int
    action: Literal['apply', 'require_review']
    snapshot: ReviewSnapshot
    policy_hash: str
    input_fingerprint: str
    run_protocol_hash: str


class ObservationRequest(RunCommand):
    operational_alert_ref: UUID
    analyst_review_seconds: float | None = Field(default=None, ge=0)
    total_task_seconds: float | None = Field(default=None, ge=0)
    errors: int = Field(default=0, strict=True, ge=0)
    rework: int = Field(default=0, strict=True, ge=0)
    notes: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def duration(self):
        if not self.notes.strip(): raise ValueError('observation notes required')
        if self.analyst_review_seconds is not None and self.total_task_seconds is not None and self.analyst_review_seconds > self.total_task_seconds:
            raise ValueError('review duration cannot exceed total task duration')
        return self


class RecordedObservation(V2Contract):
    request: ObservationRequest
    actor_id: int
    available_at: AwareDatetime
    recalled: bool
    reason_codes: list[str]
    measurement_method: Literal['human_reported_stopwatch'] = 'human_reported_stopwatch'


def _row(conn, ref):
    row = conn.execute('SELECT * FROM prospective_runs WHERE run_ref=?', (str(ref),)).fetchone()
    if row is None: raise LookupError('Collection run not found')
    return row


def read_run(conn, ref):
    row = _row(conn, ref)
    events = list(conn.execute('SELECT * FROM prospective_run_events WHERE run_id=? ORDER BY id', (row['id'],)))
    opened = next((e for e in events if e['action'] == 'open'), None)
    closed = next((e for e in events if e['action'] == 'close'), None)
    count = conn.execute('SELECT count(*) FROM prospective_decisions WHERE run_id=?', (row['id'],)).fetchone()[0]
    observations = conn.execute('SELECT count(*) FROM prospective_observations WHERE run_id=?', (row['id'],)).fetchone()[0]
    protocol = FrozenProtocol.model_validate_json(row['snapshot'])
    return RunView(run_ref=ref, protocol=protocol, protocol_hash=digest(protocol.model_dump(mode='json', by_alias=True)),
        status={'open':'open','close':'closed','evaluated':'evaluated'}[events[-1]['action']] if events else 'draft',
        revision=1+len(events)+count+observations, decision_count=count, created_by_actor_id=row['actor_id'],
        opened_at=opened['created_at'] if opened else None, opened_by_actor_id=opened['actor_id'] if opened else None,
        closed_at=closed['created_at'] if closed else None, closed_by_actor_id=closed['actor_id'] if closed else None)


def list_runs(conn):
    return RunPage(items=[read_run(conn,r[0]) for r in conn.execute('SELECT run_ref FROM prospective_runs ORDER BY id DESC').fetchall()])


def _begin(conn, actor_id, *, admin=False):
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('foreign keys and no existing transaction required')
    conn.execute('BEGIN IMMEDIATE')
    actor = db.get(conn, m.User, actor_id)
    roles = ('system_admin',) if admin else ('system_admin','security_analyst')
    if actor is None or actor.status != 'active' or actor.role not in roles:
        raise PermissionError('active authorized collection actor required')


def _retry(conn, table, actor_id, request_id, payload):
    row = conn.execute(f'SELECT * FROM {table} WHERE request_id=?', (str(request_id),)).fetchone()
    if row and (row['actor_id'] != actor_id or row['request_payload'] != payload):
        raise CollectionConflict('requestId belongs to a different collection operation')
    return row


def create_run(conn, actor_id, request):
    request = RunCreate.model_validate(request.model_dump())
    payload = request.model_dump_json(by_alias=True)
    try:
        _begin(conn, actor_id, admin=True)
        retry = _retry(conn,'prospective_runs',actor_id,request.request_id,payload)
        if retry:
            result=read_run(conn,retry['run_ref']); conn.commit(); return result
        now = m.utc_now()
        if request.holdout_start is not None and request.holdout_start <= now:
            raise ValueError('registration must precede a future holdout; no backdating')
        policy, context = load_policy(), load_context_policy()
        clean=clean_code_tree()
        if request.evidence_basis!='synthetic/demo' and not clean:
            raise CollectionConflict('non-synthetic registration requires a clean committed code tree')
        protocol=FrozenProtocol(registration=request,registered_at=now,code_commit_sha=code_commit(),source_tree_clean=clean,selective_policy=policy,
            context_policy=context,selective_policy_hash=digest(policy.model_dump(mode='json',by_alias=True)),
            context_policy_hash=digest(context.model_dump(mode='json',by_alias=True)))
        ref=uuid4()
        conn.execute('INSERT INTO prospective_runs (run_ref,actor_id,request_id,request_payload,snapshot,created_at) VALUES (?,?,?,?,?,?)',
            (str(ref),actor_id,str(request.request_id),payload,protocol.model_dump_json(by_alias=True),db.format_timestamp(now)))
        result=read_run(conn,ref); conn.commit(); return result
    except Exception:
        conn.rollback(); raise


def change_run(conn, ref, actor_id, action, request):
    request=RunCommand.model_validate(request.model_dump())
    payload=canonical(dict(runRef=str(ref),action=action,request=request.model_dump(mode='json')))
    try:
        _begin(conn,actor_id,admin=True)
        row=_row(conn,ref)
        retry=_retry(conn,'prospective_run_events',actor_id,request.request_id,payload)
        run=read_run(conn,ref)
        if retry: conn.commit(); return run
        if request.expected_revision!=run.revision: raise CollectionConflict('collection changed; refresh revision')
        now=m.utc_now(); plan=run.protocol.registration; event={}
        if action=='open':
            if run.status!='draft' or plan.holdout_start is None or not now < plan.holdout_start:
                raise CollectionConflict('only a future-dated draft can open before its start')
            if not plan.readiness_review_reference: raise CollectionConflict('final PASS review reference required before opening')
            if plan.evidence_basis!='synthetic/demo' and not clean_code_tree(): raise CollectionConflict('registered code tree must remain clean')
            if code_commit()!=run.protocol.code_commit_sha or load_policy()!=run.protocol.selective_policy or load_context_policy()!=run.protocol.context_policy:
                raise CollectionConflict('code or configuration differs from frozen registration')
        elif action=='close':
            if run.status!='open' or now < plan.outcome_cutoff:
                raise CollectionConflict('close only after the outcome cutoff')
        elif action=='evaluated':
            if run.status!='closed': raise CollectionConflict('only a closed run can record evaluation')
            from packages.evaluation.prospective_recorded import export_connection, evaluate_recorded
            event['reportHash']=digest(evaluate_recorded(export_connection(conn,ref),now=now))
        else: raise ValueError('unsupported collection action')
        conn.execute('INSERT INTO prospective_run_events (run_id,actor_id,request_id,request_payload,action,snapshot,created_at) VALUES (?,?,?,?,?,?,?)',
            (row['id'],actor_id,str(request.request_id),payload,action,canonical(event),db.format_timestamp(now)))
        result=read_run(conn,ref); conn.commit(); return result
    except Exception:
        conn.rollback(); raise


def prepare_decision(conn, run_ref, expected_revision, actor_id, action, snapshot, at):
    """Validate optional collection eligibility without writing either ledger."""
    row=_row(conn,run_ref); run=read_run(conn,run_ref); plan=run.protocol.registration
    if run.status!='open': raise CollectionConflict('the run is '+run.status)
    if at<plan.holdout_start: raise CollectionConflict('the holdout window has not started')
    if at>=plan.holdout_end: raise CollectionConflict('the holdout window has ended')
    if run.revision!=expected_revision: raise CollectionConflict('collection changed; refresh revision')
    if code_commit()!=run.protocol.code_commit_sha or snapshot.policy_config_snapshot!=run.protocol.selective_policy:
        raise CollectionConflict('decision code/policy differs from frozen collection')
    if plan.evidence_basis!='synthetic/demo' and not clean_code_tree(): raise CollectionConflict('registered code tree must remain clean')
    provenance=snapshot.context_provenance
    if provenance is None: raise CollectionConflict('decision-time context provenance required')
    if any(f.freshness_policy!=run.protocol.context_policy for field in provenance.fields for f in field.facts):
        raise CollectionConflict('referenced context configuration differs from frozen collection')
    aid=snapshot.inputs.alert.id
    admission=conn.execute("SELECT created_at FROM operational_routing_audit WHERE operational_alert_id=? AND action='admit_tier1' ORDER BY id LIMIT 1",(aid,)).fetchone()
    if admission is None: raise CollectionConflict('recorded operational admission is required')
    from datetime import datetime
    stamp=lambda s: datetime.fromisoformat(str(s).replace('Z','+00:00')) if isinstance(s,str) else s
    boundary={'admission':stamp(admission[0]),'policy':run.opened_at,'triage':snapshot.inputs.triage.updated_at}
    for field in provenance.fields:
        for fact in field.facts:
            boundary['fact:'+str(fact.fact_ref)]=max(fact.available_at,fact.recorded_at,fact.valid_from)
    for match in snapshot.inputs.matches:
        memory=match.memory
        dates=[stamp(memory.lesson.created_at),stamp(memory.last_supported_at)]
        if memory.last_conflict_at: dates.append(stamp(memory.last_conflict_at))
        if memory.decision: dates.append(stamp(memory.decision.created_at))
        if memory.valid_from is not None and memory.valid_from<=at: dates.append(memory.valid_from)
        boundary['lesson:'+str(memory.lesson.lesson_ref)]=max(dates)
    # Absence/unknown is first observed by this evaluation, never assigned an invented earlier time.
    if not provenance.complete or not snapshot.inputs.matches: boundary['unknownInputsObserved']=at
    if any(t>at for t in boundary.values()): raise CollectionConflict('future input cannot enter a recorded decision')
    return RecordedDecision(decision_ref=uuid4(),review_event_id=0,run_ref=run_ref,
        operational_alert_ref=snapshot.inputs.alert.operational_alert_ref,alert_occurred_at=snapshot.inputs.alert.occurred_at,
        operational_admitted_at=admission[0],review_eligible_at=max(boundary.values()),decision_at=at,
        availability_boundary=boundary,actor_id=actor_id,action=action,snapshot=snapshot,
        policy_hash=digest(snapshot.policy_config_snapshot.model_dump(mode='json',by_alias=True)),
        input_fingerprint=digest(snapshot.model_dump(mode='json',by_alias=True)),run_protocol_hash=run.protocol_hash)


def persist_decision(conn, decision, event_id):
    """Called in the same serialized transaction after the operational event exists."""
    decision=decision.model_copy(update={'review_event_id':event_id})
    conn.execute('INSERT INTO prospective_decisions (run_id,review_event_id,snapshot) VALUES (?,?,?)',
        (_row(conn,decision.run_ref)['id'],event_id,decision.model_dump_json(by_alias=True)))


def observe(conn,ref,actor_id,request):
    request=ObservationRequest.model_validate(request.model_dump())
    payload=canonical(dict(runRef=str(ref),request=request.model_dump(mode='json')))
    try:
        _begin(conn,actor_id)
        row=_row(conn,ref); run=read_run(conn,ref)
        retry=_retry(conn,'prospective_observations',actor_id,request.request_id,payload)
        if retry: conn.commit(); return run
        if request.expected_revision!=run.revision: raise CollectionConflict('collection changed; refresh revision')
        now=m.utc_now()
        if run.status!='open' or now>=run.protocol.registration.outcome_cutoff: raise CollectionConflict('observation window closed')
        if not any(d.operational_alert_ref==request.operational_alert_ref for d in decisions(conn,ref)):
            raise CollectionConflict('record a collection decision before measuring its task')
        from packages.detection.selective_review import read_review
        view=read_review(conn,request.operational_alert_ref)
        observation=RecordedObservation(request=request,actor_id=actor_id,available_at=now,recalled=view.recalled,reason_codes=view.reason_codes)
        conn.execute('INSERT INTO prospective_observations (run_id,actor_id,request_id,request_payload,snapshot,created_at) VALUES (?,?,?,?,?,?)',
            (row['id'],actor_id,str(request.request_id),payload,observation.model_dump_json(by_alias=True),db.format_timestamp(now)))
        result=read_run(conn,ref); conn.commit(); return result
    except Exception:
        conn.rollback(); raise


def decisions(conn,ref):
    return [RecordedDecision.model_validate_json(r[0]) for r in conn.execute('SELECT snapshot FROM prospective_decisions WHERE run_id=? ORDER BY id',(_row(conn,ref)['id'],))]
