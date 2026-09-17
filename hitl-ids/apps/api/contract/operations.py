"""Admin and evaluator surfaces (plan step S10a): dashboard, runs, audit, guardrails, evaluation.

Thin by design (D6): the analyst path is the only one built to depth. These exist so an
administrator can see what the guardrails blocked and an evaluator can read the three-arm deltas
without a terminal — which is what makes the safety and evaluation claims demonstrable rather than
asserted.

Two shapes here are load-bearing for honesty:

* ``GuardrailConfigUpdate`` is the **only** write an administrator has, and it is role-gated. The
  five settings are the ones `guardrail_config` actually holds; a form offering more would imply
  controls that do not exist.
* ``EvaluationComparison`` carries **deltas that may be negative**, and the contract says so. S15
  measured precision@50 falling from 1.000 to 0.980; an evaluator screen that could only render
  improvements would be a screen that lies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from apps.api.contract.common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Actor,
    ApiModel,
    PageInfo,
    SortDirection,
)
from packages.contracts import models as m

# --------------------------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------------------------


class QueueBandCount(ApiModel):
    queue_class: m.QueueClass
    count: int = Field(ge=0)
    requires_review: int = Field(ge=0)


class TopValue(ApiModel):
    """One value and how often it occurs, e.g. an IP address or a destination port."""

    value: str
    count: int = Field(ge=0)
    flagged: int = Field(ge=0, description="Of these, alerts a detector flagged (band is not none)")


class TimeBucket(ApiModel):
    bucket: str = Field(description="Capture-local hour, e.g. 2018-02-14 12:00")
    count: int = Field(ge=0)
    flagged: int = Field(ge=0)


class DashboardBreakdowns(ApiModel):
    """``GET /api/dashboard/breakdowns`` — top talkers, verdict and status mix, guardrail actions,
    and flow volume by capture hour (console rebuild B4).

    These are **recorded** flows: the histogram shows when the traffic was captured, not a live rate.
    """

    generated_at: datetime
    top_source_ips: list[TopValue] = Field(default_factory=list)
    top_destination_ips: list[TopValue] = Field(default_factory=list)
    top_destination_ports: list[TopValue] = Field(default_factory=list)
    verdict_mix: dict[str, int] = Field(default_factory=dict,
                                        description="Verdicts currently in force, by category")
    status_mix: dict[str, int] = Field(default_factory=dict)
    guardrail_interventions: dict[str, int] = Field(default_factory=dict,
                                                    description="Interventions by guardrail code")
    flow_time_histogram: list[TimeBucket] = Field(default_factory=list)


class EntityIp(ApiModel):
    """``GET /api/entities/ip/{ip}`` — what the recorded flows say about one address (B5)."""

    ip: str
    alerts: int = Field(ge=0)
    as_source: int = Field(ge=0)
    as_destination: int = Field(ge=0)
    flagged: int = Field(ge=0)
    first_seen: str | None = Field(default=None, description="Earliest capture time")
    last_seen: str | None = Field(default=None, description="Latest capture time")
    by_queue_class: dict[str, int] = Field(default_factory=dict)
    by_attack_category: dict[str, int] = Field(default_factory=dict)
    verdict_mix: dict[str, int] = Field(default_factory=dict)
    top_peers: list[TopValue] = Field(default_factory=list)
    top_destination_ports: list[TopValue] = Field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Administrator IP security report
# --------------------------------------------------------------------------------------------


class IpReportSummary(ApiModel):
    total_alerts: int = Field(ge=0)
    confirmed_malicious: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    escalated: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    expected_activity: int = Field(ge=0)
    needs_investigation: int = Field(ge=0)
    distinct_attack_categories: int = Field(ge=0)
    distinct_destination_hosts: int = Field(ge=0)
    distinct_destination_ports: int = Field(ge=0)
    first_seen: str | None = None
    last_seen: str | None = None


class IpAttackBehaviour(ApiModel):
    attack_category: str
    alert_count: int = Field(ge=0)
    confirmed_malicious: int = Field(ge=0)


class IpTargetHost(ApiModel):
    destination_ip: str
    alerts: int = Field(ge=0)
    confirmed_malicious: int = Field(ge=0)
    last_seen: str | None = None


class IpDestinationPort(ApiModel):
    port: int = Field(ge=0, le=65535)
    alerts: int = Field(ge=0)
    confirmed_malicious: int = Field(ge=0)


class IpReportTimelineRow(ApiModel):
    capture_time: str | None = None
    alert_ref: str
    source_record_id: str
    source_ip: str
    destination_ip: str
    destination_port: int = Field(ge=0, le=65535)
    protocol: str
    attack_category: str | None = None
    detection_score: m.Score
    operational_score: m.Score
    effective_verdict: m.FeedbackCategory | None = None
    status: m.AlertStatus


class IpReportRecommendation(ApiModel):
    action: Literal[
        "Review for temporary block",
        "Investigate / monitor",
        "Review for suppression / allow-listing",
        "Mixed evidence — investigate before action",
        "Monitor",
    ]
    reason: str
    advisory: str = "Recommendation is advisory. No network blocking action is performed."


class IpSecurityReport(ApiModel):
    """A read-only source-IP report derived from recorded flows and effective analyst verdicts."""

    source_ip: str
    from_date: str | None = None
    to_date: str | None = None
    generated_at: datetime
    summary: IpReportSummary
    attack_behaviour: list[IpAttackBehaviour] = Field(default_factory=list)
    targeted_hosts: list[IpTargetHost] = Field(default_factory=list)
    destination_ports: list[IpDestinationPort] = Field(default_factory=list)
    timeline: list[IpReportTimelineRow] = Field(default_factory=list)
    recommendation: IpReportRecommendation


SourceIpOverviewSort = Literal[
    "totalAlerts",
    "confirmedMalicious",
    "confirmedMaliciousRate",
    "escalated",
    "falsePositives",
    "unjudged",
    "lastSeen",
    "sourceIp",
]


class SourceIpOverviewQuery(ApiModel):
    from_date: str | None = None
    to_date: str | None = None
    search: str | None = Field(default=None, max_length=200)
    min_alerts: int = Field(default=1, ge=1)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)
    sort: SourceIpOverviewSort = "totalAlerts"
    direction: SortDirection = "desc"


class SourceIpOverviewRow(ApiModel):
    source_ip: str
    total_alerts: int = Field(ge=0)
    judged_alerts: int = Field(ge=0)
    confirmed_malicious: int = Field(ge=0)
    confirmed_malicious_rate: float | None = Field(default=None, ge=0, le=1)
    false_positives: int = Field(ge=0)
    benign_positives: int = Field(ge=0)
    escalated: int = Field(ge=0)
    needs_investigation: int = Field(ge=0)
    unjudged: int = Field(ge=0)
    first_seen: str | None = None
    last_seen: str | None = None


class SourceIpOverviewPage(ApiModel):
    generated_at: datetime
    from_date: str | None = None
    to_date: str | None = None
    items: list[SourceIpOverviewRow]
    page: PageInfo
    sort: SourceIpOverviewSort
    direction: SortDirection


class DashboardSummary(ApiModel):
    """``GET /api/dashboard/summary`` — the analyst's landing view."""

    generated_at: datetime
    run_id: int | None = None
    total_alerts: int = Field(ge=0)
    by_queue_class: list[QueueBandCount] = Field(default_factory=list)
    by_evidence_class: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_attack_category: dict[str, int] = Field(default_factory=dict)
    requires_review: int = Field(ge=0)
    tier2_candidates: int = Field(ge=0)
    feedback_events: int = Field(ge=0)
    guardrail_interventions: int = Field(ge=0)
    alerts_moved_by_feedback: int = Field(
        default=0, ge=0,
        description="Alerts whose combined_score or queue_class differs from detection")


