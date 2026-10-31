"""Offline event-time holdout. Never reads today's aggregate memory or writes application state."""
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from packages.contracts.operational_v2 import OperationalAlertV2, OperationalTriageStateV2, V2Contract
from packages.detection.selective_review_policy import ReviewInputs, SelectivePolicy, evaluate_review
from packages.detection.triage_memory import MemoryDecision, MemoryLesson, MemoryView, Outcome, context_for, explain_match
from packages.detection.triage_policy import TriageContext
from packages.detection.trusted_context import TrustedContextFact, resolve_context


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if result.tzinfo is None:
        raise ValueError('historical timestamps require an explicit timezone')
    return result


class PolicyPeriod(V2Contract):
    effective_at: AwareDatetime
    available_at: AwareDatetime
    configuration: SelectivePolicy


class StateObservation(V2Contract):
    alert_ref: UUID
    available_at: AwareDatetime
    state: OperationalTriageStateV2


class ContextObservation(V2Contract):
    alert_ref: UUID
    available_at: AwareDatetime
    audit_id: int = Field(gt=0)
    context: TriageContext


class SupportEvent(V2Contract):
    event_id: str
    lesson_ref: UUID
    alert_ref: UUID
    available_at: AwareDatetime
    outcome: Outcome
    relation: Literal['support', 'conflict']


class ActivationEvent(V2Contract):
    lesson_ref: UUID
    available_at: AwareDatetime
    action: Literal['activate', 'reject']
    actor_id: int
    reason: str
    valid_from: AwareDatetime | None
    expires_at: AwareDatetime | None


class OutcomeEvent(V2Contract):
    event_id: str
    alert_ref: UUID
    available_at: AwareDatetime
    outcome: Literal['expected_activity', 'false_positive', 'confirmed_malicious', 'suspicious', 'inconclusive']


class OverrideEvent(V2Contract):
    alert_ref: UUID
    available_at: AwareDatetime


class TemporalArchive(V2Contract):
    format_version: Literal['temporal-review-v1'] = 'temporal-review-v1'
    data_basis: Literal['synthetic/demo', 'historical-inputs-unverified']
    provenance: str = Field(min_length=1)
    holdout_start: AwareDatetime
    holdout_end: AwareDatetime
    alerts: list[OperationalAlertV2]
    states: list[StateObservation]
    contexts: list[ContextObservation]
    policies: list[PolicyPeriod]
    lessons: list[MemoryLesson]
    supports: list[SupportEvent]
    activations: list[ActivationEvent]
    outcomes: list[OutcomeEvent]
    overrides: list[OverrideEvent] = Field(default_factory=list)
    context_facts: list[TrustedContextFact] | None = None

    @model_validator(mode='after')
    def coherent_history(self):
        if self.holdout_start >= self.holdout_end:
            raise ValueError('holdout must be a nonempty [start, end) interval')
        alerts = {a.operational_alert_ref: a for a in self.alerts}
        lessons = {m.lesson_ref: m for m in self.lessons}
        if len(alerts) != len(self.alerts) or len(lessons) != len(self.lessons):
            raise ValueError('duplicate alert or lesson identity')
        for alert in self.alerts:
            timestamp(alert.occurred_at)
        if self.context_facts is not None and len({f.fact_ref for f in self.context_facts})!=len(self.context_facts):
            raise ValueError('duplicate context fact reference')
        for lesson in self.lessons:
            if lesson.source_operational_alert_ref not in alerts:
                raise ValueError('lesson source alert is missing')
            if timestamp(lesson.created_at) < timestamp(alerts[lesson.source_operational_alert_ref].occurred_at):
                raise ValueError('lesson predates its source alert')
        for group in (self.states, self.contexts, self.supports, self.outcomes, self.overrides):
            for event in group:
                if event.alert_ref not in alerts:
                    raise ValueError('event references an unknown alert')
        for group in (self.states, self.contexts):
            identities = [(e.alert_ref, e.available_at) for e in group]
            if len(set(identities)) != len(identities):
                raise ValueError('ambiguous same-time observations')
        for event in self.states:
            alert = alerts[event.alert_ref]
            if event.state.updated_at > event.available_at:
                raise ValueError('state contains a future update')
            if alert.id is not None and event.state.operational_alert_id != alert.id:
                raise ValueError('state belongs to another alert')
        for group in (self.supports, self.outcomes):
            if len({e.event_id for e in group}) != len(group):
                raise ValueError('duplicate event identity')
            for event in group:
                if event.available_at < timestamp(alerts[event.alert_ref].occurred_at):
                    raise ValueError('review predates source alert')
        if len({(e.lesson_ref, e.alert_ref) for e in self.supports}) != len(self.supports):
            raise ValueError('duplicate lesson support from the same alert')
        for event in self.supports:
            lesson = lessons.get(event.lesson_ref)
            if lesson is None or event.available_at < timestamp(lesson.created_at):
                raise ValueError('support predates or references a missing lesson')
            if (event.outcome == lesson.outcome) != (event.relation == 'support'):
                raise ValueError('support relation disagrees with human outcome')
        if len({e.lesson_ref for e in self.activations}) != len(self.activations):
            raise ValueError('duplicate immutable activation decision')
        for event in self.activations:
            lesson = lessons.get(event.lesson_ref)
            if lesson is None or event.available_at < timestamp(lesson.created_at):
                raise ValueError('activation predates or references a missing lesson')
            if event.action == 'activate':
                if event.valid_from is None or event.expires_at is None or not event.available_at <= event.valid_from < event.expires_at:
                    raise ValueError('activation validity cannot be backdated')
                prior = [e for e in self.supports if e.lesson_ref == event.lesson_ref and e.available_at < event.available_at]
                support = sum(e.relation == 'support' for e in prior)
                conflicts = len(prior) - support
                if support < lesson.configuration.minimum_support or conflicts or support / len(prior) < lesson.configuration.minimum_agreement_ratio:
                    raise ValueError('activation lacks strictly earlier qualifying reviews')
        versions = {}
        effective = set()
        for period in self.policies:
            if period.effective_at in effective:
                raise ValueError('ambiguous policy effective time')
            effective.add(period.effective_at)
            config = period.configuration.model_dump_json()
            version = period.configuration.version
            if version in versions and versions[version] != config:
                raise ValueError('changed configuration reuses a policy version')
            versions[version] = config
        return self


