"""Canonical data contracts — plan step S2, the keystone every later step reads and writes.

Field names are the TDM §7.2 column names, so the SQLite -> PostgreSQL migration (S18) stays
mechanical. Departures from the TDM are marked ``DEVIATION:`` and logged in
``docs/plan-changelog.md`` v1.5.

Settled inputs, taken as given (``docs/HANDOVER.md`` §4 and §7):

* Eight attack classes: ``models/label-mapping.json``.
* Evidence classes from plan v1.0. ``signature_override`` has no live instances on corrected data
  (changelog v1.3) and is kept as a defensive branch.
* Five feedback categories from ``stage-5/core/feedback-engine.js``. ``duplicate`` is a queue
  action (``alerts.is_duplicate_of``), not a scoring category.
* Guardrail constants: the TDM defaults plus ``stage-5/config/adaptation-config.json``.

Contracts are immutable; derive changed copies with ``model_copy(update=...)``. Non-finite floats
are refused everywhere because JSON columns cannot store them — an ingest step that meets
``Infinity`` in a CIC feature must map it explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel

# --------------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------------

AttackClass = Literal[
    "Benign", "Botnet", "Brute Force", "DDoS", "DoS", "Infiltration", "Port Scan", "Web Attack"
]
EvidenceClass = Literal["corroborated", "signature_override", "ml_only", "none"]
# S7b (changelog v1.14): the queue band an alert sits in now, top first (decisions Q24, Q25).
# Detection places an alert in its evidence class's band or the Tier 2 band; feedback moves it.
QueueClass = Literal["tier2_candidate", "corroborated", "signature_override", "ml_only", "none"]
QUEUE_PRIORITY: dict[str, int] = {
    "tier2_candidate": 0, "corroborated": 1, "signature_override": 2, "ml_only": 3, "none": 4,
}
Severity = Literal["Critical", "High", "Medium", "Low", "Informational"]
RuleSeverity = Literal["Critical", "High", "Medium", "Low"]
AlertStatus = Literal["new", "claimed", "in_progress", "resolved", "dismissed"]
FeedbackCategory = Literal[
    "confirm_true_positive",
    "mark_false_positive",
    "mark_expected_activity",
    "needs_investigation",
    "escalate",
]
# S7b: the verdicts similar-alert learning counts, by category as feedback-engine.js counts them.
# escalate counts as a confirmation; needs_investigation is not counted.
LearningCategory = Literal["confirm_true_positive", "mark_false_positive", "mark_expected_activity"]
GuardrailAction = Literal["applied", "capped", "rejected"]
GuardrailCode = Literal[
    "non_finite_adjustment_rejected",
    "maximum_negative_adjustment_capped",
    "maximum_increase_capped",
    "critical_alert_floor",
    "infiltration_alert_floor",
    "signature_ml_disagreement_review_preserved",
    # S7 (changelog v1.10): invariant I3, and the 0-100 bound when guardrails are switched off.
    "signature_override_feedback_immune",
    "score_range_clamped",
]
Role = Literal["security_analyst", "system_admin", "evaluator"]
UserStatus = Literal["active", "inactive"]
ModelStatus = Literal["active", "available", "archived"]
DetectionRunStatus = Literal["pending", "running", "completed", "aborted"]
EvaluationRunStatus = Literal["pending", "running", "completed", "failed"]
AuditEventType = Literal[
    "LOGIN",
    "LOGOUT",
    "DETECTION_RUN",
    "FEEDBACK",
    "FEEDBACK_AMEND",
    "GUARDRAIL_INTERVENTION",
    "GUARDRAIL_REJECTION",
    # S7b: a verdict changed its family's learning (similar-alert learning).
    "SIMILAR_ALERT_LEARNING",
    "ALERT_STATUS_CHANGE",
    "ALERT_DUPLICATE",
    "CONFIG_CHANGE",
    "RULE_CREATE",
    "RULE_UPDATE",
    "MODEL_STATUS_CHANGE",
    "EVALUATION_RUN",
]

Score = Annotated[float, Field(ge=0, le=100)]
Probability = Annotated[float, Field(ge=0, le=1)]
Port = Annotated[int, Field(ge=0, le=65535)]

SIGNATURE_EVIDENCE = frozenset({"corroborated", "signature_override"})
ML_EVIDENCE = frozenset({"corroborated", "ml_only"})

# Label metadata that must never reach a detector. A superset of the inference leakage guard
# (packages/detection/ml/inference.py FORBIDDEN_PREDICTION_FIELDS) — a test pins that relation.
LEAKAGE_FIELDS = frozenset({
    "Attempted Category",
    "attack_class",
    "is_attempted",
    "Label",
    "rawLabel",
    "attackType",
    "mappedAttackType",
    "trueAttackType",
    "groundTruth",
    "severity",
    "similarityKey",
})
_LEAKAGE_FOLDED = frozenset(field.casefold() for field in LEAKAGE_FIELDS)

# Seeded into guardrail_config and snapshotted into detection_runs.guardrail_config.
GUARDRAIL_DEFAULTS: dict[str, tuple[float, str]] = {
    # TDM §7.2.11 defaults.
    "max_feedback_reduction": (
        30, "Largest score reduction one feedback event may apply (magnitude)"),
    "critical_alert_floor": (
        70, "Negative feedback cannot push a Critical alert below this score"),
    "critical_alert_threshold": (80, "Score at or above which an alert is critical"),
    "learned_exception_min_occurrences": (
        3, "Minimum occurrences before a learned exception (TDM)"),
    "learned_exception_min_confidence": (
        60, "Minimum confidence (%) for a learned exception (TDM)"),
    # Plan S2: the third guardrail in feedback-engine.js that plan v0.2 had dropped.
    "infiltration_alert_floor": (
        75, "Negative feedback cannot push an Infiltration alert below this score"),
    # stage-5/config/adaptation-config.json. The docs omit a positive cap entirely; without it
    # repeated confirmations inflate a score without bound.
    "max_feedback_increase": (
        20, "Largest score increase one feedback event may apply"),
    "review_threshold": (70, "adaptation-config guardrails.reviewThreshold"),
    "high_risk_threshold": (70, "adaptation-config guardrails.highRiskThreshold"),
    "aggregation_min_feedback_count": (
        3, "Similar feedback events required before aggregated adaptation"),
    "aggregation_min_agreement_ratio": (0.67, "Analyst agreement ratio for a moderate adjustment"),
    "aggregation_strong_agreement_ratio": (0.80, "Analyst agreement ratio for a strong adjustment"),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    """Strict base: unknown fields are errors, instances are immutable, floats are finite."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ProducerContract(BaseModel):
    """Base for records emitted by ``packages/detection/ml/inference.py``.

    Accepts the producer's camelCase keys or snake_case names, and drops producer keys outside
    the contract (e.g. ``baseRiskScore``, marked legacy by its own producer).
    """

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        allow_inf_nan=False,
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
    )


