"""Complementary Evidence Fusion, re-specified for the trust/triage model (plan step S6).

Notebook 03 specified CEF when the detectors looked complementary. On corrected data they are not
(changelog v1.2-v1.3): the signature layer adds no detections, it adds a reason a human can check.
The evidence classes, the scores and the invariants survive. Three things changed, logged in
changelog v1.8:

* ``corroborated`` requires the model to agree on the *class*. A rule whose class the model
  contradicts is not corroboration (v1.6: 23 NMAP probes of TCP/21 matched the FTP rule); it is
  ``signature_override`` - a checkable claim the model disputes, so always reviewed.
* The model's malicious probability is ``1 - P(Benign)``. The notebook used the predicted class's
  confidence, which understates it whenever probability is split between attack classes.
* One critical threshold - the guardrails' ``critical_alert_threshold`` - sets severity
  "Critical", ``is_critical`` and the review flag, so the three can never disagree.

Specification
-------------
::

    sig   = max(severity_scores[match.severity] for each signature match), 0 when none matched
    ml    = 1 - P(Benign), 0 when the model's prediction is unavailable

    evidence_class
        corroborated        a rule matched, and the model predicts a class a matching rule asserts
        signature_override  a rule matched, and the model does not predict any matching rule's class
        ml_only             no rule matched, and the model predicts an attack
        none                otherwise
    combined_score          (0-100, rounded to 2 places as the TDM's DECIMAL(5,2) stores it)
        corroborated        min(100, max(sig, ml) * 100 + agreement_bonus)
        signature_override  sig * 100
        ml_only, none       ml * 100
    requires_review
        signature_override            always                                   (I2)
        corroborated, ml_only         when combined_score >= critical_threshold
        every class                   when the model's prediction is unavailable
    severity                none -> Informational; otherwise Critical >= critical_threshold,
                            High >= 70, Medium >= 40, else Low (bands from stage-4 fusion-engine.js)
    evidence_priority       corroborated 0 . signature_override 1 . ml_only 2 . none 3   (Q22)
    queue                   ORDER BY evidence band, then combined_score DESC - db.QUEUE_ORDER_BY,
                            whose queue_priority is this band until S7b moves the alert

Invariants, tested in tests/test_fusion.py:
    I1  a signature match never leaves the score below sig * 100
    I2  signature_override is always review-flagged
    I3  feedback cannot decay signature_override - S7 enforces it, not fusion
    I4  fuse() is a pure function of its inputs: no clock, no randomness, no I/O
    I5  no signature_override alert ranks below any ml_only alert
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from packages.contracts import models as m
from packages.detection.signature.engine import format_number, readable_condition

SCHEME = "cef-trust-v1.8"
EVIDENCE_PRIORITY: dict[str, int] = {
    "corroborated": 0, "signature_override": 1, "ml_only": 2, "none": 3,
}
DEFAULT_SEVERITY_SCORES: dict[str, float] = {
    "Low": 0.40, "Medium": 0.60, "High": 0.80, "Critical": 0.95,
}
HIGH_BAND = 70.0
MEDIUM_BAND = 40.0

VERDICTS = {
    "corroborated": ("A signature rule and the model agree on {category}. The rule's conditions "
                     "below can be checked against the flow."),
    "signature_override": ("A signature rule asserts {category}, but the model does not confirm "
                           "it. The rule's conditions are checkable against the flow; review "
                           "which is right."),
    "ml_only": ("Only the model flagged this flow ({category}). No rule gives a checkable "
                "reason, so review the model's evidence."),
    "none": "No detector flagged this flow.",
}


class FusionConfig(m.Contract):
    """The parameters that replace the TDM's inert weights. Snapshotted into
    ``detection_runs.fusion_weights`` so a run can be replayed."""

    agreement_bonus: float = Field(default=5.0, ge=0, le=100)
    critical_threshold: float = Field(
        default=m.GUARDRAIL_DEFAULTS["critical_alert_threshold"][0], ge=0, le=100)
    severity_scores: dict[m.RuleSeverity, m.Probability] = Field(
        default_factory=lambda: dict(DEFAULT_SEVERITY_SCORES))

    @model_validator(mode="after")
    def _every_severity_scored(self) -> FusionConfig:
        missing = set(DEFAULT_SEVERITY_SCORES) - set(self.severity_scores)
        if missing:
            raise ValueError(f"severity_scores lacks {sorted(missing)}")
        return self

    def snapshot(self) -> dict[str, Any]:
        return {"scheme": SCHEME, "evidence_priority": dict(EVIDENCE_PRIORITY),
                **self.model_dump(mode="json")}

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> FusionConfig:
        if snapshot.get("scheme") != SCHEME:
            raise ValueError(f"snapshot scheme {snapshot.get('scheme')!r} is not {SCHEME!r}")
        return cls.model_validate({key: value for key, value in snapshot.items()
                                   if key not in ("scheme", "evidence_priority")})


class FusionDecision(m.Contract):
    """Everything fusion decides about one flow. Carries no timestamps, so fuse() stays pure."""

    combined_score: m.Score
    severity: m.Severity
    confidence: m.Probability
    signature_severity: m.Probability | None
    ml_probability: m.Probability | None
    signature_rules: list[m.SignatureMatch] | None
    ml_predicted_class: m.AttackClass | None
    attack_category: m.AttackClass | None
    shap_attributions: m.MlExplanation | None
    explanation: str = Field(min_length=1)
    is_critical: bool
    evidence_class: m.EvidenceClass
    evidence_priority: int = Field(ge=0)
    requires_review: bool

    def to_alert(self, *, dataset_id: int, run_id: int, created_at: datetime) -> m.Alert:
        """The contract's Alert; ``detection_score`` freezes the score fusion produced."""
        return m.Alert(
            dataset_id=dataset_id, run_id=run_id, detection_score=self.combined_score,
            created_at=created_at, updated_at=created_at,
            **{name: getattr(self, name) for name in type(self).model_fields})


