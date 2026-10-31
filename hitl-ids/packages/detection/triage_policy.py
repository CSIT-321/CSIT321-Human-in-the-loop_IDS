"""Pure, explainable V2 policy. Priority is urgency, and a recommendation is not a route."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from packages.contracts.models import Score
from packages.contracts.operational_v2 import OperationalAlertV2, V2Contract

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "config" / "operational-triage-v1.json"
PolicyBand = Literal["P1", "P2", "P3", "P4"]


class TriageContext(V2Contract):
    asset_criticality: Literal["low", "medium", "high", "critical"] | None = None
    repeated_campaign: StrictBool | None = None
    correlated_alert_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    response_required: StrictBool | None = None
    known_malicious_indicator: StrictBool | None = None
    analyst_escalated: StrictBool | None = None
    unresolved_by_tier1: StrictBool | None = None
    evidence_conflict: StrictBool | None = None
    # A known indicator is not, by itself, confirmation that this alert is malicious.
    confirmed_malicious: StrictBool | None = None


class BandThreshold(V2Contract):
    band: PolicyBand
    minimum: Score


class TriagePolicy(V2Contract):
    version: str = Field(min_length=1)
    suricata_severity_priority: dict[str, Score]
    priority_bands: tuple[BandThreshold, ...]
    critical_asset_adjustment: Score
    known_malicious_indicator_adjustment: Score
    evidence_conflict_adjustment: Score
    high_priority_threshold: Score
    campaign_alert_threshold: int = Field(strict=True, ge=2)

    @model_validator(mode="after")
    def complete_ordered_configuration(self):
        if set(self.suricata_severity_priority) != {"1", "2", "3", "4"}:
            raise ValueError("severity policy must explicitly define priorities 1 through 4")
        if tuple(b.band for b in self.priority_bands) != ("P1", "P2", "P3", "P4"):
            raise ValueError("bands must be ordered P1, P2, P3, P4")
        minima = [band.minimum for band in self.priority_bands]
        if minima[-1] != 0 or any(a <= b for a, b in zip(minima, minima[1:])):
            raise ValueError("band minima must strictly descend to zero")
        return self


class ContextAdjustment(V2Contract):
    condition: str
    requested_delta: float
    applied_delta: float
    reason: str


class TriagePolicyResult(V2Contract):
    base_priority: Score
    base_priority_reason: str
    context_adjustments: tuple[ContextAdjustment, ...]
    final_operational_priority: Score
    priority_band: PolicyBand
    review_required: Literal[True] = True
    review_reasons: tuple[str, ...] = Field(min_length=1)
    handling_route: Literal["tier1_review"] = "tier1_review"
    workflow_stage: Literal["triage"] = "triage"
    tier2_recommended: bool
    tier2_recommendation_reasons: tuple[str, ...]
    decision_source: Literal["system_policy"] = "system_policy"
    policy_version: str


def load_triage_policy(path: Path = DEFAULT_POLICY) -> TriagePolicy:
    return TriagePolicy.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_triage(alert: OperationalAlertV2, context: TriageContext | None = None,
                    policy: TriagePolicy | None = None) -> TriagePolicyResult:
    policy = policy or load_triage_policy()
    # Revalidate caller-provided DTOs (including model_copy updates) at this boundary.
    policy = TriagePolicy.model_validate(policy.model_dump())
    context = TriageContext.model_validate((context or TriageContext()).model_dump())
    alert = OperationalAlertV2.model_validate(alert.model_dump())
    if alert.source_kind == "external_nids_alert" and alert.detector_source == "suricata":
        if type(alert.native_severity) is not int or str(alert.native_severity) not in policy.suricata_severity_priority:
            raise ValueError("Suricata native severity has no configured priority")
        base = policy.suricata_severity_priority[str(alert.native_severity)]
        basis = f"Suricata native severity {alert.native_severity} maps to urgency {base:g}; not a probability."
    elif alert.source_kind == "legacy_flow_alert":
        base = alert.source_provenance.detection_score
        basis = f"V2-only baseline uses immutable legacy detection score {base:g}; legacy queue state is unchanged."
    else:
        raise ValueError("detector source has no V1 triage policy")
    score = base
    adjustments = []
    conditions = (
        (context.asset_criticality == "critical", "critical_asset", policy.critical_asset_adjustment,
         "Explicit critical asset context"),
        (context.known_malicious_indicator is True, "known_malicious_indicator",
         policy.known_malicious_indicator_adjustment, "Explicit known malicious indicator context"),
        (context.evidence_conflict is True, "evidence_conflict", policy.evidence_conflict_adjustment,
         "Conflicting evidence needs human investigation"),
    )
    for active, condition, delta, explanation in conditions:
        if active:
            next_score = min(100.0, score + delta)
            applied = next_score - score
            adjustments.append(ContextAdjustment(condition=condition, requested_delta=delta,
                applied_delta=applied, reason=f"{explanation}: requested +{delta:g}, applied +{applied:g}; bounded at 100."))
            score = next_score
    selected_band = next(b for b in policy.priority_bands if score >= b.minimum)
    band = selected_band.band
    reasons = [basis, "Tier 1 review is required; no automatic dismissal or Tier 2 transition."]
    reasons.append(f"Final urgency {score:g} maps to {band} at configured minimum {selected_band.minimum:g}; priority does not assign a tier.")
    unknown = [field for field, value in context.model_dump(by_alias=True).items() if value is None]
    if unknown:
        reasons.append("Context unknown / not available: " + ", ".join(unknown))
    reasons.extend(change.reason for change in adjustments)
    recommendations = []
    if context.analyst_escalated is True:
        recommendations.append("Analyst explicitly requested escalation.")
    if context.confirmed_malicious is True and context.response_required is True:
        recommendations.append("Explicitly confirmed malicious activity requires a response.")
    if score >= policy.high_priority_threshold and context.asset_criticality == "critical":
        recommendations.append(f"Priority {score:g} meets threshold {policy.high_priority_threshold:g} AND asset is explicitly critical.")
    if context.repeated_campaign is True and context.correlated_alert_count is not None and context.correlated_alert_count >= policy.campaign_alert_threshold:
        recommendations.append(f"Repeated campaign AND {context.correlated_alert_count} correlated alerts meet threshold {policy.campaign_alert_threshold}.")
    if context.unresolved_by_tier1 is True:
        recommendations.append("Tier 1 explicitly reports the alert as unresolved.")
    return TriagePolicyResult(base_priority=base, base_priority_reason=basis,
        context_adjustments=tuple(adjustments), final_operational_priority=score, priority_band=band,
        review_reasons=tuple(reasons), tier2_recommended=bool(recommendations),
        tier2_recommendation_reasons=tuple(recommendations), policy_version=policy.version)