# --------------------------------------------------------------------------------------------
# Signature rules — condition format shared with scripts/retune_rules.py and the frozen
# legacy fixture: scalar = equality, {"oneOf": [...]} = membership, {"min"/"max"} = inclusive
# range. A rule's clauses are ANDed.
# --------------------------------------------------------------------------------------------


class OneOfCondition(Contract):
    one_of: list[int | float | str] = Field(alias="oneOf", min_length=1)

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {"oneOf": self.one_of}


class RangeCondition(Contract):
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _bounded(self) -> RangeCondition:
        if self.min is None and self.max is None:
            raise ValueError("a range condition needs min, max, or both")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("range condition has min > max")
        return self

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        return {bound: value for bound, value in (("min", self.min), ("max", self.max))
                if value is not None}


ConditionValue = OneOfCondition | RangeCondition | int | float | str


class SignatureRule(Contract):
    """TDM §7.2.3 ``signature_rules``."""

    id: int | None = None
    rule_id: str = Field(min_length=1, max_length=50)  # DEVIATION: TDM's 20 is too short
    name: str = Field(min_length=1, max_length=200)
    severity: RuleSeverity
    conditions: dict[str, ConditionValue] = Field(min_length=1)
    enabled: bool = True
    version: str = Field(min_length=1, max_length=50)
    created_at: AwareDatetime = Field(default_factory=utc_now)
    # DEVIATION: the class a match asserts; corroboration compares it with the ML class.
    attack_category: AttackClass
    # DEVIATION: the human-checkable reason for the rule — the signature layer is the trust half
    # of the hybrid (changelog v1.3).
    rationale: str | None = None

    @field_validator("attack_category")
    @classmethod
    def _asserts_an_attack(cls, value: str) -> str:
        if value == "Benign":
            raise ValueError("a signature rule must assert an attack class, not Benign")
        return value


