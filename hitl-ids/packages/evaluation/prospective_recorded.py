"""Read-only evaluation of actual recorded decisions, never a reconstructed counterfactual."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field
from packages.contracts import models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.prospective_collection import (
    RunView, RecordedDecision, RecordedObservation, read_run, decisions, digest,
)
from packages.evaluation.temporal_review import OutcomeEvent


class RecordedArchive(V2Contract):
    evaluation_mode: Literal['prospective_recorded'] = 'prospective_recorded'
    run: RunView
    decisions: list[RecordedDecision]
    outcomes: list[OutcomeEvent]
    observations: list[RecordedObservation]
    review_events: list[dict[str, Any]]
    admission_routing_events: list[dict[str, Any]]
    run_events: list[dict[str, Any]]
    unrelated_history: dict[str, Any] = Field(default_factory=dict)


def export_connection(conn,ref):
    """Read SELECTs only, under the caller's consistent read transaction."""
    run=read_run(conn,ref)
    run_id=conn.execute('SELECT id FROM prospective_runs WHERE run_ref=?',(str(ref),)).fetchone()[0]
    refs={r['id']:r['operational_alert_ref'] for r in conn.execute('SELECT id,operational_alert_ref FROM operational_alerts_v2')}
    outcomes=[]
    for r in conn.execute('SELECT * FROM triage_memory_support_events WHERE is_primary=1 ORDER BY id'):
        outcomes.append(OutcomeEvent(event_id='memory:'+str(r['id']),alert_ref=refs[r['source_alert_id']],available_at=r['created_at'],outcome=r['outcome']))
    for r in conn.execute("SELECT e.*,c.primary_operational_alert_id FROM tier2_case_events e JOIN tier2_cases c ON c.id=e.case_id WHERE e.action='finding' ORDER BY e.id"):
        outcomes.append(OutcomeEvent(event_id='case:'+str(r['id']),alert_ref=refs[r['primary_operational_alert_id']],available_at=r['created_at'],outcome=r['finding']))
    events=[{**dict(r),'alertRef':refs[r['operational_alert_id']]} for r in conn.execute('SELECT * FROM selective_review_events ORDER BY id')]
    routing=[{**dict(r),'alertRef':refs[r['operational_alert_id']]} for r in conn.execute('SELECT * FROM operational_routing_audit ORDER BY id')]
    return RecordedArchive(run=run,decisions=decisions(conn,ref),outcomes=outcomes,
        observations=[RecordedObservation.model_validate_json(r[0]) for r in conn.execute('SELECT snapshot FROM prospective_observations WHERE run_id=? ORDER BY id',(run_id,))],
        review_events=events,admission_routing_events=routing,
        run_events=[dict(r) for r in conn.execute('SELECT * FROM prospective_run_events WHERE run_id=? ORDER BY id',(run_id,))],
        unrelated_history={'contextFacts':[json.loads(r[0]) for r in conn.execute('SELECT snapshot FROM trusted_context_facts ORDER BY id')]})


def load_recorded_database(path,ref):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return export_connection(conn,ref)


def _time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value


