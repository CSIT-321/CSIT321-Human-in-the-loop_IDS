"""Separate immutable attention decisions; live validation can revoke but never grant deferral."""
from hashlib import sha256
import json
from uuid import UUID,uuid4
from typing import Literal
from pydantic import Field, model_validator
from packages.contracts import db,models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.adapters.operational_v2 import read_projection,read_triage
from packages.detection.triage_memory import MemoryCommand,lookup_memory
from packages.detection.triage_policy import TriageContext
from packages.detection.context_store import resolved_for
from packages.detection.trusted_context import ResolvedTrustedContext
from packages.detection.selective_review_policy import (
    Disposition,SelectivePolicy,SelectiveResult,ReviewInputs,load_policy,evaluate_review,
)


class ReviewConflict(ValueError):
    pass


class ReviewCommand(MemoryCommand):
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    collection_run_ref: UUID | None = None
    expected_run_revision: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode='after')
    def collection_identity(self):
        if (self.collection_run_ref is None)!=(self.expected_run_revision is None):
            raise ValueError('collection run and revision must be supplied together')
        return self


class ReviewSnapshot(V2Contract):
    inputs: ReviewInputs
    policy_config_snapshot: SelectivePolicy
    result: SelectiveResult
    input_version: str
    context_provenance: ResolvedTrustedContext | None = None


class CollectionRecording(V2Contract):
    run_ref: UUID
    status: Literal['recorded','not_recorded']
    decision_ref: UUID | None = None
    reason: str | None = None

    @model_validator(mode='after')
    def receipt(self):
        if self.status=='recorded' and (self.decision_ref is None or self.reason is not None):
            raise ValueError('recorded collection receipt requires its decision identity')
        if self.status=='not_recorded' and (self.decision_ref is not None or not self.reason):
            raise ValueError('skipped collection receipt requires its reason')
        return self


class ReviewEvent(V2Contract):
    id: int
    event_ref: UUID
    actor_id: int
    action: str
    reason: str
    event_type: str
    created_at: str
    snapshot: ReviewSnapshot
    collection_recording: CollectionRecording | None = None


class ReviewView(V2Contract):
    operational_alert_ref: UUID
    title: str
    version: str
    disposition: Disposition
    reason_codes: list[str]
    explanation: str
    priority: float | None
    route: str
    policy_evaluation: ReviewSnapshot
    last_decision: ReviewEvent | None
    human_override: bool
    eligible_alert: bool
    recalled: bool


class ReviewMutation(V2Contract):
    view: ReviewView
    replayed: bool


class EffectiveReview(V2Contract):
    """Current attention projection, separate from immutable/persisted routing facts."""
    disposition: Disposition
    review_required: bool
    reason_codes: list[str]
    explanation: str
    recalled: bool
    version: str


def effective_review(conn, ref):
    # read_review is the single authority for persisted decisions, live guardrails,
    # expiry, conflicts and human recall. Never copy its policy into queue SQL.
    view = read_review(conn, ref)
    return EffectiveReview(disposition=view.disposition, review_required=view.disposition != 'no_immediate_review',
        reason_codes=view.reason_codes, explanation=view.explanation, recalled=view.recalled, version=view.version)


class ReviewMetrics(V2Contract):
    total_alerts: int
    eligible_alerts: int
    must_review_count: int
    recommended_review_count: int
    no_immediate_review_count: int
    immediate_review_reduction_rate: float
    unsafe_suppression_count: int
    conflict_triggered_recall_count: int
    sampled_override_count: int
    data_basis: str = 'Observed local decisions and human outcomes; not a measured real-world workload benefit.'


def _json(value):
    return json.dumps(value,sort_keys=True,allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode()).hexdigest()


def _id(conn,ref):
    row=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(ref),)).fetchone()
    if row is None:raise LookupError('Operational alert not found')
    return row[0]


def _event(row):
    return ReviewEvent(id=row['id'],event_ref=row['event_ref'],actor_id=row['actor_id'],action=row['action'],
        reason=row['reason'],event_type=row['event_type'],created_at=row['created_at'],
        snapshot=ReviewSnapshot.model_validate_json(row['decision_snapshot']),
        collection_recording=json.loads(row['request_payload']).get('collectionRecording')) if row else None


