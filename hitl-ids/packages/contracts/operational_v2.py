"""Source-neutral evidence and independently mutable triage state; no routing policy."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from .canonical import CanonicalAlert
from .models import Contract, Probability, Score, utc_now


class V2Contract(Contract):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LegacySourceProvenanceV2(V2Contract):
    source_kind: Literal["legacy_flow_alert"] = "legacy_flow_alert"
    dataset_id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    legacy_alert_ref: UUID
    detection_score: Score
    legacy_fusion_confidence: Probability


class ExternalSourceProvenanceV2(V2Contract):
    source_kind: Literal["external_nids_alert"] = "external_nids_alert"
    sensor_id: str = Field(min_length=1)
    raw_reference: str = Field(min_length=1)
    admission_policy_version: str = Field(min_length=1)
    admission_decision: Literal["hold_for_review"]
    admission_reason: str = Field(min_length=1)
    proposed_operational_priority: Score
    proposed_evidence_class: Literal["external_rule"]
    review_required: Literal[True]
    learning_eligible: Literal[False]
    evaluation_eligible: Literal[False]


SourceProvenanceV2 = Annotated[
    LegacySourceProvenanceV2 | ExternalSourceProvenanceV2, Field(discriminator="source_kind")]


class OperationalAlertV2(V2Contract):
    id: int | None = Field(default=None, gt=0)
    operational_alert_ref: UUID
    canonical_alert_id: UUID
    source_kind: Literal["legacy_flow_alert", "external_nids_alert"]
    detector_source: str = Field(min_length=1)
    detector_name: str = Field(min_length=1)
    detector_version: str | None
    legacy_alert_id: int | None = Field(default=None, gt=0)
    external_inbox_id: int | None = Field(default=None, gt=0)
    detection_title: str = Field(min_length=1)
    detection_category: str | None
    native_severity: str | int
    detector_confidence: Probability | None
    detector_evidence: CanonicalAlert
    source_provenance: SourceProvenanceV2
    occurred_at: str
    occurred_at_timezone_offset: str | None
    source_ip: str
    destination_ip: str
    source_port: Annotated[int, Field(strict=True, ge=0, le=65535)] | None
    destination_port: Annotated[int, Field(strict=True, ge=0, le=65535)] | None
    protocol: str

    @model_validator(mode="after")
    def coherent_source_and_evidence(self):
        legacy = self.source_kind == "legacy_flow_alert"
        if legacy != (self.legacy_alert_id is not None) or legacy == (self.external_inbox_id is not None):
            raise ValueError("exactly one source reference matching sourceKind is required")
        if self.source_provenance.source_kind != self.source_kind:
            raise ValueError("source provenance must match sourceKind")
        if self.operational_alert_ref != self.canonical_alert_id:
            raise ValueError("V2 foundation preserves the canonical reference")
        if legacy:
            if self.detector_source != "current_flow":
                raise ValueError("legacy projection requires current_flow evidence")
            if self.source_provenance.legacy_alert_ref != self.operational_alert_ref:
                raise ValueError("legacy alert reference must be preserved")
        elif self.detector_source == "current_flow":
            raise ValueError("external projection cannot use current_flow evidence")
        if self.detector_source == "suricata" and self.detector_confidence is not None:
            raise ValueError("Suricata confidence must remain null")
        evidence = self.detector_evidence
        for name in ("canonical_alert_id", "detector_source", "detector_name", "detector_version",
                     "detection_title", "detection_category", "occurred_at", "occurred_at_timezone_offset",
                     "source_ip", "destination_ip", "source_port", "destination_port", "protocol"):
            if getattr(self, name) != getattr(evidence, name):
                raise ValueError(f"{name} must match immutable canonical evidence")
        if self.native_severity != evidence.detector_severity or type(self.native_severity) is not type(evidence.detector_severity):
            raise ValueError("native severity must match canonical evidence, including its type")
        if self.detector_confidence != evidence.confidence:
            raise ValueError("detector confidence must match canonical evidence")
        return self


HandlingRouteV2 = Literal["unassigned", "tier1_review", "tier2_candidate", "tier2_case", "no_immediate_review"]
WorkflowStageV2 = Literal["staged", "triage", "assessment", "investigation", "incident", "resolved"]
DecisionSourceV2 = Literal["system_policy", "analyst", "historical_memory", "legacy_projection"]
PriorityBandV2 = Literal["critical", "high", "medium", "low", "informational"]


class OperationalTriageStateV2(V2Contract):
    operational_alert_id: int = Field(gt=0)
    operational_priority: Score | None = None
    priority_band: PriorityBandV2 | None = None
    handling_route: HandlingRouteV2 = "unassigned"
    workflow_stage: WorkflowStageV2 = "staged"
    review_required: bool = True
    review_reason: str = "Operational admission pending; V2 triage policy is not active."
    tier2_recommended: bool = False
    tier2_recommendation_reasons: tuple[str, ...] = ()
    decision_source: DecisionSourceV2 = "system_policy"
    triage_policy_version: str | None = None
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def explicit_priority_and_recommendation(self):
        if (self.operational_priority is None) != (self.priority_band is None):
            raise ValueError("operational priority and priority band must be assigned together")
        if self.tier2_recommended != bool(self.tier2_recommendation_reasons):
            raise ValueError("Tier 2 recommendation and reasons must agree")
        if any(not reason.strip() for reason in self.tier2_recommendation_reasons):
            raise ValueError("Tier 2 recommendation reasons must be nonempty")
        return self
