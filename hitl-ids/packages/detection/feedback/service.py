"""Analyst feedback (plan step S7): a verdict -> guardrails -> stored, audited, re-scored - and,
since S7b, carried to the alerts like it.

``submit_feedback(conn, alert_id=..., user_id=..., category=...)`` is one transaction:

* the verdict becomes an append-only ``feedback_events`` row;
* the alert's ``combined_score``, ``requires_review`` and queue band change;
* its family's learning is recomputed and every member with no verdict of its own is re-placed
  (``refresh_family``; the design is in ``feedback/learning.py``);
* the audit trail gains a ``FEEDBACK`` entry, a ``GUARDRAIL_*`` entry whenever a guardrail
  intervened, and a ``SIMILAR_ALERT_LEARNING`` entry whenever the family's learning changed.

Any failure rolls all of it back.

Direct feedback, ported from ``stage-5/core/feedback-engine.js`` (``applyDirectFeedback``):

* A verdict does not stack. It supersedes the alert's previous verdict (``amended_from_id``), and
  the alert's current score is ``detection_score`` + the guarded change of the latest verdict.
* The requested change per category is the engine's: +10 / -30 / -15 / 0 / +15.
* The review flag is the category's own flag, a guardrail's, or S6's rule re-applied to the new
  score. The engine's separate ``reviewThreshold`` (70) is not used: S6 made one threshold drive
  severity, ``is_critical`` and review.

Decided in changelog v1.10: ``uncertain`` is folded into ``needs_investigation`` (identical effect -
no change, forces review); ``duplicate`` is a queue action (``alerts.is_duplicate_of``), not
feedback.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, get_args

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter
from packages.detection.feedback.learning import (
    SCHEME,
    LearningPolicy,
    attack_of,
    fusion_review,
    learn,
    member_placement,
    verdict_queue_class,
)
from packages.detection.fusion.cef import ceilings_from_chart, severity_for
from packages.detection.guardrail.policy import GuardrailPolicy, apply_guardrails
from packages.detection.ranking.severity import SeverityChart, load_severity_chart


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

# The effective verdict of every alert in one family - each alert's latest, as current_feedback
# chooses it - oldest first, the order the family's learning replays them in.
EFFECTIVE_VERDICTS = """
    SELECT f.* FROM feedback_events f JOIN alerts a ON a.id = f.alert_id
    WHERE a.family_key = ? AND NOT EXISTS (
        SELECT 1 FROM feedback_events g WHERE g.alert_id = f.alert_id
        AND (g.created_at > f.created_at OR (g.created_at = f.created_at AND g.id > f.id)))
    ORDER BY f.created_at, f.id"""


def _learning_state(family: m.AlertFamily) -> dict[str, Any]:
    return family.model_dump(exclude={"id", "updated_at"})


@dataclass(frozen=True)
class MemberMove:
    """One family member the learning moved — an alert nobody judged.

    This is the product's thesis made concrete, so it is recorded per alert rather than counted.
    A count ("3 alerts moved") cannot be checked, cannot be clicked through to, and cannot be shown
    to a viva panel; ``AL-00421 62.0 -> 72.0, ml_only -> tier2_candidate`` can.
    """

    alert_id: int
    alert_ref: str
    source_record_id: str
    score_before: float
    score_after: float
    queue_class_before: m.QueueClass
    queue_class_after: m.QueueClass


@dataclass(frozen=True)
class FamilyRefresh:
    """One recomputation of a family's learning (S7b)."""

    before: m.AlertFamily | None
    after: m.AlertFamily
    moves: list[MemberMove]
    # the guardrails holding the scores of the family's unjudged members, counted by code
    guardrail_interventions: dict[str, int]

    @property
    def members_moved(self) -> int:
        return len(self.moves)

    @property
    def changed(self) -> bool:
        return self.before is None or _learning_state(self.before) != _learning_state(self.after)


@dataclass(frozen=True)
class FeedbackResult:
    feedback: m.FeedbackEvent
    alert: m.Alert
    outcome: m.GuardrailOutcome
    audit: list[m.AuditEntry]
    learning: FamilyRefresh | None = None  # None when the verdict cannot teach a family


def _config_rows(conn: sqlite3.Connection) -> dict[str, float]:
    return {row["config_key"]: row["config_value"]
            for row in conn.execute("SELECT config_key, config_value FROM guardrail_config")}


