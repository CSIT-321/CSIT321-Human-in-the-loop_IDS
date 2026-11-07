"""C1 verdict bridge: a V2 human decision on a flow alert also goes to the approved engine.

Decisions D1 and D2 (analysis/codebase-review/DECISION-BRIEF.md), user decisions 2026-11-07:
- D1: the approved engine (feedback/service.py) stays the writer of a flow alert's score: guardrails, family
  learning and the approved audit trail all run as in the approved demo.
- D2: one verdict form with the 4 V2 outcomes. On a flow alert each maps to one approved category
  (``OUTCOME_TO_CATEGORY``). Escalate is a separate action and records the approved 'escalate' (+15).
- A flow group's V2 alert is its representative's projection, so the verdict goes to that one legacy alert.
  Family learning carries it to the unjudged members of its family.
- External NIDS (Suricata) alerts have no approved-engine row: nothing is written for them.

The caller owns the transaction. The V2 verdict or escalation and the approved verdict commit together or not at
all; ``apply_feedback`` never commits.
"""
from __future__ import annotations

from packages.detection.feedback.service import FeedbackResult, apply_feedback

OUTCOME_TO_CATEGORY = {
    "confirmed_malicious": "confirm_true_positive",
    "suspicious": "needs_investigation",
    "expected_activity": "mark_expected_activity",
    "false_positive": "mark_false_positive",
}
ESCALATE = "escalate"


def _bridge(conn, alert, *, actor_id: int, category: str, note: str) -> FeedbackResult | None:
    if alert.source_kind != "legacy_flow_alert" or alert.legacy_alert_id is None:
        return None
    if not conn.in_transaction:
        raise ValueError("the verdict bridge must run inside the V2 decision's transaction")
    return apply_feedback(conn, alert_id=alert.legacy_alert_id, user_id=actor_id, category=category, note=note)


def bridge_verdict(conn, alert, *, actor_id: int, outcome: str, note: str) -> FeedbackResult | None:
    """Record the approved verdict mapped from one V2 Tier 1 verdict outcome. None for a non-flow alert."""
    return _bridge(conn, alert, actor_id=actor_id, category=OUTCOME_TO_CATEGORY[outcome], note=note)


def bridge_escalation(conn, alert, *, actor_id: int, note: str) -> FeedbackResult | None:
    """Record the approved 'escalate' (+15, guardrailed) for one human Tier 2 escalation. None for a non-flow alert."""
    return _bridge(conn, alert, actor_id=actor_id, category=ESCALATE, note=note)