class MatchedCondition(Contract):
    """One satisfied clause, with the observed value, so an analyst can check it against the flow."""

    feature: str = Field(min_length=1)
    expected: ConditionValue
    observed: int | float | str


class SignatureMatch(Contract):
    """One rule firing on one flow. Stored as an element of ``alerts.signature_rules``."""

    rule_id: str = Field(min_length=1, max_length=50)  # DEVIATION: TDM's 20 is too short
    version: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1)
    attack_category: AttackClass
    severity: RuleSeverity
    matched_conditions: list[MatchedCondition] = Field(min_length=1)


# --------------------------------------------------------------------------------------------
# ML prediction and TreeSHAP explanation — the shape inference.py already emits.
# --------------------------------------------------------------------------------------------


class ShapAttribution(ProducerContract):
    feature_name: str
    feature_value: float
    shap_contribution: float
    direction: Literal["supports_prediction", "opposes_prediction"]


class AdditivityCheck(ProducerContract):
    passed: bool
    difference: float
    tolerance: float


class MlExplanation(ProducerContract):
    """Native TreeSHAP for the predicted class. Stored whole in ``alerts.shap_attributions``."""

    status: Literal["available", "unavailable"]
    reason: str | None = None
    method: str
    output_space: str | None = None
    explained_class: AttackClass | None = None
    explained_class_index: int | None = None
    base_value: float | None = None
    raw_model_margin: float | None = None
    top_supporting_features: list[ShapAttribution] = Field(default_factory=list)
    top_opposing_features: list[ShapAttribution] = Field(default_factory=list)
    additivity_check: AdditivityCheck | None = None

    @model_validator(mode="after")
    def _available_means_verified(self) -> MlExplanation:
        # NFR-01: an explanation is shown only if its SHAP values reconstruct the model margin.
        if self.status == "available" and not (self.additivity_check and self.additivity_check.passed):
            raise ValueError("an available explanation must carry a passed additivity check")
        if self.status == "unavailable" and not self.reason:
            raise ValueError("an unavailable explanation must state its reason")
        return self


class MlPrediction(ProducerContract):
    record_id: str = Field(alias="id", min_length=1)
    prediction_status: Literal["available", "unavailable"]
    failure_reason: str | None = None
    predicted_class_index: int | None = None
    predicted_class: AttackClass | None = Field(default=None, alias="predictedAttackType")
    model_confidence: Probability | None = None
    class_probabilities: dict[AttackClass, Probability] | None = None
    second_best_class: AttackClass | None = None
    prediction_margin: float | None = None
    model_provenance: dict[str, str] = Field(default_factory=dict)
    explanation: MlExplanation = Field(alias="mlExplanation")

    @model_validator(mode="after")
    def _available_means_complete(self) -> MlPrediction:
        if self.prediction_status == "available" and (
            self.predicted_class is None or self.model_confidence is None
        ):
            raise ValueError("an available prediction needs predicted_class and model_confidence")
        return self


# --------------------------------------------------------------------------------------------
# Table models, in foreign-key order.
# --------------------------------------------------------------------------------------------


class User(Contract):
    """TDM §7.2.1. Real authentication is deferred to S18; S10 uses a stub."""

    id: int | None = None
    username: str = Field(min_length=1, max_length=100)
    password_hash: str = Field(min_length=1, repr=False)
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=255)
    role: Role
    status: UserStatus = "active"
    created_at: AwareDatetime = Field(default_factory=utc_now)
    last_login: AwareDatetime | None = None
    require_pw_change: bool = False
    one_time_pw: str | None = Field(default=None, repr=False)


class Dataset(Contract):
    """TDM §7.2.2."""

    id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=50)
    source_file: str = Field(min_length=1, max_length=500)
    preparation_meta: dict[str, Any] | None = None
    total_records: int = Field(ge=0)
    class_distribution: dict[str, Any]
    is_held_out: bool = False
    created_at: AwareDatetime = Field(default_factory=utc_now)
    created_by: int | None = None