def evaluate_recorded(archive: RecordedArchive, *, now=None):
    if not isinstance(archive,RecordedArchive): raise ValueError('registered evaluation rejects reconstructed-only data')
    archive=RecordedArchive.model_validate(archive.model_dump())
    run=archive.run; protocol=run.protocol; plan=protocol.registration
    if run.status not in ('closed','evaluated') or run.closed_at is None or plan.outcome_cutoff is None:
        raise ValueError('registered evaluation requires a closed collection run')
    if (now or m.utc_now())<plan.outcome_cutoff or run.closed_at<plan.outcome_cutoff:
        raise ValueError('outcome cutoff has not closed')
    if run.opened_at is None or not protocol.registered_at<=run.opened_at<plan.holdout_start<plan.holdout_end<=plan.outcome_cutoff:
        raise ValueError('invalid registration/opening chronology')
    if not plan.readiness_review_reference: raise ValueError('missing readiness review approval reference')
    for action,at,actor in (('open',run.opened_at,run.opened_by_actor_id),('close',run.closed_at,run.closed_by_actor_id)):
        events=[e for e in archive.run_events if e['action']==action]
        if len(events)!=1 or _time(events[0]['created_at'])!=at or events[0]['actor_id']!=actor:
            raise ValueError('persisted run lifecycle evidence is missing or inconsistent')
    if plan.evidence_basis!='synthetic/demo' and not protocol.source_tree_clean:
        raise ValueError('non-synthetic registration requires verified committed source')
    if run.protocol_hash!=digest(protocol.model_dump(mode='json',by_alias=True)):
        raise ValueError('frozen protocol hash mismatch')
    if protocol.selective_policy_hash!=digest(protocol.selective_policy.model_dump(mode='json',by_alias=True)) or protocol.context_policy_hash!=digest(protocol.context_policy.model_dump(mode='json',by_alias=True)):
        raise ValueError('frozen configuration hash mismatch')
    selected=sorted((d for d in archive.decisions if plan.holdout_start<=d.decision_at<plan.holdout_end),key=lambda d:(d.decision_at,d.review_event_id))
    if len({d.decision_ref for d in selected})!=len(selected) or len({d.review_event_id for d in selected})!=len(selected):
        raise ValueError('duplicate recorded decision')
    review_events={e['id']:e for e in archive.review_events}
    admission_evidence=[]
    for decision in selected:
        s=decision.snapshot; provenance=s.context_provenance
        if decision.run_ref!=run.run_ref or decision.run_protocol_hash!=run.protocol_hash:
            raise ValueError('decision does not belong to frozen protocol')
        if decision.policy_hash!=protocol.selective_policy_hash or s.policy_config_snapshot!=protocol.selective_policy:
            raise ValueError('referenced in-window policy differs from frozen protocol')
        if digest(s.model_dump(mode='json',by_alias=True))!=decision.input_fingerprint:
            raise ValueError('recorded decision fingerprint mismatch')
        if decision.operational_alert_ref!=s.inputs.alert.operational_alert_ref or decision.alert_occurred_at!=_time(s.inputs.alert.occurred_at):
            raise ValueError('recorded alert identity/occurrence mismatch')
        if not decision.operational_admitted_at<=decision.review_eligible_at<=decision.decision_at or not decision.availability_boundary or max(decision.availability_boundary.values())!=decision.review_eligible_at:
            raise ValueError('recorded readiness chronology mismatch')
        admissions=[e for e in archive.admission_routing_events if e['alertRef']==str(decision.operational_alert_ref) and e['action']=='admit_tier1' and _time(e['created_at'])==decision.operational_admitted_at]
        if len(admissions)!=1: raise ValueError('persisted operational admission evidence missing')
        if admissions[0] not in admission_evidence: admission_evidence.append(admissions[0])
        if provenance is None or provenance.evaluated_at!=decision.decision_at:
            raise ValueError('recorded decision-time provenance required')
        for field in provenance.fields:
            for fact in field.facts:
                if fact.freshness_policy!=protocol.context_policy: raise ValueError('referenced context policy differs from protocol')
                if max(fact.available_at,fact.recorded_at,fact.valid_from)>decision.decision_at:
                    raise ValueError('future fact referenced by an earlier recorded decision')
        event=review_events.get(decision.review_event_id)
        if event is None or event['alertRef']!=str(decision.operational_alert_ref) or event['operational_alert_id']!=s.inputs.alert.id or _time(event['created_at'])!=decision.decision_at or event['actor_id']!=decision.actor_id or event['action']!=decision.action or json.loads(event['decision_snapshot'])!=s.model_dump(mode='json',by_alias=True):
            raise ValueError('actual persisted review event does not match collection snapshot')
    # Freeze only the relevant window, not the entire mutable-length export archive.
    by_alert={}
    for decision in selected:
        inputs=decision.snapshot.inputs
        eligible=(inputs.triage.handling_route,inputs.triage.workflow_stage)==('tier1_review','triage') and not inputs.human_verdict_present
        if decision.action=='apply' and eligible: by_alert.setdefault(decision.operational_alert_ref,decision)
    rows=[]; scoped_outcomes=[]; scoped_observations=[]; scoped_events=[]
    for ref,decision in by_alert.items():
        truth=sorted((e for e in archive.outcomes if e.alert_ref==ref and decision.decision_at<e.available_at<plan.outcome_cutoff),key=lambda e:(e.available_at,e.event_id))
        malicious=[e for e in truth if e.outcome in ('confirmed_malicious','suspicious')]
        outcome=malicious[0] if malicious else truth[-1] if truth else None
        observations=[e for e in archive.observations if e.request.operational_alert_ref==ref and decision.decision_at<=e.available_at<plan.outcome_cutoff]
        overrides=[e for e in archive.review_events if e['alertRef']==str(ref) and e['action']=='require_review' and decision.decision_at<_time(e['created_at'])<plan.outcome_cutoff]
        scoped_outcomes.extend(truth); scoped_observations.extend(observations); scoped_events.extend(overrides)
        deferred=decision.snapshot.result.disposition=='no_immediate_review'
        rows.append(dict(decisionRef=str(decision.decision_ref),alertRef=str(ref),alertOccurredAt=decision.alert_occurred_at.isoformat(),
            operationalAdmittedAt=decision.operational_admitted_at.isoformat(),reviewEligibleAt=decision.review_eligible_at.isoformat(),decisionAt=decision.decision_at.isoformat(),
            disposition=decision.snapshot.result.disposition,outcomeAt=outcome.available_at.isoformat() if outcome else None,
            laterHumanOutcome=outcome.outcome if outcome else None,outcomeStatus='completed' if outcome and outcome.outcome!='inconclusive' else 'pending_or_inconclusive',
            unsafeDeferral=deferred and bool(malicious),safelyDeferred=deferred and bool(outcome and outcome.outcome in ('expected_activity','false_positive')),
            recalled=deferred and (bool(overrides) or any(e.recalled for e in observations)),
            completeTrustedContext=decision.snapshot.context_provenance.complete,
            detectorSource=decision.snapshot.inputs.alert.detector_source,detectionCategory=decision.snapshot.inputs.alert.detection_category,
            priorityBand=decision.snapshot.inputs.triage.priority_band))
    total=len(rows); deferred=sum(r['disposition']=='no_immediate_review' for r in rows)
    labelled=sum(r['outcomeStatus']=='completed' for r in rows)
    labelled_deferred=sum(r['disposition']=='no_immediate_review' and r['outcomeStatus']=='completed' for r in rows)
    unsafe=sum(r['unsafeDeferral'] for r in rows)
    measurements=[o for o in scoped_observations if o.request.analyst_review_seconds is not None or o.request.total_task_seconds is not None]
    scope=dict(protocol=protocol.model_dump(mode='json',by_alias=True),runRef=str(run.run_ref),openedAt=run.opened_at.isoformat(),closedAt=run.closed_at.isoformat(),
        openedByActorId=run.opened_by_actor_id,closedByActorId=run.closed_by_actor_id,
        decisions=[d.model_dump(mode='json',by_alias=True) for d in selected],outcomes=[e.model_dump(mode='json',by_alias=True) for e in scoped_outcomes],
        observations=[e.model_dump(mode='json',by_alias=True) for e in scoped_observations],overrides=scoped_events,admissions=admission_evidence)
    return dict(evaluationMode='prospective_recorded',evidenceBasis=plan.evidence_basis,
        evidenceWarning='Synthetic/demo collection, not production evidence.' if plan.evidence_basis=='synthetic/demo' else 'Historical inputs require independent provenance validation; not proof of production safety.',
        runRef=str(run.run_ref),protocolVersion=plan.protocol_version,protocolHash=run.protocol_hash,codeCommitSha=protocol.code_commit_sha,
        inputSha256=digest(scope),frozenInputs=scope,cohortRule='First eligible applied decision per alert; later evaluations/overrides retained separately.',
        persistedDecisionCount=len(selected),eligibleAlerts=total,baselineImmediateReviews=total,selectiveImmediateReviews=total-deferred,
        deferredAlerts=deferred,reviewVolumeReductionRate=deferred/total if total else 0,
        unsafeDeferrals=unsafe,unsafeDeferralRate=unsafe/labelled_deferred if labelled_deferred else None,
        safelyDeferredAlerts=sum(r['safelyDeferred'] for r in rows),recalls=sum(r['recalled'] for r in rows),
        contextCoverage=sum(r['completeTrustedContext'] for r in rows)/total if total else 0,
        outcomeCompleteness=labelled/total if total else 0,targetsMet=total>=plan.minimum_eligible_alerts and bool(total and labelled/total>=plan.minimum_outcome_completeness),
        workload=dict(measurementCount=len(measurements),analystReviewSeconds=sum(o.request.analyst_review_seconds for o in measurements if o.request.analyst_review_seconds is not None) if any(o.request.analyst_review_seconds is not None for o in measurements) else None,
            totalTaskSeconds=sum(o.request.total_task_seconds for o in measurements if o.request.total_task_seconds is not None) if any(o.request.total_task_seconds is not None for o in measurements) else None,
            errors=sum(o.request.errors for o in scoped_observations),rework=sum(o.request.rework for o in scoped_observations),measuredAnalystTimeReduction=None,
            interpretation='Human-reported stopwatch durations. No paired time baseline: review-volume reduction is not measured time reduction.'),
        decisions=rows,limitations=['First eligible applied decision defines the alert cohort.', 'Outcomes at or after outcomeCutoff are excluded.',
            'Read-only snapshot evaluation; no current policy reconstruction.', 'Registration approval references require independent human verification.'])