def load_policy(conn: sqlite3.Connection, *, active: bool = True) -> GuardrailPolicy:
    """The guardrail settings as the administrator last configured them."""
    return GuardrailPolicy.from_rows(_config_rows(conn), active=active)


def load_learning_policy(conn: sqlite3.Connection) -> LearningPolicy:
    """The agreement gate's settings as the administrator last configured them."""
    return LearningPolicy.from_rows(_config_rows(conn))


def current_feedback(conn: sqlite3.Connection, alert_id: int) -> m.FeedbackEvent | None:
    """The alert's effective verdict: its latest feedback event."""
    row = conn.execute("SELECT * FROM feedback_events WHERE alert_id = ? "
                       "ORDER BY created_at DESC, id DESC LIMIT 1", (alert_id,)).fetchone()
    return None if row is None else db.from_row(m.FeedbackEvent, row)


def refresh_family(conn: sqlite3.Connection, family_key: str, *, policy: GuardrailPolicy,
                   learning: LearningPolicy, chart: SeverityChart,
                   now: datetime) -> FamilyRefresh:
    """Recompute one family's learning from its members' effective verdicts, store it, and
    re-place every member with no verdict of its own. Idempotent; the caller owns the transaction.

    Detection does not call this. It reads what this stored: ``runner._place`` consults
    ``alert_families`` at ingest, so an alert that arrives after the verdicts takes its family's
    learning without a wholesale replay."""
    members = {row["id"]: db.from_row(m.Alert, row) for row in conn.execute(
        "SELECT * FROM alerts WHERE family_key = ? ORDER BY id", (family_key,))}
    if not members:
        raise LookupError(f"no alert belongs to family {family_key}")
    verdicts = [db.from_row(m.FeedbackEvent, row)
                for row in conn.execute(EFFECTIVE_VERDICTS, (family_key,))]
    attack = attack_of(next(iter(members.values())))  # the attack class is part of the key
    weight = chart.weight(attack)
    result = learn((verdict.category for verdict in verdicts
                    if members[verdict.alert_id].evidence_class != "signature_override"),  # I3
                   weight, policy, learning)

    row = conn.execute("SELECT * FROM alert_families WHERE family_key = ?",
                       (family_key,)).fetchone()
    before = None if row is None else db.from_row(m.AlertFamily, row)
    candidate = m.AlertFamily(
        family_key=family_key, attack_category=attack, scheme=SCHEME,
        severity_version=chart.version, weight=weight, feedback_counts=result.counts,
        dominant_category=result.gate.dominant, agreement_ratio=result.gate.agreement,
        gate_open=result.gate.open, gate_reason=result.gate.reason,
        learned_adjustment=result.learned_adjustment, learned_offset=result.learned_offset,
        applied_adjustment=result.applied_adjustment, applied_offset=result.applied_offset,
        updated_at=now)
    if before is None:
        after = db.get(conn, m.AlertFamily, db.insert(conn, candidate))
    elif _learning_state(before) != _learning_state(candidate):
        values = db.to_row(candidate)
        del values["id"]
        assignments = ", ".join(f"{column} = ?" for column in values)
        conn.execute(f"UPDATE alert_families SET {assignments} WHERE id = ?",
                     [*values.values(), before.id])
        after = db.get(conn, m.AlertFamily, before.id)
    else:
        after = before

    ceilings = ceilings_from_chart(chart)  # the chart's ceilings, so the label matches detection
    judged = {verdict.alert_id for verdict in verdicts}
    moves: list[MemberMove] = []
    interventions = Counter()
    for alert in members.values():
        if alert.id in judged:
            continue  # its own verdict takes priority, and S7a has placed it
        place = member_placement(alert, after.applied_adjustment, after.applied_offset, chart,
                                 policy)
        if place.outcome is not None:
            interventions.update(item.code for item in place.outcome.interventions)
        if ((place.score, place.queue_class, place.requires_review)
                != (alert.combined_score, alert.queue_class, alert.requires_review)):
            conn.execute(
                "UPDATE alerts SET combined_score = ?, severity = ?, queue_class = ?, "
                "queue_priority = ?, requires_review = ?, updated_at = ? WHERE id = ?",
                (place.score,
                 severity_for(place.score, alert.attack_category, ceilings,
                              critical_threshold=policy.critical_alert_threshold),
                 place.queue_class, place.queue_priority, int(place.requires_review),
                 db.format_timestamp(now), alert.id))
            moves.append(MemberMove(
                alert_id=int(alert.id or 0), alert_ref=str(alert.alert_ref),
                source_record_id="",  # filled below: one query for the movers, never one per row
                score_before=alert.combined_score, score_after=place.score,
                queue_class_before=alert.queue_class, queue_class_after=place.queue_class))
    return FamilyRefresh(before, after, _named(conn, moves),
                         dict(sorted(interventions.items())))