def memory_at(archive, at):
    """Reconstruct from raw events strictly before at, never from final/audit aggregate snapshots."""
    result = []
    for lesson in sorted(archive.lessons, key=lambda m: str(m.lesson_ref)):
        if timestamp(lesson.created_at) >= at:
            continue
        events = [e for e in archive.supports if e.lesson_ref == lesson.lesson_ref and e.available_at < at]
        support = [e for e in events if e.relation == 'support']
        conflicts = [e for e in events if e.relation == 'conflict']
        ratio = len(support) / len(events) if events else 0
        config = lesson.configuration
        status = 'eligible_for_activation' if len(support) >= config.minimum_support and ratio >= config.minimum_agreement_ratio and not conflicts else 'candidate'
        valid = None
        expires = timestamp(lesson.created_at) + timedelta(days=config.default_validity_days)
        if at >= expires:
            status = 'expired'
        decision = next((e for e in archive.activations if e.lesson_ref == lesson.lesson_ref and e.available_at < at), None)
        if decision:
            if decision.action == 'reject':
                status = 'rejected'
            else:
                valid, expires = decision.valid_from, decision.expires_at
                status = 'conflict_review' if conflicts else 'expired' if at >= expires else 'active' if valid < at else 'eligible_for_activation'
        result.append(MemoryView(lesson=lesson, status=status, revision=len(events) + bool(decision),
            support_count=len(support), conflict_count=len(conflicts), agreement_ratio=ratio,
            valid_from=valid, expires_at=expires,
            last_supported_at=max((e.available_at for e in support), default=timestamp(lesson.created_at)).isoformat(),
            last_conflict_at=max(e.available_at for e in conflicts).isoformat() if conflicts else None,
            decision=MemoryDecision(action=decision.action, actor_id=decision.actor_id, reason=decision.reason,
                created_at=decision.available_at.isoformat()) if decision else None))
    return result


def related_matches(memories, alert):
    context = context_for(alert)
    return [explain_match(m, context) for m in memories
        if m.lesson.context_snapshot.detector_source == context.detector_source and
        (m.lesson.context_snapshot.detection_title == context.detection_title or
         (context.detection_category is not None and m.lesson.context_snapshot.detection_category == context.detection_category))]


