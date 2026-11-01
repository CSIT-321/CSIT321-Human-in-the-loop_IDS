"""Additive V2 routing API with operational UUID identities."""
from uuid import UUID
from apps.api.contract.common import ApiModel
from packages.contracts.operational_v2 import OperationalTriageStateV2
from packages.detection.routing import RoutingAction, RoutingAudit
from packages.detection.tier2_cases import CaseView


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


class RoutingResponse(ApiModel):
    view: RoutingView
    audit: RoutingAudit
    replayed: bool


class EscalateCaseResponse(RoutingResponse):
    case: CaseView
    event_id: int
