"""Read-only product audit shape for the selected current HITL workspace."""
from typing import Any, Literal

from pydantic import Field

from apps.api.contract.common import ApiModel

AuditCategory = Literal['WORKSPACE', 'WORK', 'VERDICT', 'MEMORY', 'REVIEW', 'TIER2', 'RESPONSE', 'RESOLUTION']


class CurrentAuditEvent(ApiModel):
    event_ref: str
    timestamp: str
    actor_type: Literal['human', 'system']
    actor_id: int | None = None
    actor_name: str | None = None
    decision_source: Literal['analyst', 'system_policy', 'historical_migration', 'admin']
    event_category: AuditCategory
    event_type: str
    action: str
    object_type: Literal['workspace', 'alert', 'case', 'lesson', 'recommendation']
    object_ref: str
    alert_ref: str | None = None
    case_ref: str | None = None
    lesson_ref: str | None = None
    workspace: str
    summary: str
    result: str | None = None
    source_subsystem: str
    detail: dict[str, Any] = Field(default_factory=dict)


class CurrentAuditPage(ApiModel):
    items: list[CurrentAuditEvent]
    total: int
    limit: int
    offset: int
    active_workspace: str