# --------------------------------------------------------------------------------------------
# Detection runs
# --------------------------------------------------------------------------------------------


class DetectionRunRequest(ApiModel):
    """``POST /api/detection/run``. Detection is an offline batch (D3), never inline in a request:
    the endpoint starts a run and returns its handle."""

    sample: str | None = Field(
        default=None, description="Source CSV path; defaults to the committed demo sample")
    limit: int | None = Field(default=None, ge=1, description="First N flows in timestamp order")
    seed: int | None = None


class DetectionRunSummary(ApiModel):
    run_id: int
    status: m.DetectionRunStatus
    dataset_id: int
    model_version: str
    rule_set_version: str
    seed: int | None = None
    started_at: datetime
    completed_at: datetime | None = None
    flows: int = Field(default=0, ge=0)
    alerts: int = Field(default=0, ge=0)
    by_evidence_class: dict[str, int] = Field(default_factory=dict)
    by_queue_class: dict[str, int] = Field(default_factory=dict)
    explanations_computed: bool = True


# --------------------------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------------------------


class AuditEntryOut(ApiModel):
    """One append-only audit record. ``UPDATE`` and ``DELETE`` raise at the database (NFR-02/03)."""

    event_id: int
    event_type: m.AuditEventType
    actor: Actor
    created_at: datetime
    alert_ref: str | None = None
    rationale: str | None = None
    details: dict[str, Any] | None = None


