"""The analyst's surface: the queue, one alert's evidence, and the feedback loop (plan step S10a).

These five endpoints are the demo. Everything else in the API exists to support them.

**The list item carries both scores.** ``detectionScore`` is what detection produced and never
changes; ``combinedScore`` is what feedback moves. The dashboard's second score column is the
demo's whole point, and an endpoint that returns one number cannot show it (`deviations.md` C13).

**The detail response is four evidence panels, not a row dump** — flow, signature, model, and the
combined explanation — because S12 renders exactly those four, including their empty states
("no rule matched (ML-only alert)"). An alert no detector flagged is a legitimate response, not a
404: every flow becomes an alert (`deviations.md` C11).

**The feedback response must tell the guardrail story.** Not the final score — the whole chain:
what the analyst asked for, what bound it, what was actually applied, and what the family learned.
S12 draws `original → requested Δ → guardrail bound → actual Δ → final` directly from this shape.
A response returning only the new score would make the guardrails invisible, and the guardrails are
the project's safety claim.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from apps.api.contract.common import Actor, ApiModel
from packages.contracts import models as m

# --------------------------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------------------------


class AlertSummary(ApiModel):
    """One row of the analyst queue.

    Everything here is what a triage decision needs at a glance. Anything requiring a second
    thought belongs in the detail response, not in a 50-row list.
    """

    alert_ref: UUID = Field(description="Public identity. Row ids are never exposed")
    created_at: datetime
    updated_at: datetime

    # The two score columns, and the band that orders them.
    detection_score: m.Score = Field(description="Immutable: what detection produced")
    combined_score: m.Score = Field(description="Operational: what analyst feedback moves")
    severity: m.Severity
    confidence: m.Probability

    queue_class: m.QueueClass = Field(
        description="The band the alert sits in now; feedback moves this (Q24)")
    queue_priority: int = Field(ge=0, description="Sort key for queue_class; lower is higher")
    evidence_class: m.EvidenceClass = Field(
        description="What evidence exists. Never changes, and is never sorted on")

    attack_category: m.AttackClass | None = Field(
        default=None, description="The class the system assigned; null when nothing flagged it")
    status: m.AlertStatus
    requires_review: bool
    is_critical: bool
    has_feedback: bool = Field(description="Whether any analyst verdict has been recorded")
    matched_rule_ids: list[str] = Field(
        default_factory=list, description="Empty for an ML-only or unflagged alert")

    # Enough of the flow to recognise it in a list.
    src_ip: str
    dst_ip: str
    dst_port: int = Field(ge=0, le=65535)
    protocol: str
    source_record_id: str = Field(
        description="The flow's id in its source dataset (e.g. AL-00478): the short, stable name "
                    "an analyst reads aloud in a demo. An identifier, not a label (S12)")
    flow_time: str | None = Field(
        default=None, description="When the flow was captured, as the dataset recorded it "
                                  "(capture-local, no timezone)")
    owner: Actor | None = Field(default=None, description="Who is working the alert; null when "
                                                         "nobody owns it")
    family_size: int = Field(default=0, ge=0, description="Alerts in this alert's family, itself "
                                                         "included; 0 when it has no family")


# --------------------------------------------------------------------------------------------
# One alert — the four evidence panels
# --------------------------------------------------------------------------------------------


class FlowPanel(ApiModel):
    """Panel 1 — what the flow was."""

    src_ip: str
    dst_ip: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    protocol: str
    duration_seconds: float = Field(ge=0)
    packets: int = Field(ge=0)
    bytes: int = Field(ge=0)
    source_record_id: str = Field(
        description="The flow's id in its source dataset. The evaluation's only join to ground "
                    "truth; exposed for traceability, and it carries no label")
    features: dict[str, float | int | str | None] = Field(
        default_factory=dict,
        description="The CICFlowMeter vector under corrected-release column names")


class RuleMatchPanel(ApiModel):
    """One rule that fired."""

    rule_id: str
    name: str
    severity: m.RuleSeverity
    attack_category: m.AttackClass | None = None
    rationale: str | None = None
    matched_conditions: list[dict[str, object]] = Field(
        default_factory=list, description="Field, operator and observed value, per clause")


class SignaturePanel(ApiModel):
    """Panel 2 — what the rules said. ``matched`` empty is the ML-only empty state."""

    matched: list[RuleMatchPanel] = Field(default_factory=list)
    rule_set_version: str | None = None
    severity_score: m.Probability | None = Field(
        default=None, description="Highest matched rule severity, 0-1; null when nothing matched")
    note: str | None = Field(
        default=None,
        description="Empty-state text for the panel, e.g. 'no rule matched (ML-only alert)'")


class ShapFeature(ApiModel):
    feature_name: str
    feature_value: float | int | str | None = None
    shap_contribution: float
    direction: str = Field(description="supports_prediction | opposes_prediction")


class MlPanel(ApiModel):
    """Panel 3 — what the model said, and why (NFR-01).

    ``additivityPassed`` is not decoration: it is the check that the explanation actually explains
    this prediction. 5,000/5,000 pass on the demo sample.
    """

    predicted_class: m.AttackClass | None = None
    probability: m.Probability | None = None
    model_version: str | None = None
    explanation_status: str | None = None
    top_supporting: list[ShapFeature] = Field(default_factory=list)
    top_opposing: list[ShapFeature] = Field(default_factory=list)
    base_value: float | None = None
    raw_margin: float | None = None
    additivity_passed: bool | None = None
    note: str | None = Field(default=None, description="Empty-state text when no prediction exists")


class EvidencePanel(ApiModel):
    """Panel 4 — how the two were combined, in words the analyst can repeat in a handover."""

    evidence_class: m.EvidenceClass
    queue_class: m.QueueClass
    explanation: str = Field(min_length=1)
    fusion_scheme: str | None = None
    agreement: bool = Field(description="True when rule and model both flagged this flow")
    tier2_candidate: bool = Field(
        description="Would be escalated to Tier 2 (Q25 — the demo shows the marker; automatic "
                    "escalation is post-demo)")


class FamilyPanel(ApiModel):
    """What the alert's family has learned (S7b) — why an alert nobody touched may have moved."""

    family_key: str | None = None
    members: int = Field(default=0, ge=0)
    gate_open: bool = False
    gate_reason: str | None = None
    dominant_category: m.LearningCategory | None = None
    agreement_ratio: m.Probability | None = None
    applied_adjustment: float = 0.0
    applied_offset: int = 0
    note: str | None = Field(
        default=None, description="Why this alert's score differs from its detection score when "
                                  "it has no verdict of its own")


