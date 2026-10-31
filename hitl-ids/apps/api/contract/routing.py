"""Additive V2 routing API with operational UUID identities."""
from uuid import UUID
from apps.api.contract.common import ApiModel
from packages.contracts.operational_v2 import OperationalTriageStateV2
from packages.detection.routing import RoutingAction, RoutingAudit


class RoutingView(ApiModel):
    operational_alert_ref: UUID
    title: str
    detector_name: str
    state: OperationalTriageStateV2
    state_version: str
    review_reasons: list[str]
    latest_decision: RoutingAudit | None
    allowed_actions: list[RoutingAction]


class RoutingResponse(ApiModel):
    view: RoutingView
    audit: RoutingAudit
    replayed: bool