class MlModel(Contract):
    """TDM §7.2.4."""

    id: int | None = None
    version: str = Field(min_length=1, max_length=50)
    model_type: str = Field(min_length=1, max_length=50)
    f1_score: Probability | None = None
    precision: Probability | None = None
    recall: Probability | None = None
    model_file: str = Field(min_length=1, max_length=500)
    status: ModelStatus = "available"
    created_at: AwareDatetime = Field(default_factory=utc_now)


class DetectionRun(Contract):
    """TDM §7.2.5."""

    id: int | None = None
    dataset_id: int
    model_version: str = Field(min_length=1, max_length=50)
    rule_set_version: str = Field(min_length=1, max_length=50)
    # TDM column name kept for the migration. It holds the fusion configuration snapshot, not a
    # weight vector: weighted-sum fusion was REJECTED (changelog v1.0).
    fusion_weights: dict[str, Any]
    guardrail_config: dict[str, float]
    status: DetectionRunStatus = "pending"
    alert_count: int = Field(default=0, ge=0)
    started_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: AwareDatetime | None = None
    # DEVIATION: S9's run_detection(..., seed) must be reproducible from this row alone.
    seed: int | None = None

    @model_validator(mode="after")
    def _completed_has_end(self) -> DetectionRun:
        if self.status == "completed" and self.completed_at is None:
            raise ValueError("a completed run needs completed_at")
        return self