def _latest(events, at):
    return max((e for e in events if e.available_at <= at), key=lambda e: e.available_at, default=None)


def _metrics(rows):
    eligible = [r for r in rows if r['eligible']]
    deferred = [r for r in eligible if r['disposition'] == 'no_immediate_review']
    labelled = [r for r in deferred if r['laterOutcome'] not in (None, 'inconclusive')]
    unsafe = sum(r['laterOutcome'] in ('confirmed_malicious', 'suspicious') for r in deferred)
    safe = sum(r['laterOutcome'] in ('expected_activity', 'false_positive') for r in deferred)
    count = len(eligible)
    unknown = sum('UNKNOWN_REQUIRED_CONTEXT' in r['reasonCodes'] or 'MISSING_TRUSTED_CONTEXT' in r['reasonCodes'] for r in eligible)
    return dict(totalEligibleAlerts=count, baselineImmediateReviews=count,
        selectiveImmediateReviews=count-len(deferred), noImmediateReviewCount=len(deferred),
        workloadReductionRate=len(deferred)/count if count else 0,
        maliciousOrSuspiciousIncorrectlyDeferred=unsafe, expectedOrFalsePositiveSafelyDeferred=safe,
        unsafeDeferralRate=unsafe/len(labelled) if labelled else None,
        labelledDeferredAlerts=len(labelled), unlabelledOrInconclusiveDeferredAlerts=len(deferred)-len(labelled),
        conflictTriggeredRecalls=sum(r['recalledAt'] is not None for r in deferred),
        memoryCoverage=sum(r['memoryCoverage'] for r in eligible)/count if count else 0,
        activeLessonCoverage=sum(r['activeLessonCoverage'] for r in eligible)/count if count else 0,
        unknownSafetyContextBlockedCount=unknown,
        unknownSafetyContextBlockedPercent=100*unknown/count if count else 0)


