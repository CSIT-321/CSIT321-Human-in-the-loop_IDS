"""Additive V2 routing API with operational UUID identities."""
from uuid import UUID
from apps.api.contract.common import ApiModel
from packages.contracts.operational_v2 import OperationalTriageStateV2
from packages.detection.routing import RoutingAction, RoutingAudit
from packages.detection.tier2_cases import CaseView
from packages.contracts.suricata_bundle import AttackClassification, SystemRoutingDecision
from packages.detection.selective_review import EffectiveReview


class OperationalSummary(ApiModel):
    """Whole persisted V2 dataset; categories overlap, never a sum of queue pages."""
    total_alerts: int
    critical_alerts: int
    tier1_review: int
    tier2_cases: int
    expert_review: int
    review_required: int
    no_immediate_review: int
    open_tier2_cases: int


class QueueDetectionSummary(ApiModel):
    source_ip: str
    destination_ip: str
    destination_port: int | None
    occurred_at: str
    related_signature_count: int | None = None
    evidence_types: list[str] = []


class RoutingView(ApiModel):
    operational_alert_ref: UUID
    title: str
    detector_name: str
    detector_source: str | None = None
    state: OperationalTriageStateV2
    state_version: str
    review_reasons: list[str]
    latest_decision: RoutingAudit | None
    allowed_actions: list[RoutingAction]
    case_ref: UUID | None = None
    classification: AttackClassification | None = None
    system_routing: SystemRoutingDecision | None = None
    detection_summary: QueueDetectionSummary | None = None
    effective_review: EffectiveReview | None = None


class RoutingResponse(ApiModel):
    view: RoutingView
    audit: RoutingAudit
    replayed: bool


class EscalateCaseResponse(RoutingResponse):
    case: CaseView
    event_id: int