class Alert(Contract):
    """TDM §7.2.6 — one scored flow. Every flow in a run becomes an alert, including those no
    detector flagged (evidence class ``none``)."""

    id: int | None = None
    alert_ref: UUID = Field(default_factory=uuid4)
    dataset_id: int
    run_id: int
    combined_score: Score
    severity: Severity
    confidence: Probability
    signature_severity: Probability | None = None
    ml_probability: Probability | None = None
    signature_rules: list[SignatureMatch] | None = None
    ml_predicted_class: AttackClass | None = None
    attack_category: AttackClass | None = None
    shap_attributions: MlExplanation | None = None
    explanation: str = Field(min_length=1)
    status: AlertStatus = "new"
    owner_id: int | None = None
    is_duplicate_of: int | None = None
    is_critical: bool = False
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)
    # DEVIATION: the immutable score detection produced. combined_score is the operational score
    # feedback moves; the engine measures its caps and floors against this one.
    detection_score: Score
    # DEVIATION (plan v1.0): load-bearing — the queue orders by these (db.QUEUE_ORDER_BY).
    evidence_class: EvidenceClass
    evidence_priority: int = Field(ge=0)
    # DEVIATION: raised by fusion (plan S6) or by feedback and guardrails (plan S7).
    requires_review: bool = False
    # DEVIATION (S7b): the queue band the alert sits in now, which the queue orders by
    # (db.QUEUE_ORDER_BY). Detection places it in its evidence class's band or the Tier 2 band;
    # analyst feedback moves it (Q24). evidence_class never changes. Omitted, both default to the
    # evidence class's band.
    queue_class: QueueClass
    queue_priority: int = Field(ge=0)
    # DEVIATION (S7b): the alert's similar-alert family (feedback.learning.family_key). None keeps
    # the alert out of similar-alert learning.
    family_key: str | None = Field(default=None, min_length=2)

    @model_validator(mode="before")
    @classmethod
    def _queue_defaults_to_the_evidence_band(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if data.get("queue_class") is None:
                data["queue_class"] = data.get("evidence_class")
            if data.get("queue_priority") is None:
                data["queue_priority"] = QUEUE_PRIORITY.get(data["queue_class"])
        return data

    @model_validator(mode="after")
    def _evidence_matches_detectors(self) -> Alert:
        # Necessary conditions only. How S6 assigns classes and priorities is S6's to specify.
        signature_fired = bool(self.signature_rules)
        if signature_fired != (self.evidence_class in SIGNATURE_EVIDENCE):
            raise ValueError(
                f"evidence_class {self.evidence_class!r} contradicts the signature matches: "
                f"a signature {'fired' if signature_fired else 'did not fire'}"
            )
        if self.evidence_class in ML_EVIDENCE and self.ml_predicted_class in (None, "Benign"):
            raise ValueError(
                f"evidence_class {self.evidence_class!r} needs an ML attack prediction, "
                f"got {self.ml_predicted_class!r}"
            )
        if self.id is not None and self.is_duplicate_of == self.id:
            raise ValueError("an alert cannot be a duplicate of itself")
        if self.queue_priority != QUEUE_PRIORITY[self.queue_class]:
            raise ValueError(f"queue_priority {self.queue_priority} is not the priority of "
                             f"queue_class {self.queue_class!r}")
        # I3: a rule the model disputes stays in its own band - feedback can neither demote it
        # nor make it a Tier 2 candidate (a disputed rule goes to the administrator first).
        if self.evidence_class == "signature_override" and self.queue_class != "signature_override":
            raise ValueError("a signature_override alert never leaves its queue band (I3)")
        return self


class FlowRecord(Contract):
    """TDM §7.2.9 ``flow_data`` — one network flow, 1:1 with its alert.

    ``flow_features`` is the full CICFlowMeter vector under corrected-dataset column names.
    Ground truth never enters it: ``Attempted Category`` states whether an attack succeeded, a
    leakage vector that arrived with the corrected release (changelog v1.1).
    """

    id: int | None = None
    alert_id: int | None = None  # None until the parent alert is persisted
    src_ip: str = Field(min_length=1, max_length=45)
    dst_ip: str = Field(min_length=1, max_length=45)
    src_port: Port
    dst_port: Port
    protocol: str = Field(min_length=1, max_length=10)
    duration: float = Field(ge=0)  # seconds; the CIC "Flow Duration" feature is microseconds
    packets: int = Field(ge=0)
    bytes: int = Field(ge=0)
    flow_features: dict[str, float | int | str | None]
    # DEVIATION: the flow's id in its source dataset — the only join key to ground truth, which
    # is kept out of this schema entirely.
    source_record_id: str = Field(min_length=1)

    @field_validator("flow_features")
    @classmethod
    def _no_label_fields(cls, features: dict[str, Any]) -> dict[str, Any]:
        leaked = sorted(key for key in features if key.casefold() in _LEAKAGE_FOLDED)
        if leaked:
            raise ValueError(f"flow_features carries label fields {leaked}; "
                             "ground truth must never reach a detector")
        return features


def _check_guardrail_action(action: str, requested: float, actual: float) -> None:
    if action == "applied" and actual != requested:
        raise ValueError("'applied' means the requested delta was applied unchanged")
    if action == "capped" and actual == requested:
        raise ValueError("'capped' means the applied delta differs from the requested one")
    if action == "rejected" and actual != 0:
        raise ValueError("'rejected' means no delta was applied (actual_delta = 0)")


class FeedbackEvent(Contract):
    """TDM §7.2.7. Append-only: an amendment is a new row naming ``amended_from_id``."""

    id: int | None = None
    alert_id: int
    user_id: int
    # DEVIATION: the engine's five categories, not the TDM's six (see module docstring).
    category: FeedbackCategory
    note: str | None = None
    original_score: Score
    requested_delta: float
    actual_delta: float
    guardrail_action: GuardrailAction
    guardrail_reason: str | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)
    amended_from_id: int | None = None

    @model_validator(mode="after")
    def _delta_matches_action(self) -> FeedbackEvent:
        _check_guardrail_action(self.guardrail_action, self.requested_delta, self.actual_delta)
        if self.guardrail_action != "applied" and not self.guardrail_reason:
            raise ValueError("capped or rejected feedback must state guardrail_reason")
        if not 0 <= self.original_score + self.actual_delta <= 100:
            raise ValueError("original_score + actual_delta leaves the 0-100 score range")
        return self


class AlertNote(Contract):
    """An analyst's note on an alert (console rebuild, B2). Append-only, like verdicts: a correction
    is a new note, so the thread stays the record of what was known when."""

    id: int | None = None
    alert_id: int
    user_id: int
    body: str = Field(min_length=1, max_length=2000)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class GuardrailIntervention(Contract):
    code: GuardrailCode
    configured_value: float
    original_value: float | None = None
    applied_value: float | None = None