def evaluate_temporal(archive: TemporalArchive):
    archive = TemporalArchive.model_validate(archive.model_dump())
    rows = []
    alerts = sorted(archive.alerts, key=lambda a: (timestamp(a.occurred_at), str(a.operational_alert_ref)))
    for alert in alerts:
        at = timestamp(alert.occurred_at)
        if not archive.holdout_start <= at < archive.holdout_end:
            continue
        ref = alert.operational_alert_ref
        state = _latest([e for e in archive.states if e.alert_ref == ref], at)
        context = _latest([e for e in archive.contexts if e.alert_ref == ref], at)
        provenance = resolve_context(alert,archive.context_facts,at) if archive.context_facts is not None else None
        trusted = [field for field in provenance.fields if field.status=='trusted'] if provenance else []
        period = max((p for p in archive.policies if p.available_at <= at and p.effective_at <= at),
            key=lambda p: p.effective_at, default=None)
        matches = related_matches(memory_at(archive, at), alert)
        eligible = state is not None and (state.state.handling_route, state.state.workflow_stage) == ('tier1_review', 'triage')
        inputs = None
        result = None
        if state is not None:
            inputs = ReviewInputs(alert=alert, triage=state.state, context=provenance.context if provenance else context.context if context else TriageContext(),
                context_audit_id=(max((fact.id or 1 for field in trusted for fact in field.facts),default=None) if provenance else context.audit_id if context else None),
                context_recorded_at=(min((field.available_at for field in trusted),default=None) if provenance else context.available_at if context else None),
                matches=matches, human_override=any(e.alert_ref == ref and e.available_at < at for e in archive.overrides),
                human_verdict_present=any(e.alert_ref == ref and e.available_at < at for e in [*archive.outcomes, *archive.supports]))
            if period:
                result = evaluate_review(inputs, period.configuration, at)
        reasons = result.reason_codes if result else ['MISSING_HISTORICAL_TRIAGE' if state is None else 'MISSING_HISTORICAL_POLICY']
        if inputs is not None and any(v is None for v in inputs.context.model_dump().values()) and 'UNKNOWN_REQUIRED_CONTEXT' not in reasons:
            reasons = [*reasons, 'UNKNOWN_REQUIRED_CONTEXT']
        selected = next((m for m in matches if result and m.memory.lesson.lesson_ref == result.matched_lesson_ref), None)
        # Scoring truth is attached only after the historical decision, never supplied to the policy.
        truth = sorted((e for e in archive.outcomes if e.alert_ref == ref and at < e.available_at < archive.holdout_end),
            key=lambda e: (e.available_at, e.event_id))
        malicious_truth = [e for e in truth if e.outcome in ('confirmed_malicious', 'suspicious')]
        # A later benign outcome cannot erase an observed malicious contradiction.
        scored_truth = malicious_truth[0] if malicious_truth else truth[-1] if truth else None
        truth_at = scored_truth.available_at if scored_truth else None
        simultaneous = {e.outcome for e in truth if e.available_at == truth_at}
        later_outcome = scored_truth.outcome if scored_truth else None
        row = dict(alertRef=str(ref), occurredAt=at.isoformat(), eligible=eligible,
            excludedReason=None if eligible else 'missing_historical_triage' if state is None else 'ineligible_historical_workflow',
            disposition=result.disposition if result else 'must_review', reasonCodes=reasons,
            detectionCategory=alert.detection_category or '(unknown)', detectorSource=alert.detector_source,
            priorityBand=state.state.priority_band if state and state.state.priority_band else '(unknown)',
            memoryOutcome=selected.memory.lesson.outcome if selected else '(none)',
            policyVersion=period.configuration.version if period else None,
            policySnapshot=period.configuration.model_dump(mode='json', by_alias=True) if period else None,
            policyEffectiveAt=period.effective_at.isoformat() if period else None,
            inputs=inputs.model_dump(mode='json', by_alias=True) if inputs else None,
            contextProvenance=provenance.model_dump(mode='json',by_alias=True) if provenance else None,
            memoryCoverage=bool(matches), activeLessonCoverage=any(m.guidance_active for m in matches),
            laterOutcome=later_outcome, laterOutcomeAvailableAt=truth_at.isoformat() if truth_at else None,
            laterOutcomeHistory=[e.model_dump(mode='json', by_alias=True) for e in truth],
            ambiguousTruth=len(simultaneous)>1, recalledAt=None)
        # Recalls are new later observations; historical dispositions are never rewritten.
        if row['disposition'] == 'no_immediate_review':
            conflict_times = sorted({e.available_at for e in archive.supports if e.relation == 'conflict' and at < e.available_at < archive.holdout_end})
            for moment in conflict_times:
                # The event just became available: use an infinitesimal next decision instant.
                new_matches = related_matches(memory_at(archive, moment + timedelta(microseconds=1)), alert)
                if any(m.memory.conflict_count for m in new_matches):
                    row['recalledAt'] = moment.isoformat()
                    break
        rows.append(row)
    activations = [e for e in archive.activations if e.action == 'activate' and e.available_at < archive.holdout_end]
    activation_details = []
    for event in sorted(activations, key=lambda e: (e.available_at, str(e.lesson_ref))):
        lesson = next(m for m in archive.lessons if m.lesson_ref == event.lesson_ref)
        activation_details.append(dict(lessonRef=str(event.lesson_ref), activatedAt=event.available_at.isoformat(),
            secondsToActivation=(event.available_at-timestamp(lesson.created_at)).total_seconds(),
            supportingAlertsBeforeActivation=len({e.alert_ref for e in archive.supports if e.lesson_ref == event.lesson_ref and e.relation == 'support' and e.available_at < event.available_at}),
            streamAlertsSinceCreation=sum(timestamp(lesson.created_at) <= timestamp(a.occurred_at) < event.available_at for a in alerts)))
    last = memory_at(archive, archive.holdout_end)
    memory_metrics = dict(candidateLessonsCreated=sum(timestamp(m.created_at)<archive.holdout_end for m in archive.lessons),
        lessonsReachingActivation=len(activations), activationTiming=activation_details,
        conflictsAfterActivation=sum(e.relation=='conflict' and e.available_at<archive.holdout_end and
            any(a.lesson_ref==e.lesson_ref and a.available_at<e.available_at for a in activations) for e in archive.supports),
        expiredLessonCount=sum(m.expires_at is not None and m.expires_at<=archive.holdout_end and m.status!='rejected' for m in last))
    groups = {}
    for key in ('detectionCategory', 'memoryOutcome', 'priorityBand', 'detectorSource'):
        groups[key] = {value: _metrics([r for r in rows if r[key]==value]) for value in sorted({r[key] for r in rows})}
    canonical = archive.model_dump(mode='json', by_alias=True)
    # Input order has no semantics; normalize lists for a reproducible provenance digest.
    for key, value in canonical.items():
        if isinstance(value, list):
            canonical[key] = sorted(value, key=lambda item: json.dumps(item, sort_keys=True))
    digest = sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(formatVersion='temporal-review-report-v1', evaluationMode='retrospective_reconstruction', dataBasis=archive.data_basis,
        evidenceWarning='Synthetic/demo evaluation; not real-world production evidence.' if archive.data_basis=='synthetic/demo' else
            'Historical inputs supplied; provenance and label completeness require independent validation. Not proof of production safety.',
        provenance=archive.provenance, inputSha256=digest, holdoutStart=archive.holdout_start.isoformat(), holdoutEnd=archive.holdout_end.isoformat(),
        totalHoldoutAlerts=len(rows), excludedAlerts=sum(not r['eligible'] for r in rows),
        metrics=_metrics(rows), contextCoverage=context_coverage(rows), memoryMetrics=memory_metrics, breakdowns=groups, decisions=rows,
        limitations=['Observed-feedback replay, not a causal simulation of feedback lost through deferral.',
            'Any strictly later malicious/suspicious outcome before holdout end scores unsafe; otherwise the latest outcome scores. Missing/inconclusive outcomes are not safe labels.',
            'Recall counts unique deferred alerts receiving a related later conflict; it does not erase the original workload/safety result.',
            'Memory lifecycle metrics include pre-holdout learning; workload metrics cover only eligible holdout alerts.',
            'Historical triage missing at occurrence excludes the alert; policy gaps force review. No present-day fallback.'])


