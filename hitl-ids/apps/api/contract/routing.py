"""Additive V2 routing API with operational UUID identities."""
from uuid import UUID
from apps.api.contract.common import ApiModel
from packages.contracts.operational_v2 import OperationalTriageStateV2
from packages.detection.routing import RoutingAction, RoutingAudit
from packages.detection.tier2_cases import CaseView
from packages.contracts.suricata_bundle import AttackClassification, SystemRoutingDecision
from packages.detection.selective_review import EffectiveReview
from packages.detection.analyst_work import WorkView


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
    active_alerts: int = 0
    completed_work: int = 0
    escalated_work: int = 0
    available_work: int = 0
    in_review_work: int = 0
    # C2 + D4 condition 3 (approved 2026-11-08). tier1_groups + tier1_singles = tier1_review.
    tier2_candidates: int = 0   # open C3 recommendations on active work
    auto_escalated: int = 0     # Tier 2 cases the system policy opened
    tier1_groups: int = 0
    tier1_singles: int = 0


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
    tier2_recommendation_open: bool = False  # C3: the "Why Tier 2" panel shows only while this is true
    case_ref: UUID | None = None
    group_member_count: int | None = None  # C2: flows in the group this alert represents; None for a single
    classification: AttackClassification | None = None
    system_routing: SystemRoutingDecision | None = None
    detection_summary: QueueDetectionSummary | None = None
    effective_review: EffectiveReview | None = None
    work: WorkView | None = None


class RoutingResponse(ApiModel):
    view: RoutingView
    audit: RoutingAudit
    replayed: bool


class EscalateCaseResponse(RoutingResponse):
    case: CaseView
    event_id: int
