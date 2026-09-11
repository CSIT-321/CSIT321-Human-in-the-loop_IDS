"""Guardrails on analyst feedback (plan step S7) — the project's safety claim.

A requested score change passes these checks, in order, before it can touch an alert:

    0  switch   ``active=False`` applies the change raw — the evaluation's guardrails-off arm (D9).
                Only the 0-100 score range still binds.
    1  finite   a non-finite request is rejected.
    2  I3       a ``signature_override`` alert is frozen. A precision-1.000 rule the model disputes
                is either a rule regression or analyst error; either way the feedback is rejected
                and routed to the administrator instead of eroding the score.
    3  cap      the change is limited to [-max_feedback_reduction, +max_feedback_increase].
    4  floors   a negative change cannot push a Critical alert below ``critical_alert_floor``, nor
                an Infiltration alert below ``infiltration_alert_floor``.
    5  range    the result stays within 0-100.

The base is always the alert's ``detection_score``: feedback does not stack. An alert's current
score is its detection score plus the guarded change of its one effective verdict — the semantics
of ``stage-5/core/feedback-engine.js``, pinned by its test "Detection Score remains immutable after
repeated adaptation".

Ported from that engine's ``applyGuardrails`` with two deliberate differences (changelog v1.10):

* A floor protects an alert only when its base score is at or above the floor. The JS engine
  lifted a sub-floor alert *up* to the floor on negative feedback, so a "false positive" verdict
  could raise a score.
* ``signature_override`` is frozen (invariant I3); the JS engine only preserved its review flag.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import Field

from packages.contracts import models as m

POLICY_KEYS = ("max_feedback_reduction", "max_feedback_increase", "critical_alert_floor",
               "infiltration_alert_floor", "critical_alert_threshold")


def _default(key: str) -> float:
    return m.GUARDRAIL_DEFAULTS[key][0]


class GuardrailPolicy(m.Contract):
    """Guardrail settings. Loaded from ``guardrail_config`` (admin-configurable, NFR-08)."""

    active: bool = True
    max_feedback_reduction: float = Field(default=_default("max_feedback_reduction"), ge=0)
    max_feedback_increase: float = Field(default=_default("max_feedback_increase"), ge=0)
    critical_alert_floor: m.Score = _default("critical_alert_floor")
    infiltration_alert_floor: m.Score = _default("infiltration_alert_floor")
    critical_alert_threshold: m.Score = _default("critical_alert_threshold")

    @classmethod
    def from_rows(cls, rows: Mapping[str, float], *, active: bool = True) -> GuardrailPolicy:
        return cls(active=active, **{key: rows[key] for key in POLICY_KEYS if key in rows})


def critically_protected(alert: m.Alert) -> bool:
    """The Critical floor's trigger: a Critical alert, or a Critical-severity matching rule."""
    return alert.is_critical or any(match.severity == "Critical"
                                    for match in alert.signature_rules or [])


def apply_guardrails(alert: m.Alert, requested: float,
                     policy: GuardrailPolicy | None = None) -> m.GuardrailOutcome:
    """The change actually allowed when ``requested`` is proposed for ``alert``. Pure."""
    policy = policy if policy is not None else GuardrailPolicy()
    base = alert.detection_score
    interventions: list[m.GuardrailIntervention] = []

    def outcome(requested_delta: float, score: float, action: str, review: bool,
                changed: bool) -> m.GuardrailOutcome:
        actual = round(score - base, 2) if changed else requested_delta
        return m.GuardrailOutcome(
            score_before=base, requested_delta=requested_delta, actual_delta=actual,
            score_after=round(base + actual, 2), action=action, interventions=interventions,
            requires_review=review)

    if not math.isfinite(requested):
        interventions.append(m.GuardrailIntervention(
            code="non_finite_adjustment_rejected", configured_value=0))
        return outcome(0.0, base, "rejected", review=False, changed=False)

    if not policy.active:
        score = min(100.0, max(0.0, base + requested))
        changed = score != base + requested
        if changed:
            interventions.append(m.GuardrailIntervention(
                code="score_range_clamped", configured_value=score,
                original_value=round(base + requested, 2), applied_value=score))
        return outcome(requested, score, "capped" if changed else "applied", review=False,
                       changed=changed)

    if alert.evidence_class == "signature_override":
        if requested != 0:
            interventions.append(m.GuardrailIntervention(
                code="signature_override_feedback_immune", configured_value=base,
                original_value=requested, applied_value=0))
            return m.GuardrailOutcome(
                score_before=base, requested_delta=requested, actual_delta=0.0, score_after=base,
                action="rejected", interventions=interventions, requires_review=True)
        interventions.append(m.GuardrailIntervention(
            code="signature_ml_disagreement_review_preserved", configured_value=1))
        return outcome(requested, base, "applied", review=True, changed=False)

    review, changed = False, False
    capped = requested
    if capped < -policy.max_feedback_reduction:
        capped = -policy.max_feedback_reduction
        interventions.append(m.GuardrailIntervention(
            code="maximum_negative_adjustment_capped", configured_value=capped,
            original_value=requested, applied_value=capped))
        review, changed = True, True
    if capped > policy.max_feedback_increase:
        capped = policy.max_feedback_increase
        interventions.append(m.GuardrailIntervention(
            code="maximum_increase_capped", configured_value=capped,
            original_value=requested, applied_value=capped))
        changed = True

    score = base + capped
    if capped < 0:
        for code, floor, protected in (
                ("critical_alert_floor", policy.critical_alert_floor, critically_protected(alert)),
                ("infiltration_alert_floor", policy.infiltration_alert_floor,
                 alert.attack_category == "Infiltration")):
            # Hold at the floor only an alert that started at or above it: never raise a score.
            if protected and base >= floor and score < floor:
                interventions.append(m.GuardrailIntervention(
                    code=code, configured_value=floor, original_value=round(score, 2),
                    applied_value=floor))
                score = floor
                review, changed = True, True

    if not 0 <= score <= 100:
        bounded = min(100.0, max(0.0, score))
        interventions.append(m.GuardrailIntervention(
            code="score_range_clamped", configured_value=bounded, original_value=round(score, 2),
            applied_value=bounded))
        score, changed = bounded, True

    return outcome(requested, score, "capped" if changed else "applied", review=review,
                   changed=changed)