def context_coverage(rows):
    eligible=[r for r in rows if r['eligible']]
    complete=[r for r in eligible if r.get('contextProvenance') and r['contextProvenance']['complete']]
    def blocked(statuses):
        return sum(any(f['status'] in statuses for f in (r.get('contextProvenance') or {}).get('fields',[])) for r in eligible)
    return dict(eligibleAlerts=len(eligible),completeTrustedSafetyContext=len(complete),
        blockedByUnknownContext=blocked(('unknown','not_applicable')),blockedByExpiredContext=blocked(('expired',)),
        blockedByConflictingContext=blocked(('conflict',)),legacySnapshotsWithoutFactProvenance=sum(r.get('contextProvenance') is None for r in eligible),
        contextCoverageRate=len(complete)/len(eligible) if eligible else 0,
        trustedContextDeferralRate=sum(r['disposition']=='no_immediate_review' for r in complete)/len(complete) if complete else None)


def render_markdown(report):
    lines = ['# Selective Review Temporal Holdout', '', 'Mode: retrospective_reconstruction (not registered prospective evidence)', '', report['evidenceWarning'], '',
        f"Window: [{report['holdoutStart']}, {report['holdoutEnd']})", f"Input SHA-256: `{report['inputSha256']}`", '',
        '## Workload and Safety', '', '| Metric | Value |', '| --- | --- |']
    lines += [f'| {key} | {value if value is not None else "unavailable"} |' for key, value in report['metrics'].items()]
    lines += ['', '## Context Coverage', '', '```json', json.dumps(report['contextCoverage'],indent=2), '```',
        '', f"Excluded alerts: {report['excludedAlerts']} / {report['totalHoldoutAlerts']}", '', '## Memory', '',
        '```json', json.dumps(report['memoryMetrics'], indent=2), '```']
    for group, entries in report['breakdowns'].items():
        lines += ['', f'## By {group}', '', '| Group | Eligible | Deferred | Unsafe |', '| --- | --- | --- |']
        lines += [f"| {str(key).replace('|', '/').replace(chr(10), ' ')} | {m['totalEligibleAlerts']} | {m['noImmediateReviewCount']} | {m['maliciousOrSuspiciousIncorrectlyDeferred']} |" for key, m in entries.items()]
    lines += ['', '## Interpretation', '', *['- '+s for s in report['limitations']]]
    if 'prospectiveProtocol' in report:
        lines += ['', '## Prospective Protocol', '', '```json',json.dumps(report['prospectiveProtocol'],indent=2),'```',
            '```json',json.dumps(report['outcomeCompleteness'],indent=2),'```']
    return '\n'.join(lines)+'\n'
