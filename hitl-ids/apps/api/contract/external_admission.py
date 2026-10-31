"""Safe staging inspection; raw detector evidence is not accepted from HTTP callers."""
from typing import Literal
from uuid import UUID
from apps.api.contract.common import ApiModel


class ExternalAdmissionView(ApiModel):
    external_inbox_id: int
    canonical_alert_id: UUID
    detector: str
    signature: str
    category: str
    native_severity: int
    confidence: None
    source_ip: str
    destination_ip: str
    source_port: int | None
    destination_port: int | None
    protocol: str
    occurred_at: str
    occurred_at_timezone_offset: str | None
    status: Literal['staged', 'eligible', 'admitted', 'held', 'failed']
    status_reason: str
    staging_decision: str
    proposed_priority: float
    proposal_policy_version: str
    review_id: int | None
    review_decision: Literal['accepted', 'held'] | None
    review_reason: str | None
    review_actor_id: int | None
    operational_alert_ref: UUID | None
    operational_alert_id: int | None
    admitted_at: str | None
    admission_actor_id: int | None
    can_review: bool
    can_admit: bool


class ExternalAdmissionResponse(ApiModel):
    view: ExternalAdmissionView
    replayed: bool
