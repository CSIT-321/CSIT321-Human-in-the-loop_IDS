"""Direct analyst feedback (plan step S7): one verdict -> guardrails -> stored, audited, re-scored.

``submit_feedback(conn, alert_id=..., user_id=..., category=...)`` is one transaction: the verdict
becomes an append-only ``feedback_events`` row, the alert's ``combined_score`` and
``requires_review`` change, and the audit trail gains a ``FEEDBACK`` entry — plus a ``GUARDRAIL_*``
entry whenever a guardrail intervened. Any failure rolls all of it back.

Semantics ported from ``stage-5/core/feedback-engine.js`` (``applyDirectFeedback``):

* A verdict does not stack. It supersedes the alert's previous verdict (``amended_from_id``), and
  the alert's current score is ``detection_score`` + the guarded change of the latest verdict.
* The requested change per category is the engine's: +10 / -30 / -15 / 0 / +15.
* The review flag is the category's own flag, a guardrail's, or S6's rule re-applied to the new
  score. The engine's separate ``reviewThreshold`` (70) is not used: S6 made one threshold drive
  severity, ``is_critical`` and review.

Decided in changelog v1.10: ``uncertain`` is folded into ``needs_investigation`` (identical effect —
no change, forces review); ``duplicate`` is a queue action (``alerts.is_duplicate_of``), not
feedback. Similar-alert learning — a verdict on one alert adjusting similar ones — is S7b.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import get_args

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter
from packages.detection.guardrail.policy import GuardrailPolicy, apply_guardrails


@dataclass(frozen=True)
class FeedbackEffect:
    requested_delta: float
    forces_review: bool
    meaning: str


FEEDBACK_EFFECTS: dict[str, FeedbackEffect] = {
    "confirm_true_positive": FeedbackEffect(10, True, "confirmed as a true positive"),
    "mark_false_positive": FeedbackEffect(-30, False, "marked as a false positive"),
    "mark_expected_activity": FeedbackEffect(-15, False, "marked as expected activity"),
    "needs_investigation": FeedbackEffect(0, True, "needs continued investigation"),
    "escalate": FeedbackEffect(15, True, "escalated for higher-priority review"),
}
assert set(FEEDBACK_EFFECTS) == set(get_args(m.FeedbackCategory))


@dataclass(frozen=True)
class FeedbackResult:
    feedback: m.FeedbackEvent
    alert: m.Alert
    outcome: m.GuardrailOutcome
    audit: list[m.AuditEntry]


def load_policy(conn: sqlite3.Connection, *, active: bool = True) -> GuardrailPolicy:
    """The guardrail settings as the administrator last configured them."""
    rows = {row["config_key"]: row["config_value"]
            for row in conn.execute("SELECT config_key, config_value FROM guardrail_config")}
    return GuardrailPolicy.from_rows(rows, active=active)


def current_feedback(conn: sqlite3.Connection, alert_id: int) -> m.FeedbackEvent | None:
    """The alert's effective verdict: its latest feedback event."""
    row = conn.execute("SELECT * FROM feedback_events WHERE alert_id = ? "
                       "ORDER BY created_at DESC, id DESC LIMIT 1", (alert_id,)).fetchone()
    return None if row is None else db.from_row(m.FeedbackEvent, row)


def fusion_review(alert: m.Alert, score: float, critical_threshold: float) -> bool:
    """S6's review rule, re-applied to a new score."""
    if alert.evidence_class == "signature_override" or alert.ml_predicted_class is None:
        return True
    return alert.evidence_class in ("corroborated", "ml_only") and score >= critical_threshold


def submit_feedback(conn: sqlite3.Connection, *, alert_id: int, user_id: int, category: str,
                    note: str | None = None, policy: GuardrailPolicy | None = None,
                    now: datetime | None = None) -> FeedbackResult:
    """Record one analyst verdict and re-score its alert inside the guardrails. Commits."""
    if category not in FEEDBACK_EFFECTS:
        raise ValueError(f"unknown feedback category {category!r}; "
                         f"expected one of {sorted(FEEDBACK_EFFECTS)}")
    alert = db.get(conn, m.Alert, alert_id)
    if alert is None:
        raise LookupError(f"no alert with id {alert_id}")
    effect = FEEDBACK_EFFECTS[category]
    policy = policy if policy is not None else load_policy(conn)
    now = now if now is not None else m.utc_now()

    outcome = apply_guardrails(alert, effect.requested_delta, policy)
    previous = current_feedback(conn, alert_id)
    event = m.FeedbackEvent(
        alert_id=alert_id, user_id=user_id, category=category, note=note,
        original_score=alert.detection_score, requested_delta=outcome.requested_delta,
        actual_delta=outcome.actual_delta, guardrail_action=outcome.action,
        guardrail_reason="; ".join(item.code for item in outcome.interventions) or None,
        created_at=now, amended_from_id=previous.id if previous else None)
    requires_review = (effect.forces_review or outcome.requires_review
                       or fusion_review(alert, outcome.score_after,
                                        policy.critical_alert_threshold))

    with conn:  # one transaction: commits on success, rolls back on any exception
        feedback_id = db.insert(conn, event)
        conn.execute("UPDATE alerts SET combined_score = ?, requires_review = ?, updated_at = ? "
                     "WHERE id = ?", (outcome.score_after, int(requires_review),
                                      db.format_timestamp(now), alert_id))
        writer = AuditWriter(conn)
        audit = [writer.feedback(user_id, alert_id, feedback_id, category=category,
                                 rationale=note)]
        if outcome.interventions:
            audit.append(writer.guardrail(outcome, alert_id=alert_id, feedback_id=feedback_id,
                                          actor_id=user_id))

    return FeedbackResult(feedback=db.get(conn, m.FeedbackEvent, feedback_id),
                          alert=db.get(conn, m.Alert, alert_id), outcome=outcome, audit=audit)