def _named(conn: sqlite3.Connection, moves: list[MemberMove]) -> list[MemberMove]:
    """Attach each moved alert's source record id — the short name an analyst reads aloud.

    It lives in `flow_data`, so it is fetched once for the whole set rather than per member: a
    family can hold hundreds of alerts and a verdict must stay one fast transaction.
    """
    if not moves:
        return moves
    ids = [move.alert_id for move in moves]
    names = {int(row["alert_id"]): str(row["source_record_id"]) for row in conn.execute(
        f"SELECT alert_id, source_record_id FROM flow_data "
        f"WHERE alert_id IN ({', '.join('?' * len(ids))})", ids)}
    return [replace(move, source_record_id=names.get(move.alert_id, "")) for move in moves]


def submit_feedback(conn: sqlite3.Connection, *, alert_id: int, user_id: int, category: str,
                    note: str | None = None, policy: GuardrailPolicy | None = None,
                    learning: LearningPolicy | None = None, chart: SeverityChart | None = None,
                    now: datetime | None = None) -> FeedbackResult:
    """Record one analyst verdict, re-score its alert inside the guardrails, and carry it to the
    alert's family. Commits."""
    if category not in FEEDBACK_EFFECTS:
        raise ValueError(f"unknown feedback category {category!r}; "
                         f"expected one of {sorted(FEEDBACK_EFFECTS)}")
    alert = db.get(conn, m.Alert, alert_id)
    if alert is None:
        raise LookupError(f"no alert with id {alert_id}")
    effect = FEEDBACK_EFFECTS[category]
    policy = policy if policy is not None else load_policy(conn)
    learning = learning if learning is not None else load_learning_policy(conn)
    chart = chart if chart is not None else load_severity_chart()
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
    band = verdict_queue_class(alert, category, outcome.score_after, chart, policy)
    # I3: a disputed rule's verdict goes to the administrator; it teaches its family nothing.
    teaches = alert.family_key is not None and alert.evidence_class != "signature_override"

    with conn:  # one transaction: commits on success, rolls back on any exception
        feedback_id = db.insert(conn, event)
        conn.execute("UPDATE alerts SET combined_score = ?, severity = ?, requires_review = ?, "
                     "queue_class = ?, queue_priority = ?, updated_at = ? WHERE id = ?",
                     (outcome.score_after,
                      severity_for(outcome.score_after, alert.attack_category,
                                   ceilings_from_chart(chart),
                                   critical_threshold=policy.critical_alert_threshold),
                      int(requires_review), band, m.QUEUE_PRIORITY[band],
                      db.format_timestamp(now), alert_id))
        writer = AuditWriter(conn)
        audit = [writer.feedback(user_id, alert_id, feedback_id, category=category,
                                 rationale=note)]
        if outcome.interventions:
            audit.append(writer.guardrail(outcome, alert_id=alert_id, feedback_id=feedback_id,
                                          actor_id=user_id))
        refresh = None
        if teaches:
            refresh = refresh_family(conn, alert.family_key, policy=policy, learning=learning,
                                     chart=chart, now=now)
            if refresh.changed:
                audit.append(writer.similar_alert_learning(
                    refresh.after, before=refresh.before, actor_id=user_id, alert_id=alert_id,
                    feedback_id=feedback_id, members_moved=refresh.members_moved,
                    guardrail_interventions=refresh.guardrail_interventions,
                    moves=refresh.moves))

    return FeedbackResult(feedback=db.get(conn, m.FeedbackEvent, feedback_id),
                          alert=db.get(conn, m.Alert, alert_id), outcome=outcome, audit=audit,
                          learning=refresh)