# --------------------------------------------------------------------------------------------
# Feedback — the write path. Never delegated: it invokes the guardrails.
# --------------------------------------------------------------------------------------------


class FeedbackRequest(ApiModel):
    """``POST /api/alerts/{alertRef}/feedback``.

    Five scoring categories. ``duplicate`` is deliberately absent — it is a *queue action*
    (link to the original, suppress from the active queue), not a score change, and the documents'
    "six categories" folds the two together (`deviations.md` A6).
    """

    category: m.FeedbackCategory
    note: str | None = Field(default=None, max_length=2000)


class GuardrailInterventionOut(ApiModel):
    """One guardrail that acted, named so the UI can explain it rather than show a bare number."""

    code: m.GuardrailCode
    configured_value: float
    original_value: float | None = None
    applied_value: float | None = None
    explanation: str = Field(min_length=1)


class ScoreAdjustment(ApiModel):
    """The chain S12 visualises: original → requested → bound → actual → final.

    Also returned on its own by ``GET /api/alerts/{alertRef}/score-adjustment``, so the screen can
    re-read it without re-submitting a verdict.
    """

    detection_score: m.Score = Field(
        description="The immutable base every adjustment measures from")
    score_before: m.Score
    requested_delta: float
    actual_delta: float
    score_after: m.Score
    action: m.GuardrailAction = Field(description="applied | capped | rejected")
    interventions: list[GuardrailInterventionOut] = Field(default_factory=list)
    requires_review: bool
    queue_class_before: m.QueueClass
    queue_class_after: m.QueueClass
    summary: str = Field(min_length=1,
                         description="One sentence stating what happened and what bound it")