class AuditQuery(ApiModel):
    """``GET /api/audit-log`` filters."""

    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    event_type: list[m.AuditEventType] | None = None
    actor_id: int | None = None
    since: datetime | None = None
    until: datetime | None = None


# --------------------------------------------------------------------------------------------
# Guardrail configuration — the administrator's only write
# --------------------------------------------------------------------------------------------


class GuardrailSetting(ApiModel):
    config_key: str
    config_value: float
    description: str | None = None
    updated_at: datetime | None = None


class GuardrailConfig(ApiModel):
    """``GET /api/config/guardrails``."""

    settings: list[GuardrailSetting] = Field(default_factory=list)


class GuardrailConfigUpdate(ApiModel):
    """``PUT /api/config/guardrails`` — **role-gated to `system_admin`** (the stub checks the
    header; S18 makes it real).

    Every field is optional; omitted settings are left alone. Values are validated against the same
    ranges `GuardrailPolicy` enforces, so an invalid configuration is refused here rather than
    discovered when an analyst's feedback behaves strangely.
    """

    max_feedback_reduction: float | None = Field(default=None, ge=0, le=100)
    max_feedback_increase: float | None = Field(default=None, ge=0, le=100)
    critical_alert_floor: m.Score | None = None
    infiltration_alert_floor: m.Score | None = None
    critical_alert_threshold: m.Score | None = None
    rationale: str = Field(min_length=1, max_length=2000,
                           description="Required: the audit entry records why, not just what")


# --------------------------------------------------------------------------------------------
# Evaluation — S15's metrics. These schemas are why S15 comes before S10a.
# --------------------------------------------------------------------------------------------


class ClassMetrics(ApiModel):
    support: int = Field(ge=0)
    predicted: int = Field(ge=0)
    precision: float
    recall: float
    f1: float
    fpr: float
    fnr: float


class PrecisionAtK(ApiModel):
    k: int = Field(ge=1)
    precision: float
    attacks: int = Field(ge=0)
    false_positives: int = Field(ge=0)


class SaturationMetrics(ApiModel):
    """Why a promotion can be inert: where a band sits at the ceiling the formula has no headroom
    and order falls to the `id ASC` tie-break. 975 of 996 on the demo sample."""

    flagged_alerts: int = Field(ge=0)
    at_maximum_score: int = Field(ge=0)
    share_at_maximum: float
    distinct_scores_among_flagged: int = Field(ge=0)