def current_snapshot(conn,ref):
    aid=_id(conn,ref)
    alert=read_projection(conn,aid)
    triage=read_triage(conn,aid)
    now=m.utc_now()
    provenance=resolved_for(conn,ref,now)
    context=provenance.context
    trusted=[field for field in provenance.fields if field.status=='trusted']
    context_ids=[fact.id for field in trusted for fact in field.facts if fact.id is not None]
    matches=[];offset=0
    while True:
        page,total=lookup_memory(conn,ref,200,offset)
        matches.extend(page);offset+=len(page)
        if offset>=total or not page:break
    override=conn.execute("SELECT 1 FROM selective_review_events WHERE operational_alert_id=? AND action='require_review' LIMIT 1",(aid,)).fetchone() is not None
    reviewed=conn.execute('SELECT 1 FROM triage_memory_support_events WHERE source_alert_id=? LIMIT 1',(aid,)).fetchone() is not None
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='verdict_memory_contributions'").fetchone():
        reviewed=reviewed or conn.execute('SELECT 1 FROM verdict_memory_contributions WHERE source_alert_id=? LIMIT 1',(aid,)).fetchone() is not None
    reviewed=reviewed or conn.execute("SELECT 1 FROM tier2_cases c JOIN tier2_case_events e ON e.case_id=c.id WHERE c.primary_operational_alert_id=? AND e.action='finding' LIMIT 1",(aid,)).fetchone() is not None
    inputs=ReviewInputs(alert=alert,triage=triage,context=context,context_audit_id=max(context_ids,default=None),
        context_recorded_at=min((field.available_at for field in trusted),default=None),matches=matches,human_override=override,human_verdict_present=reviewed)
    policy=load_policy()
    result=evaluate_review(inputs,policy,now)
    version=_hash(dict(inputs=inputs.model_dump(mode='json'),policy=policy.model_dump(mode='json'),result=result.model_dump(mode='json'),
        provenance=provenance.model_dump(mode='json',exclude={'evaluated_at'})))
    return ReviewSnapshot(inputs=inputs,policy_config_snapshot=policy,result=result,input_version=version,context_provenance=provenance)


def read_review(conn,ref):
    snapshot=current_snapshot(conn,ref)
    aid=snapshot.inputs.alert.id
    last=_event(conn.execute('SELECT * FROM selective_review_events WHERE operational_alert_id=? ORDER BY id DESC LIMIT 1',(aid,)).fetchone())
    result=snapshot.result
    disposition=result.disposition
    codes=result.reason_codes
    explanation=result.explanation
    if snapshot.inputs.human_override:
        disposition='must_review';codes=['HUMAN_REVIEW_OVERRIDE']
        explanation='Authenticated human override remains in force; Tier 1 review is required.'
    elif last is None:
        disposition='must_review';codes=['NO_PERSISTED_REVIEW_DECISION',*codes]
        explanation='Must Review until an explicit policy evaluation is recorded. '+explanation
    elif last.snapshot.input_version!=snapshot.input_version:
        disposition='must_review';codes=['CHANGED_EVIDENCE_REQUIRES_REVIEW',*codes]
        explanation='Stored decision is historical; changed evidence invalidates deferral. '+explanation
    elif last.action=='require_review':
        disposition='must_review';codes=['HUMAN_REVIEW_OVERRIDE']
        explanation='An authenticated human required review: '+last.reason
    recalled=bool(last and last.snapshot.result.disposition=='no_immediate_review' and disposition!='no_immediate_review')
    return ReviewView(operational_alert_ref=ref,title=snapshot.inputs.alert.detection_title,
        version=_hash(dict(input=snapshot.input_version,last=last.id if last else None)),disposition=disposition,
        reason_codes=list(dict.fromkeys(codes)),explanation=explanation,priority=snapshot.inputs.triage.operational_priority,
        route=snapshot.inputs.triage.handling_route,policy_evaluation=snapshot,last_decision=last,
        human_override=snapshot.inputs.human_override,eligible_alert=(snapshot.inputs.triage.handling_route,snapshot.inputs.triage.workflow_stage)==('tier1_review','triage'),recalled=recalled)