class FamilyEffect(ApiModel):
    """What this verdict taught the alerts like it. Zero members moved is a normal answer — the
    gate needs three verdicts before it opens."""

    family_key: str | None = None
    gate_open: bool = False
    gate_reason: str | None = None
    members_moved: int = Field(default=0, ge=0)
    guardrail_interventions: dict[str, int] = Field(default_factory=dict)


class FeedbackRecord(ApiModel):
    """One recorded verdict. Append-only: an amendment is a new record citing the one it replaces."""

    feedback_ref: int = Field(description="Sequence of the event, for ordering in the history view")
    category: m.FeedbackCategory
    note: str | None = None
    actor: Actor
    created_at: datetime
    adjustment: ScoreAdjustment
    amended_from: int | None = Field(
        default=None, description="The verdict this one supersedes, if any")


class AlertDetail(ApiModel):
    """``GET /api/alerts/{alertRef}`` — the summary plus the four panels and the family."""

    alert: AlertSummary
    flow: FlowPanel
    signature: SignaturePanel
    ml: MlPanel
    evidence: EvidencePanel
    family: FamilyPanel
    feedback_count: int = Field(ge=0)
    current_feedback: FeedbackRecord | None = None


class FeedbackResponse(ApiModel):
    """What the analyst sees the moment they submit."""

    alert: AlertSummary
    feedback: FeedbackRecord
    family: FamilyEffect
    audit_event_ids: list[int] = Field(
        default_factory=list, description="Audit entries this one action wrote")


class FeedbackHistory(ApiModel):
    """``GET /api/alerts/{alertRef}/feedback-history`` — oldest first, amendments included."""

    alert_ref: UUID
    events: list[FeedbackRecord] = Field(default_factory=list)
    effective: FeedbackRecord | None = Field(
        default=None, description="The verdict currently in force; feedback does not stack")


# --------------------------------------------------------------------------------------------
# Triage — status, owner and notes (console rebuild B1, B2). Workflow, not judgement: none of these
# moves a score, touches a family or invokes a guardrail.
# --------------------------------------------------------------------------------------------


class StatusChangeRequest(ApiModel):
    """``POST /api/alerts/{alertRef}/status``.

    Working an alert (`claimed`, `in_progress`) makes the caller its owner when it has none;
    returning it to `new` releases it; a closed alert (`resolved`, `dismissed`) can only be reopened
    to `in_progress`. A refused transition is a 409.
    """

    status: m.AlertStatus
    reason: str | None = Field(default=None, max_length=500)


class AssignRequest(ApiModel):
    """``POST /api/alerts/{alertRef}/assign``.

    `me` assigns the caller's demo user (the auth stub: there is one demo user per role); `null`
    unassigns. Assigning a `new` alert claims it; unassigning a `claimed` alert releases it.
    """

    owner: Literal["me"] | None
    reason: str | None = Field(default=None, max_length=500)


class TriageResponse(ApiModel):
    alert: AlertSummary
    audit_event_id: int = Field(ge=0, description="The ALERT_STATUS_CHANGE entry this wrote")


class NoteRequest(ApiModel):
    """``POST /api/alerts/{alertRef}/notes``. Append-only: a correction is a new note."""

    body: str = Field(min_length=1, max_length=2000)


class NoteOut(ApiModel):
    note_id: int
    author: Actor
    body: str
    created_at: datetime


class AlertNotes(ApiModel):
    """``GET /api/alerts/{alertRef}/notes`` — the whole thread, oldest first."""

    alert_ref: UUID
    notes: list[NoteOut] = Field(default_factory=list)