class MovementGroup(ApiModel):
    """``adjusted`` is the system acting; ``rankChanged`` includes drift caused by others moving.
    Leakage is measured by ``adjusted`` in the ``unrelated`` group, never by rank."""

    alerts: int = Field(ge=0)
    adjusted: int = Field(ge=0)
    rank_changed: int = Field(ge=0)
    promoted: int = Field(ge=0)
    demoted: int = Field(ge=0)
    band_changed: int = Field(ge=0)
    score_changed: int = Field(ge=0)
    attacks_promoted: int = Field(ge=0)
    benign_promoted: int = Field(ge=0)
    benign_demoted: int = Field(ge=0)
    best_rank_reached_by_a_benign_alert: int | None = None
    mean_rank_change: float


class SignatureOverridePreservation(ApiModel):
    """Invariant I3, reported separately as the plan requires — including when the database holds
    no such alert, in which case the rate is null and the note says why."""

    alerts: int = Field(ge=0)
    changed: int = Field(ge=0)
    preservation_rate: float | None = None
    note: str | None = None


class ArmResultOut(ApiModel):
    arm: str
    feedback: bool
    guardrails: bool
    verdicts: int = Field(ge=0)
    precision_at_50: float
    false_positives_in_top_50: int = Field(ge=0)
    mrr_true_positives: float
    mean_rank_true_positives: float
    critical_preservation_rate: float | None = None
    critical_floor_breaches: int = Field(ge=0)
    signature_override_alerts: int = Field(ge=0)
    guardrail_actions: dict[str, int] = Field(default_factory=dict)
    guardrail_pass: bool


class EvaluationScenarioOut(ApiModel):
    scenario_id: int
    name: str
    guardrails_active: bool
    dataset_id: int
    model_version: str
    rule_set_version: str
    preregistration: dict[str, Any] = Field(default_factory=dict)
    sequence_digest: str | None = None
    sequence_length: int = Field(default=0, ge=0)
    created_at: datetime


class EvaluationRunOut(ApiModel):
    """``GET /api/evaluation/runs`` — one committed three-arm run, so the evaluator can find it.

    Added at S14: the runs live in `evaluation/three-arm/runs/`, not in any database, so without a
    listing the evaluator would need a run id typed from a terminal.
    """

    run_id: str
    commit: str | None = None
    sequence_length: int = Field(ge=0)
    arms: list[str] = Field(default_factory=list, description="Arm names, in run order")
    detection_metrics_identical_across_arms: bool
    preregistration: dict[str, Any] = Field(default_factory=dict)


class EvaluationComparison(ApiModel):
    """``GET /api/evaluation/runs/{runId}`` — the three arms and their deltas.

    **Deltas may be negative, and the screen must render them as measured.** S15's first run showed
    precision@50 falling 1.000 → 0.980 and a benign alert reaching rank 1. Reporting only the
    favourable direction would rebuild the exit criterion plan v0.3 struck out.
    """

    run_id: str
    commit: str | None = None
    preregistration: dict[str, Any] = Field(default_factory=dict)
    sequence_digest: str | None = None
    sequence_length: int = Field(ge=0)
    detection_metrics_identical_across_arms: bool = Field(
        description="Proof that feedback reordered the queue and did not touch the detector")
    arms: list[ArmResultOut] = Field(default_factory=list)
    deltas: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="B_minus_A, C_minus_A, C_minus_B")
    movement: dict[str, dict[str, MovementGroup] | None] = Field(default_factory=dict)
    guardrails_prevented: dict[str, Any] = Field(
        default_factory=dict,
        description="As measured. Zero everywhere means the guardrails did not bind on this "
                    "sequence — a result, not a failed run")


class EvaluationDetectionMetrics(ApiModel):
    """``GET /api/evaluation/runs/{runId}/detection`` — the confusion view S14 renders."""

    alerts: int = Field(ge=0)
    attacks: int = Field(ge=0)
    macro_f1: float
    per_class: dict[str, ClassMetrics] = Field(default_factory=dict)
    flagged_vs_benign: ClassMetrics
    precision_at: list[PrecisionAtK] = Field(default_factory=list)
    saturation: SaturationMetrics
    signature_override: SignatureOverridePreservation