class GuardrailOutcome(Contract):
    """One proposed adjustment after the guardrails (S7). Not a table: persisted as
    ``feedback_events.{requested_delta, actual_delta, guardrail_action, guardrail_reason}`` and
    in full inside ``audit_log.details``."""

    score_before: Score
    requested_delta: float
    actual_delta: float
    score_after: Score
    action: GuardrailAction
    interventions: list[GuardrailIntervention] = Field(default_factory=list)
    requires_review: bool = False

    @model_validator(mode="after")
    def _action_is_explained(self) -> GuardrailOutcome:
        _check_guardrail_action(self.action, self.requested_delta, self.actual_delta)
        if self.action != "applied" and not self.interventions:
            raise ValueError("a capped or rejected outcome must list the interventions behind it")
        return self


class AlertFamily(Contract):
    """DEVIATION (S7b): one family's similar-alert learning (``packages/detection/feedback/
    learning.py``). Derived state, recomputed from the family's effective verdicts after every
    verdict - so, unlike ``feedback_events``, it is updated in place, and every change is audited
    as ``SIMILAR_ALERT_LEARNING``."""

    id: int | None = None
    family_key: str = Field(min_length=2)
    attack_category: AttackClass | None = None
    scheme: str = Field(min_length=1)
    severity_version: str = Field(min_length=1)
    weight: Probability
    feedback_counts: dict[LearningCategory, int]
    dominant_category: LearningCategory | None = None
    agreement_ratio: Probability
    gate_open: bool
    gate_reason: str = Field(min_length=1)
    # What the family has learned (formula C1, movement M1) ...
    learned_adjustment: float
    learned_offset: int
    # ... and what of it reaches the queue: nothing while the gate is shut.
    applied_adjustment: float
    applied_offset: int
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _a_shut_gate_applies_nothing(self) -> AlertFamily:
        if any(count < 0 for count in self.feedback_counts.values()):
            raise ValueError("feedback counts cannot be negative")
        if not self.gate_open and (self.applied_adjustment or self.applied_offset):
            raise ValueError("a family whose gate is shut applies no learning")
        return self


_AUDIT_REQUIRED_LINKS: dict[str, tuple[str, ...]] = {
    "LOGIN": ("actor_id",),
    "LOGOUT": ("actor_id",),
    "FEEDBACK": ("actor_id", "alert_id", "feedback_id"),
    "FEEDBACK_AMEND": ("actor_id", "alert_id", "feedback_id"),
    "GUARDRAIL_INTERVENTION": ("alert_id", "feedback_id"),
    "GUARDRAIL_REJECTION": ("alert_id", "feedback_id"),
    "SIMILAR_ALERT_LEARNING": ("actor_id", "alert_id", "feedback_id"),
    "ALERT_STATUS_CHANGE": ("alert_id",),
    "ALERT_DUPLICATE": ("alert_id",),
}


class AuditEntry(Contract):
    """TDM §7.2.8. Append-only, enforced by database triggers (schema.sql)."""

    id: int | None = None
    event_type: AuditEventType
    actor_id: int | None = None
    alert_id: int | None = None
    feedback_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _links_present(self) -> AuditEntry:
        missing = [f for f in _AUDIT_REQUIRED_LINKS.get(self.event_type, ()) if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.event_type} audit entries must set {missing}")
        return self


class GuardrailConfigEntry(Contract):
    """TDM §7.2.11."""

    id: int | None = None
    config_key: str = Field(min_length=1, max_length=100)
    config_value: float
    description: str | None = None
    updated_at: AwareDatetime = Field(default_factory=utc_now)


class EvaluationScenario(Contract):
    """TDM §7.2.12. Holds S15's scripted feedback and the guardrails-on/off switch (D9)."""

    id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    dataset_id: int
    model_version: str = Field(min_length=1, max_length=50)
    rule_set_version: str = Field(min_length=1, max_length=50)
    feedback_sequence: list[dict[str, Any]]
    metrics_config: dict[str, Any]
    guardrails_active: bool = True
    created_at: AwareDatetime = Field(default_factory=utc_now)


class EvaluationRun(Contract):
    """TDM §7.2.13."""

    id: int | None = None
    scenario_id: int
    status: EvaluationRunStatus = "pending"
    metrics: dict[str, Any] | None = None
    fpr_reduction: float | None = None
    rank_improvement: float | None = None
    guardrail_pass: bool | None = None
    usability_data: dict[str, Any] | None = None
    started_at: AwareDatetime = Field(default_factory=utc_now)
    completed_at: AwareDatetime | None = None
