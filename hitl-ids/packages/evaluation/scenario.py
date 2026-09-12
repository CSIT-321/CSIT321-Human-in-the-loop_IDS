"""The pre-registered feedback sequence (plan step S15, task 1).

**Why this file exists at all.** Plan v0.2 set the exit criterion "run C shows >= 1 critical
suppression that run B prevents (if zero, the scripted sequence is too weak - strengthen it)".
That instructs tuning the experiment until it yields the wanted answer. v0.3 struck it out and
replaced it with pre-registration: the sequence is **defined by a rule written down before any arm
runs**, it is derived deterministically from the database, and whatever it then shows is the
result - including nothing.

The rule (``s15-preregistration-1``), in full:

1. **Domain.** Alerts a detector flagged, i.e. every queue band except ``none``, in the queue's own
   contract order (``db.QUEUE_ORDER_BY``). This is the order an analyst actually works down, so the
   scripted analyst triages what the system puts in front of them, not a hand-picked slice.
2. **Subset, by construction.** At most ``max_per_family`` alerts from any one family, and only
   from families with at least ``min_family_size`` members. Every touched family therefore keeps
   untouched members, which is the only way an effect on *similar* alerts is measurable at all
   (S7b's whole claim). ``max_per_family`` must be >= the gate's ``min_feedback_count`` or no
   family could ever open its gate and the treatment arm would be inert by construction.
3. **Size.** The first ``size`` alerts satisfying 1 and 2.
4. **Category, from ground truth** - an *oracle* analyst, never wrong:
   benign -> ``mark_false_positive``; attack of chart severity >= ``escalate_at`` (7.0, CVSS High
   and above) -> ``escalate``; any other attack -> ``confirm_true_positive``.
5. **Order.** Queue order. Each verdict is timestamped ``EPOCH + n seconds`` so replaying the
   sequence is bit-identical across runs (NFR-05) and the effective-verdict order is unambiguous.

The oracle analyst is a deliberate ceiling, and must be reported as one: it measures what the
mechanism can do when the feedback is perfect, not what it does with a fallible analyst. Analyst
error is a separate arm, not yet run.

Nothing in this module reads a result. It cannot: it is imported before any arm executes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.ranking.formulas import TIER2_SEVERITY
from packages.detection.ranking.severity import SeverityChart, load_severity_chart
from packages.evaluation.truth import GroundTruth

#: The rule's identifier. Change the rule, change this, and say so in the changelog.
PREREGISTRATION = "s15-preregistration-1"

#: Verdict timestamps are pinned, not wall-clock: two runs of the same scenario must produce the
#: same bytes. Detection's own timestamps are untouched.
EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

#: The queue's order, qualified for a join against flow_data (both tables have an `id`), as
#: db.QUEUE_ORDER_BY's own comment requires.
QUEUE_ORDER_QUALIFIED = "a.queue_priority ASC, a.combined_score DESC, a.id ASC"

#: The evaluator the scripted verdicts are attributed to. A real analyst's verdicts are S10's.
EVALUATOR_USERNAME = "s15-evaluator"


@dataclass(frozen=True)
class Preregistration:
    """The rule above, as numbers. Recorded with every run; never tuned against a result."""

    size: int = 40
    max_per_family: int = 5
    min_family_size: int = 8
    escalate_at: float = TIER2_SEVERITY
    rule: str = PREREGISTRATION

    def snapshot(self) -> dict[str, Any]:
        return {"rule": self.rule, "size": self.size, "max_per_family": self.max_per_family,
                "min_family_size": self.min_family_size, "escalate_at": self.escalate_at}


def category_for(attack_type: str, chart: SeverityChart, escalate_at: float) -> str:
    """Rule 4: the verdict an oracle analyst would give this flow."""
    if attack_type == "Benign":
        return "mark_false_positive"
    try:
        severity = chart.severity(attack_type)
    except KeyError:  # a capture class the chart does not model: still an attack, still confirmed
        severity = 0.0
    return "escalate" if severity >= escalate_at else "confirm_true_positive"


def build_sequence(conn: sqlite3.Connection, truth: GroundTruth, *,
                   rule: Preregistration | None = None,
                   chart: SeverityChart | None = None) -> list[dict[str, Any]]:
    """Derive the pre-registered sequence from a detection database. Deterministic and pure: it
    reads the queue and ground truth, and writes nothing."""
    rule = rule if rule is not None else Preregistration()
    chart = chart if chart is not None else load_severity_chart()

    sizes = {row["family_key"]: int(row["n"]) for row in conn.execute(
        "SELECT family_key, COUNT(*) AS n FROM alerts WHERE family_key IS NOT NULL "
        "GROUP BY family_key")}
    rows = conn.execute(
        "SELECT a.id, a.alert_ref, a.family_key, a.queue_class, a.combined_score, "
        "a.attack_category, a.evidence_class, f.source_record_id "
        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        "WHERE a.queue_class != 'none' AND a.family_key IS NOT NULL "
        "ORDER BY " + QUEUE_ORDER_QUALIFIED)

    taken: dict[str, int] = {}
    sequence: list[dict[str, Any]] = []
    for row in rows:
        if len(sequence) >= rule.size:
            break
        family = row["family_key"]
        if sizes.get(family, 0) < rule.min_family_size:
            continue
        if taken.get(family, 0) >= rule.max_per_family:
            continue
        taken[family] = taken.get(family, 0) + 1
        record = truth.of(row["source_record_id"])
        sequence.append({
            "position": len(sequence),
            "source_record_id": row["source_record_id"],
            "alert_ref": str(row["alert_ref"]),
            "family_key": family,
            "queue_class": row["queue_class"],
            "detection_queue_score": row["combined_score"],
            "predicted_class": row["attack_category"],
            "evidence_class": row["evidence_class"],
            "ground_truth": record.attack_type,
            "category": category_for(record.attack_type, chart, rule.escalate_at),
            "at": db.format_timestamp(EPOCH + timedelta(seconds=len(sequence))),
        })
    return sequence


def sequence_digest(sequence: list[dict[str, Any]]) -> str:
    """A stable fingerprint of the sequence, so a run can prove it used the pre-registered one."""
    payload = json.dumps(sequence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def ensure_evaluator(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """The evaluator user the scripted verdicts belong to. Idempotent on the username."""
    row = conn.execute("SELECT id FROM users WHERE username = ?",
                       (EVALUATOR_USERNAME,)).fetchone()
    if row is not None:
        return int(row["id"])
    return db.insert(conn, m.User(
        username=EVALUATOR_USERNAME, password_hash="not-a-login-account",
        display_name="S15 scripted evaluator", email="s15-evaluator@evaluation.local",
        role="evaluator", created_at=now if now is not None else EPOCH))


def register_scenario(conn: sqlite3.Connection, *, name: str, sequence: list[dict[str, Any]],
                      metrics_config: dict[str, Any], guardrails_active: bool,
                      dataset_id: int, model_version: str, rule_set_version: str,
                      now: datetime | None = None) -> int:
    """Store one arm's scenario row. The three arms differ in exactly two fields - the sequence
    (empty for the control) and ``guardrails_active`` - and that is the experiment."""
    return db.insert(conn, m.EvaluationScenario(
        name=name, dataset_id=dataset_id, model_version=model_version,
        rule_set_version=rule_set_version, feedback_sequence=sequence,
        metrics_config=metrics_config, guardrails_active=guardrails_active,
        created_at=now if now is not None else EPOCH))


def pinned_run_config(conn: sqlite3.Connection) -> dict[str, Any]:
    """Dataset, model, rules and seed as the detection run recorded them - the quantities that must
    be identical across all three arms. Read from ``detection_runs``, not from a caller's argument,
    so the pinning is a property of the database being evaluated, not of a promise."""
    row = conn.execute("SELECT * FROM detection_runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise LookupError("the database holds no detection run to evaluate")
    return {"detection_run_id": int(row["id"]), "dataset_id": int(row["dataset_id"]),
            "model_version": row["model_version"], "rule_set_version": row["rule_set_version"],
            "seed": row["seed"], "fusion_weights": json.loads(row["fusion_weights"]),
            "guardrail_config": json.loads(row["guardrail_config"])}