def render_recorded_markdown(report):
    protocol=report['frozenInputs']['protocol'];plan=protocol['registration']
    lines=['# Prospective Recorded Collection', '', report['evidenceWarning'], '',
        'Mode: prospective_recorded (temporal holdout)', 'Run: '+report['runRef'], 'Protocol: '+report['protocolVersion'],
        f"Decision window: [{plan['holdoutStart']}, {plan['holdoutEnd']})",'Outcome cutoff (exclusive): '+plan['outcomeCutoff'],
        'Participant classification: '+plan['participantClass'],'Code commit: '+report['codeCommitSha'],
        'Protocol SHA-256: '+report['protocolHash'],
        'Input SHA-256: '+report['inputSha256'], '', '| Metric | Value |','| --- | --- |']
    keys=('persistedDecisionCount','eligibleAlerts','baselineImmediateReviews','selectiveImmediateReviews','deferredAlerts','reviewVolumeReductionRate','unsafeDeferrals','unsafeDeferralRate','safelyDeferredAlerts','recalls','contextCoverage','outcomeCompleteness','targetsMet')
    lines += [f'| {key} | {report[key]} |' for key in keys]
    lines += ['', '## Workload measurements', '```json',json.dumps(report['workload'],indent=2),'```','',*report['limitations']]
    return '\n'.join(lines)+'\n'
