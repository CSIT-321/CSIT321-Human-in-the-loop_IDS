"""Read-only current Admin projections. Historical feedback is intentionally absent."""
from typing import Literal

from apps.api.contract.common import ApiModel
from apps.api.contract.routing import OperationalSummary
from packages.detection.attack_classification import ClassificationPolicy
from packages.detection.system_routing import SystemRoutingPolicy
from packages.detection.triage_memory import MemoryConfig, AutoLearningPolicy
from packages.detection.selective_review_policy import SelectivePolicy


class MemoryCounts(ApiModel):
    total: int
    active: int
    conflict_review: int


class AdminOverview(ApiModel):
    detector_source: Literal['Suricata'] = 'Suricata'
    active_workspace_id: str
    active_workspace_name: str
    workspace_ready: bool
    database_ready: bool
    workspace_alert_count: int
    operational: OperationalSummary
    memory: MemoryCounts
    classification_policy_version: str
    routing_policy_version: str
    memory_policy_version: str
    selective_review_policy_version: str


class ClaimPolicyView(ApiModel):
    version: str
    claim_arbitration_window_ms: int


class AdminGovernance(ApiModel):
    automatic_learning_enabled: bool = True
    classification: ClassificationPolicy
    routing: SystemRoutingPolicy
    memory: MemoryConfig
    auto_learning: AutoLearningPolicy
    selective_review: SelectivePolicy
    analyst_work: ClaimPolicyView
    response_execution: Literal['disabled'] = 'disabled'


class AdminUser(ApiModel):
    username: str
    display_name: str
    role: str
    status: str
    last_login: str | None


class AdminUsers(ApiModel):
    items: list[AdminUser]