def fuse(matches: Sequence[m.SignatureMatch], prediction: m.MlPrediction | None,
         config: FusionConfig | None = None) -> FusionDecision:
    """Fuse one flow's signature matches and model prediction into a decision."""
    config = config if config is not None else FusionConfig()
    available = prediction is not None and prediction.prediction_status == "available"
    predicted = prediction.predicted_class if available else None
    ml = _malicious_probability(prediction) if available else 0.0
    sig = max((config.severity_scores[match.severity] for match in matches), default=0.0)

    if matches:
        if any(match.attack_category == predicted for match in matches):
            evidence, category = "corroborated", predicted
            score = min(100.0, max(sig, ml) * 100 + config.agreement_bonus)
        else:
            evidence = "signature_override"
            category = max(matches, key=lambda match: config.severity_scores[match.severity]
                           ).attack_category
            score = sig * 100
    elif predicted not in (None, "Benign"):
        evidence, category, score = "ml_only", predicted, ml * 100
    else:
        evidence, category, score = "none", None, ml * 100
    score = round(score, 2)

    critical = score >= config.critical_threshold
    requires_review = (evidence == "signature_override" or not available
                       or (evidence in ("corroborated", "ml_only") and critical))
    if evidence == "corroborated":
        confidence = max(sig, prediction.model_confidence)
    elif evidence == "signature_override":
        confidence = sig
    else:
        confidence = prediction.model_confidence if available else 0.0

    return FusionDecision(
        combined_score=score,
        severity=_severity(evidence, score, config),
        confidence=confidence,
        signature_severity=sig if matches else None,
        ml_probability=ml if available else None,
        signature_rules=list(matches) or None,
        ml_predicted_class=predicted,
        attack_category=category,
        shap_attributions=prediction.explanation if prediction is not None else None,
        explanation=_explanation(evidence, category, matches, prediction, available, ml),
        is_critical=critical,
        evidence_class=evidence,
        evidence_priority=EVIDENCE_PRIORITY[evidence],
        requires_review=requires_review,
    )


def queue_key(alert: FusionDecision | m.Alert) -> tuple[int, float]:
    """Python mirror of ``db.QUEUE_ORDER_BY`` for alerts still in their evidence band - neither the
    Tier 2 criteria nor feedback has moved them (S7b). A stable sort keeps input order for ties,
    as ``id ASC`` does for alerts inserted in that order."""
    return (alert.evidence_priority, -alert.combined_score)


def _malicious_probability(prediction: m.MlPrediction) -> float:
    probabilities = prediction.class_probabilities
    if probabilities and "Benign" in probabilities:
        return min(1.0, max(0.0, 1.0 - probabilities["Benign"]))
    confidence = prediction.model_confidence or 0.0
    return confidence if prediction.predicted_class != "Benign" else 1.0 - confidence


def _severity(evidence: str, score: float, config: FusionConfig) -> str:
    if evidence == "none":
        return "Informational"
    if score >= config.critical_threshold:
        return "Critical"
    if score >= HIGH_BAND:
        return "High"
    if score >= MEDIUM_BAND:
        return "Medium"
    return "Low"


def _observed(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number(value)
    return str(value)


def _explanation(evidence: str, category: str | None, matches: Sequence[m.SignatureMatch],
                 prediction: m.MlPrediction | None, available: bool, ml: float) -> str:
    parts = [VERDICTS[evidence].format(category=category)]
    for match in matches:
        clauses = "; ".join(
            f"{readable_condition(condition.feature, condition.expected)} "
            f"(observed {_observed(condition.observed)})"
            for condition in match.matched_conditions)
        parts.append(f"Rule {match.rule_id} [{match.attack_category}, {match.severity}]: "
                     f"{clauses}.")
    if not available:
        reason = (prediction.failure_reason if prediction is not None and prediction.failure_reason
                  else "no prediction for this flow")
        parts.append(f"Model prediction unavailable: {reason}.")
    else:
        parts.append(f"Model: {prediction.predicted_class} (confidence "
                     f"{prediction.model_confidence:.3f}; malicious probability {ml:.3f}).")
        shap = prediction.explanation
        if shap.status == "available" and shap.top_supporting_features:
            strongest = ", ".join(
                f"{feature.feature_name} = {format_number(feature.feature_value)} "
                f"({feature.shap_contribution:+.3f})"
                for feature in shap.top_supporting_features[:3])
            parts.append(f"Strongest model evidence for {shap.explained_class}: {strongest}.")
    return " ".join(parts)