def decide_review(conn,ref,*,actor_id,action,request:ReviewCommand):
    request=ReviewCommand.model_validate(request.model_dump())
    if action not in ('apply','require_review'):raise ValueError('unsupported review action')
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:raise ValueError('foreign keys and no transaction required')
    excluded={'collection_run_ref','expected_run_revision'} if request.collection_run_ref is None else set()
    payload=_json(dict(alertRef=str(ref),action=action,request=request.model_dump(mode='json',exclude=excluded)))
    conn.execute('BEGIN IMMEDIATE')
    try:
        actor=db.get(conn,m.User,actor_id)
        if actor is None or actor.status!='active' or actor.role not in ('security_analyst','system_admin'):
            raise PermissionError('active analyst or administrator required')
        retry=conn.execute('SELECT * FROM selective_review_events WHERE request_id=?',(str(request.request_id),)).fetchone()
        current=read_review(conn,ref)
        if retry:
            original=json.loads(retry['request_payload'])
            original.pop('collectionRecording',None)
            if retry['actor_id']!=actor_id or _json(original)!=payload:raise ReviewConflict('requestId belongs to another review decision')
            conn.commit();return ReviewMutation(view=current,replayed=True)
        if current.version!=request.expected_version:raise ReviewConflict('review evidence changed; refresh before deciding')
        snapshot=current.policy_evaluation
        if action=='require_review':
            if not current.eligible_alert:raise ReviewConflict('cannot overwrite an advanced or unassigned workflow')
            snapshot=snapshot.model_copy(update={'result':SelectiveResult(disposition='must_review',reason_codes=['HUMAN_REVIEW_OVERRIDE'],
                explanation='Authenticated human requires Tier 1 review: '+request.reason,matched_lesson_ref=None,policy_version=snapshot.result.policy_version,decision_source='human_override')})
        old=conn.execute("SELECT decision_snapshot FROM selective_review_events WHERE json_extract(decision_snapshot,'$.policyConfigSnapshot.version')=? LIMIT 1",(snapshot.policy_config_snapshot.version,)).fetchone()
        if old and ReviewSnapshot.model_validate_json(old[0]).policy_config_snapshot!=snapshot.policy_config_snapshot:
            raise ReviewConflict('changed configuration requires a new policy version')
        decision_at=snapshot.context_provenance.evaluated_at
        pending=None
        if request.collection_run_ref is not None:
            from packages.detection.prospective_collection import prepare_decision, persist_decision, CollectionConflict
            try:
                pending=prepare_decision(conn,request.collection_run_ref,request.expected_run_revision,actor_id,action,snapshot,decision_at)
            except (CollectionConflict,LookupError) as exc:
                if action!='require_review': raise
                recording=CollectionRecording(run_ref=request.collection_run_ref,status='not_recorded',reason=str(exc))
            else:
                recording=CollectionRecording(run_ref=request.collection_run_ref,status='recorded',decision_ref=pending.decision_ref)
            payload=_json({**json.loads(payload),'collectionRecording':recording.model_dump(mode='json',by_alias=True)})
        event=conn.execute('INSERT INTO selective_review_events (event_ref,operational_alert_id,actor_id,action,reason,request_id,request_payload,decision_snapshot,event_type,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (str(uuid4()),snapshot.inputs.alert.id,actor_id,action,request.reason,str(request.request_id),payload,snapshot.model_dump_json(by_alias=True),
             'V2_HUMAN_REVIEW_REQUIRED' if action=='require_review' else 'V2_SELECTIVE_REVIEW_DECIDED',db.format_timestamp(decision_at)))
        if pending is not None:
            persist_decision(conn,pending,event.lastrowid)
        result=ReviewMutation(view=read_review(conn,ref),replayed=False)
        conn.commit();return result
    except Exception:
        conn.rollback();raise


def review_history(conn,ref,limit,offset):
    aid=_id(conn,ref)
    total=conn.execute('SELECT count(*) FROM selective_review_events WHERE operational_alert_id=?',(aid,)).fetchone()[0]
    rows=conn.execute('SELECT * FROM selective_review_events WHERE operational_alert_id=? ORDER BY id DESC LIMIT ? OFFSET ?',(aid,limit,offset)).fetchall()
    return [_event(row) for row in rows],total


def all_reviews(conn):
    return [read_review(conn,row[0]) for row in conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2 ORDER BY id').fetchall()]


def list_reviews(conn,disposition,limit,offset):
    items=[view for view in all_reviews(conn) if disposition is None or view.disposition==disposition]
    return items[offset:offset+limit],len(items)


def review_metrics(conn):
    views=all_reviews(conn)
    counts={kind:sum(v.disposition==kind for v in views) for kind in ('must_review','recommended_review','no_immediate_review')}
    eligible=sum(v.eligible_alert for v in views)
    unsafe=conn.execute("SELECT count(DISTINCT s.operational_alert_id) FROM selective_review_events s WHERE "
        "json_extract(s.decision_snapshot,'$.result.disposition')='no_immediate_review' AND ("
        "EXISTS(SELECT 1 FROM triage_memory_support_events e WHERE e.source_alert_id=s.operational_alert_id AND e.is_primary=1 AND e.outcome IN ('confirmed_malicious','suspicious') AND e.created_at>s.created_at) OR "
        "EXISTS(SELECT 1 FROM tier2_cases c JOIN tier2_case_events e ON e.case_id=c.id WHERE c.primary_operational_alert_id=s.operational_alert_id AND e.finding IN ('confirmed_malicious','suspicious') AND e.created_at>s.created_at))").fetchone()[0]
    return ReviewMetrics(total_alerts=len(views),eligible_alerts=eligible,must_review_count=counts['must_review'],
        recommended_review_count=counts['recommended_review'],no_immediate_review_count=counts['no_immediate_review'],
        immediate_review_reduction_rate=counts['no_immediate_review']/eligible if eligible else 0,unsafe_suppression_count=unsafe,
        conflict_triggered_recall_count=sum(v.recalled and 'MEMORY_CONFLICT' in v.reason_codes for v in views),
        sampled_override_count=sum(v.disposition=='recommended_review' and 'DETERMINISTIC_AUDIT_SAMPLE' in v.reason_codes for v in views))
