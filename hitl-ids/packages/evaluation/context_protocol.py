"""Opt-in preregistered prospective reporting; no statistical performance claim."""
from pydantic import AwareDatetime, Field, model_validator
from packages.contracts import models as m
from packages.contracts.operational_v2 import V2Contract
from packages.evaluation.temporal_review import evaluate_temporal
from packages.detection.selective_review_policy import SelectivePolicy
from packages.detection.trusted_context import ContextPolicy


class ProspectiveProtocol(V2Contract):
    version: str
    registered_at: AwareDatetime
    holdout_start: AwareDatetime
    holdout_end: AwareDatetime
    minimum_eligible_alerts: int = Field(strict=True,ge=1)
    minimum_outcome_completeness: float = Field(gt=0,le=1)
    selective_policy_version: str
    context_policy_version: str
    selective_policy: SelectivePolicy
    context_policy: ContextPolicy

    @model_validator(mode='after')
    def dates(self):
        if not self.registered_at<self.holdout_start<self.holdout_end:
            raise ValueError('protocol must be registered before its nonempty holdout')
        if self.selective_policy.version!=self.selective_policy_version or self.context_policy.version!=self.context_policy_version:
            raise ValueError('frozen configuration and version identifiers must agree')
        return self


def evaluate_prospective(archive,protocol,*,now=None):
    raise ValueError('registered prospective evaluation rejects reconstructed-only data; use prospective_recorded with a closed run')


def evaluate_reconstruction_protocol(archive,protocol,*,now=None):
    """Legacy exploratory comparison only, never a registered prospective result."""
    protocol=ProspectiveProtocol.model_validate(protocol.model_dump())
    if (now or m.utc_now())<protocol.holdout_end:
        raise ValueError('prospective holdout has not closed; evaluation is prohibited')
    if archive.holdout_start!=protocol.holdout_start or archive.holdout_end!=protocol.holdout_end:
        raise ValueError('archive window differs from frozen protocol')
    if archive.context_facts is None:
        raise ValueError('prospective evaluation requires fact history, not legacy context snapshots')
    report=evaluate_temporal(archive)
    policy=protocol.selective_policy.model_dump(mode='json',by_alias=True)
    context=protocol.context_policy.model_dump(mode='json',by_alias=True)
    if any(row['policySnapshot'] is not None and row['policySnapshot']!=policy for row in report['decisions']):
        raise ValueError('policy version differs from frozen protocol')
    if any(fact['freshnessPolicy']!=context for row in report['decisions'] for field in (row.get('contextProvenance') or {}).get('fields',[]) for fact in field['facts']):
        raise ValueError('context policy version differs from frozen protocol')
    eligible=[r for r in report['decisions'] if r['eligible']]
    labelled=sum(r['laterOutcome'] not in (None,'inconclusive') for r in eligible)
    completeness=labelled/len(eligible) if eligible else 0
    report['exploratoryProtocol']=protocol.model_dump(mode='json',by_alias=True)
    report['outcomeCompleteness']=dict(eligibleAlerts=len(eligible),labelledAlerts=labelled,
        unlabelledOrInconclusiveAlerts=len(eligible)-labelled,rate=completeness,
        targetMet=len(eligible)>=protocol.minimum_eligible_alerts and completeness>=protocol.minimum_outcome_completeness,
        interpretation='Collection targets only; not statistical significance or proof of safe automation.')
    return report
