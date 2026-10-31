"""Pure selective attention policy. No routing, verdict, priority or execution side effects."""
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field
from packages.contracts.operational_v2 import V2Contract,OperationalAlertV2,OperationalTriageStateV2
from packages.detection.triage_memory import MemoryMatch
from packages.detection.triage_policy import TriageContext

Disposition=Literal['must_review','recommended_review','no_immediate_review']


class SelectivePolicy(V2Contract):
    version: str = Field(min_length=1)
    minimum_support: int = Field(strict=True,ge=3)
    minimum_agreement_ratio: float = Field(ge=0.67,le=1)
    false_positive_minimum_support: int = Field(strict=True,ge=3)
    context_maximum_age_hours: int = Field(strict=True,ge=1,le=24)
    campaign_alert_threshold: int = Field(strict=True,ge=2)
    audit_sample_percent: int = Field(strict=True,ge=0,le=100)


def load_policy():
    return SelectivePolicy.model_validate_json((Path(__file__).resolve().parents[2]/'config/selective-review-v1.json').read_text(encoding='utf-8'))


class ReviewInputs(V2Contract):
    alert: OperationalAlertV2
    triage: OperationalTriageStateV2
    context: TriageContext
    context_audit_id: int | None
    context_recorded_at: AwareDatetime | None
    matches: list[MemoryMatch]
    human_override: bool
    human_verdict_present: bool


class SelectiveResult(V2Contract):
    disposition: Disposition
    reason_codes: list[str]
    explanation: str
    matched_lesson_ref: UUID | None
    policy_version: str
    decision_source: Literal['selective_review_policy','human_override'] = 'selective_review_policy'


def evaluate_review(inputs:ReviewInputs,policy:SelectivePolicy,now:datetime):
    inputs=ReviewInputs.model_validate(inputs.model_dump())
    policy=SelectivePolicy.model_validate(policy.model_dump())
    if now.tzinfo is None:
        raise ValueError('evaluation time must be timezone-aware')
    reasons=[]
    context=inputs.context
    if inputs.human_override:
        reasons.append('HUMAN_REVIEW_OVERRIDE')
    if inputs.human_verdict_present:
        reasons.append('EXISTING_HUMAN_VERDICT')
    if (inputs.triage.handling_route,inputs.triage.workflow_stage)!=('tier1_review','triage'):
        reasons.append('UNSUPPORTED_WORKFLOW')
    if inputs.triage.tier2_recommended:
        reasons.append('TIER2_RECOMMENDED')
    if inputs.alert.detector_evidence.evidence_class=='signature_override':
        reasons.append('DETECTOR_DISAGREEMENT')
    if inputs.context_audit_id is None or inputs.context_recorded_at is None:
        reasons.append('MISSING_TRUSTED_CONTEXT')
    elif not inputs.context_recorded_at<=now<inputs.context_recorded_at+timedelta(hours=policy.context_maximum_age_hours):
        reasons.append('STALE_OR_FUTURE_CONTEXT')
    if any(value is None for value in context.model_dump().values()):
        reasons.append('UNKNOWN_REQUIRED_CONTEXT')
    for active,code in (
        (context.asset_criticality in ('high','critical'),'HIGH_RISK_ASSET'),
        (context.known_malicious_indicator is True,'KNOWN_MALICIOUS_INDICATOR'),
        (context.evidence_conflict is True,'EVIDENCE_CONFLICT'),
        (context.confirmed_malicious is True,'CONFIRMED_MALICIOUS_CONTEXT'),
        (context.response_required is True,'RESPONSE_REQUIRED'),
        (context.analyst_escalated is True or context.unresolved_by_tier1 is True,'HUMAN_ESCALATION_CONTEXT'),
        (context.repeated_campaign is True or (context.correlated_alert_count or 0)>=policy.campaign_alert_threshold,'CAMPAIGN_RISK'),
    ):
        if active:reasons.append(code)
    qualified=[]
    for match in inputs.matches:
        memory=match.memory
        # Even a related conflicted/malicious lesson is a conservative veto, not a vote to average away.
        if memory.conflict_count or memory.status=='conflict_review':
            reasons.append('MEMORY_CONFLICT')
        if memory.lesson.outcome in ('confirmed_malicious','suspicious'):
            reasons.append('UNSAFE_MEMORY_OUTCOME')
        exact=set(memory.lesson.scope_fields).issubset(match.matched_fields)
        threshold=policy.false_positive_minimum_support if memory.lesson.outcome=='false_positive' else policy.minimum_support
        if (memory.status=='active' and match.guidance_active and match.strength=='high' and exact
                and memory.lesson.scope=='exact' and not match.mismatched_fields
                and memory.valid_from is not None and memory.valid_from<=now
                and memory.expires_at is not None and now<memory.expires_at
                and memory.support_count>=max(threshold,policy.minimum_support,memory.lesson.configuration.minimum_support)
                and memory.agreement_ratio>=max(policy.minimum_agreement_ratio,memory.lesson.configuration.minimum_agreement_ratio)
                and memory.conflict_count==0 and memory.lesson.outcome in ('expected_activity','false_positive')):
            qualified.append(memory)
    if not qualified:reasons.append('NO_QUALIFIED_ACTIVE_EXACT_MEMORY')
    selected=sorted(qualified,key=lambda memory:str(memory.lesson.lesson_ref))[0] if qualified else None
    if reasons:
        return SelectiveResult(disposition='must_review',reason_codes=list(dict.fromkeys(reasons)),
            explanation='Immediate human review required: '+', '.join(dict.fromkeys(reasons))+'.',
            matched_lesson_ref=selected.lesson.lesson_ref if selected else None,policy_version=policy.version)
    bucket=int(sha256(str(inputs.alert.operational_alert_ref).encode()).hexdigest()[:8],16)%100
    sampled=bucket<policy.audit_sample_percent
    return SelectiveResult(disposition='recommended_review' if sampled else 'no_immediate_review',
        reason_codes=['DETERMINISTIC_AUDIT_SAMPLE'] if sampled else ['VALIDATED_MEMORY_AND_CONTEXT'],
        explanation='Selected for deterministic human audit sampling.' if sampled else
        'Active exact benign memory and fresh trusted safety context passed every gate. This is not a human verdict or closure.',
        matched_lesson_ref=selected.lesson.lesson_ref,policy_version=policy.version)
