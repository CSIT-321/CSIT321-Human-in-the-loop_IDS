"""The three-arm evaluation (plan step S15, tasks 2 and 4).

    A - control          no feedback      guardrails on    what the system does unaided
    B - treatment        scripted         guardrails on    the claim being tested
    C - guardrail probe  same scripted    guardrails OFF   what the guardrails prevented

**How the arms are pinned.** Dataset, model version, rule-set version and seed must be identical
across the three. They are not re-derived and compared afterwards - each arm is a **byte copy of
one detection database**, so identity is structural rather than promised, and the only two things
that then differ are the feedback sequence and ``guardrails_active``. Re-running detection three
times would be weaker: it would put the whole pipeline's determinism between the arms and the
comparison, and a difference would be ambiguous.

**What "guardrails off" means.** ``GuardrailPolicy(active=False)`` - the switch S7a already has
(``guardrail/policy.py`` step 0). Only the 0-100 score range still binds. One consequence is worth
stating plainly rather than discovering later: the I3 filter inside ``refresh_family`` is
structural, not policy-driven, so a ``signature_override`` alert teaches its family nothing even in
arm C. Arm C measures what the *score* guardrails prevented, not what a system without S7b's
family rules would do.

**Reproducibility (NFR-05)** is by construction: verdict timestamps come from the pre-registered
sequence (``scenario.EPOCH`` + n seconds), never from the clock, so two runs of the same scenario
produce identical metrics. ``tests/test_evaluation.py`` runs the harness twice and compares.

The exit criterion is the plan's v0.3 one: whatever arm C shows is recorded **as measured**. A
suppression count of zero means the guardrails did not bind on this sequence, which is a result,
not a failed run, and it is never grounds for re-sampling.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.feedback.service import load_learning_policy, load_policy, submit_feedback
from packages.detection.pipeline.store import alert_by_source_record
from packages.detection.ranking.severity import load_severity_chart
from packages.evaluation import metrics as mx
from packages.evaluation.scenario import (
    EPOCH,
    Preregistration,
    build_sequence,
    ensure_evaluator,
    pinned_run_config,
    register_scenario,
    sequence_digest,
)
from packages.evaluation.truth import GroundTruth

HITL = Path(__file__).resolve().parents[2]
RESULTS = HITL / "evaluation" / "three-arm"


@dataclass(frozen=True)
class Arm:
    """One arm of the experiment: the two variables, and nothing else."""

    name: str
    feedback: bool
    guardrails: bool
    purpose: str


ARMS = (
    Arm("A-control", feedback=False, guardrails=True,
        purpose="what the system does unaided"),
    Arm("B-treatment", feedback=True, guardrails=True,
        purpose="the claim being tested"),
    Arm("C-guardrails-off", feedback=True, guardrails=False,
        purpose="what the guardrails prevented"),
)


@dataclass(frozen=True)
class ArmResult:
    """One arm, as run and as stored."""

    arm: Arm
    database: Path
    scenario_id: int
    run_id: int
    verdicts: int
    metrics: dict[str, Any]
    deltas: dict[str, Any] = field(default_factory=dict)
    guardrail_pass: bool = True

    def row(self) -> dict[str, Any]:
        """The arm's headline numbers, for a printed summary or a report table."""
        queue, safety = self.metrics["queue"], self.metrics["safety"]
        return {
            "arm": self.arm.name, "feedback": self.arm.feedback,
            "guardrails": self.arm.guardrails, "verdicts": self.verdicts,
            "precision_at_50": queue["precision_at"]["50"]["precision"],
            "false_positives_in_top_50": queue["false_positives_in_top_50"],
            "mrr_true_positives": queue["mrr_true_positives"],
            "mean_rank_true_positives": queue["mean_rank_true_positives"],
            "critical_preservation_rate": safety["critical_preservation_rate"],
            "critical_floor_breaches": safety["critical_floor_breaches"],
            "signature_override_alerts": safety["signature_override"]["alerts"],
            "guardrail_actions": safety["guardrail_actions"],
            "guardrail_pass": self.guardrail_pass,
        }


def _commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HITL,
                                capture_output=True, text=True, timeout=10, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def apply_sequence(conn: sqlite3.Connection, sequence: list[dict[str, Any]], *, user_id: int,
                   guardrails: bool) -> int:
    """Replay the pre-registered verdicts into one arm. Returns how many were applied.

    The verdict's own pinned timestamp is used, so the effective-verdict order is the sequence's
    order and nothing depends on how fast the machine is.
    """
    policy = load_policy(conn, active=guardrails)
    learning = load_learning_policy(conn)
    chart = load_severity_chart()
    applied = 0
    for entry in sequence:
        alert = alert_by_source_record(conn, entry["source_record_id"])
        if alert is None:
            raise LookupError(f"the pre-registered sequence names source record "
                              f"{entry['source_record_id']!r}, which this database does not hold")
        submit_feedback(conn, alert_id=alert.id, user_id=user_id, category=entry["category"],
                        note=f"S15 scripted verdict #{entry['position']}", policy=policy,
                        learning=learning, chart=chart,
                        now=EPOCH + timedelta(seconds=int(entry["position"])))
        applied += 1
    return applied


def guardrail_pass(metrics: dict[str, Any]) -> bool:
    """Did every safety invariant hold in this arm? Critical floors held, I3 held, no true positive
    pushed below the score it was detected at.

    ``score_range_clamped`` is deliberately **not** a failure. It fires whenever a confirming
    verdict is applied to an alert already at 100, which on this dataset is almost every alert the
    queue puts in front of an analyst; counting it as a breach would report a safety failure every
    time the system worked correctly.

    This is a *measurement*, not an assertion: arm C is expected to be able to fail it, and a pass
    there means the guardrails never bound on this sequence.
    """
    safety = metrics["safety"]
    return (safety["critical_floor_breaches"] == 0
            and safety["signature_override"]["changed"] == 0
            and safety["true_positives_suppressed"] == 0)


def run_arm(baseline: Path, arm: Arm, sequence: list[dict[str, Any]], truth: GroundTruth, *,
            workdir: Path, rule: Preregistration,
            control_queue: list[mx.QueuedAlert] | None = None) -> ArmResult:
    """Copy the detection database, run this arm over the copy, score it, and store the run."""
    workdir.mkdir(parents=True, exist_ok=True)
    database = workdir / f"eval-{arm.name}.db"
    shutil.copy2(baseline, database)

    applied = 0
    conn = db.connect(database)
    try:
        pinned = pinned_run_config(conn)
        threshold = float(pinned["guardrail_config"]["critical_alert_threshold"])
        user_id = ensure_evaluator(conn)
        scenario_id = register_scenario(
            conn, name=f"S15 {arm.name}", sequence=sequence if arm.feedback else [],
            metrics_config={"preregistration": rule.snapshot(),
                            "sequence_digest": sequence_digest(sequence),
                            "precision_at": list(mx.PRECISION_AT),
                            "ground_truth": truth.source, "purpose": arm.purpose,
                            "pinned": {k: pinned[k] for k in
                                       ("detection_run_id", "dataset_id", "model_version",
                                        "rule_set_version", "seed")}},
            guardrails_active=arm.guardrails, dataset_id=pinned["dataset_id"],
            model_version=pinned["model_version"],
            rule_set_version=pinned["rule_set_version"])
        run_id = db.insert(conn, m.EvaluationRun(scenario_id=scenario_id, status="running",
                                                 started_at=EPOCH))
        conn.commit()

        if arm.feedback:
            applied = apply_sequence(conn, sequence, user_id=user_id, guardrails=arm.guardrails)

        queue = mx.read_queue(conn, truth)
        control = control_queue if control_queue is not None else queue
        scored = mx.score_arm(conn, truth, critical_threshold=threshold, control=control,
                              sequence=sequence if arm.feedback else None)
        passed = guardrail_pass(scored)
        conn.execute(
            "UPDATE evaluation_runs SET status = ?, metrics = ?, guardrail_pass = ?, "
            "completed_at = ? WHERE id = ?",
            ("completed", json.dumps(scored, sort_keys=True), int(passed),
             db.format_timestamp(EPOCH), run_id))
        conn.commit()
    finally:
        conn.close()

    return ArmResult(arm=arm, database=database, scenario_id=scenario_id, run_id=run_id,
                     verdicts=applied, metrics=scored, guardrail_pass=passed)


@dataclass
class Evaluation:
    """All three arms, their deltas, and the provenance that makes them re-runnable."""

    run_id: str
    baseline: Path
    sequence: list[dict[str, Any]]
    rule: Preregistration
    arms: list[ArmResult]
    pinned: dict[str, Any]
    detection_identical: bool
    commit: str | None = None

    @property
    def by_name(self) -> dict[str, ArmResult]:
        return {result.arm.name: result for result in self.arms}

    def results(self) -> dict[str, Any]:
        control, treatment, probe = (self.by_name[arm.name] for arm in ARMS)
        return {
            "run_id": self.run_id,
            "commit": self.commit,
            "baseline_database": str(self.baseline),
            "preregistration": self.rule.snapshot(),
            "sequence_digest": sequence_digest(self.sequence),
            "sequence_length": len(self.sequence),
            "pinned": self.pinned,
            "detection_metrics_identical_across_arms": self.detection_identical,
            "arms": [result.row() for result in self.arms],
            "deltas": {
                "B_minus_A": mx.deltas(control.metrics, treatment.metrics),
                "C_minus_A": mx.deltas(control.metrics, probe.metrics),
                "C_minus_B": mx.deltas(treatment.metrics, probe.metrics),
            },
            "movement": {
                "B-treatment": treatment.metrics.get("movement"),
                "C-guardrails-off": probe.metrics.get("movement"),
            },
            "guardrails_prevented": guardrails_prevented(treatment, probe),
            "full_metrics": {result.arm.name: result.metrics for result in self.arms},
        }


def guardrails_prevented(treatment: ArmResult, probe: ArmResult) -> dict[str, Any]:
    """What arm C did that arm B did not - the guardrails' measured effect.

    Reported as measured. Zero everywhere means the guardrails never bound on this sequence: a
    publishable result (plan S15 exit criteria), not a reason to strengthen the sequence.
    """
    b, c = treatment.metrics["safety"], probe.metrics["safety"]
    return {
        "critical_floor_breaches_in_C": c["critical_floor_breaches"],
        "critical_floor_breaches_in_B": b["critical_floor_breaches"],
        "extra_breaches_without_guardrails": (c["critical_floor_breaches"]
                                              - b["critical_floor_breaches"]),
        "true_positives_suppressed_in_C": c["true_positives_suppressed"],
        "true_positives_suppressed_in_B": b["true_positives_suppressed"],
        "extra_suppressions_without_guardrails": (c["true_positives_suppressed"]
                                                  - b["true_positives_suppressed"]),
        "guardrail_actions_in_B": b["guardrail_actions"],
        "guardrail_actions_in_C": c["guardrail_actions"],
        "signature_override_changed_in_C": c["signature_override"]["changed"],
        "guardrail_pass": {"B-treatment": treatment.guardrail_pass,
                           "C-guardrails-off": probe.guardrail_pass},
    }


def evaluate(baseline: str | Path, *, truth: GroundTruth | None = None,
             rule: Preregistration | None = None, workdir: str | Path | None = None,
             run_id: str | None = None) -> Evaluation:
    """Run all three arms over one detection database and return the comparison."""
    baseline = Path(baseline)
    if not baseline.exists():
        raise FileNotFoundError(f"{baseline} - build it with scripts/run_detection.py")
    truth = truth if truth is not None else GroundTruth.load()
    rule = rule if rule is not None else Preregistration()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    workdir = Path(workdir) if workdir is not None else baseline.parent

    conn = db.connect(baseline)
    try:
        pinned = pinned_run_config(conn)
        sequence = build_sequence(conn, truth, rule=rule)
    finally:
        conn.close()
    if not sequence:
        raise ValueError("the pre-registration rule selected no alerts; the arms would be "
                         "identical and the experiment vacuous")

    results: list[ArmResult] = []
    control_queue: list[mx.QueuedAlert] | None = None
    for arm in ARMS:
        result = run_arm(baseline, arm, sequence, truth, workdir=workdir, rule=rule,
                         control_queue=control_queue)
        if control_queue is None:  # the first arm is the control every later arm is measured from
            control_conn = db.connect(result.database)
            try:
                control_queue = mx.read_queue(control_conn, truth)
            finally:
                control_conn.close()
        results.append(result)

    detection = [json.dumps(result.metrics["detection"], sort_keys=True) for result in results]
    return Evaluation(run_id=run_id, baseline=baseline, sequence=sequence, rule=rule,
                      arms=results, pinned=pinned,
                      detection_identical=len(set(detection)) == 1, commit=_commit())


def export(evaluation: Evaluation, *, root: Path = RESULTS) -> Path:
    """Write the run the way ``evaluation/ranking/`` is written: a directory per run, plus a line
    in ``history.jsonl``. Returns the run's directory."""
    directory = root / "runs" / evaluation.run_id
    directory.mkdir(parents=True, exist_ok=True)
    results = evaluation.results()
    (directory / "config.json").write_text(json.dumps({
        "run_id": evaluation.run_id, "commit": evaluation.commit,
        "baseline_database": str(evaluation.baseline),
        "preregistration": evaluation.rule.snapshot(),
        "sequence_digest": sequence_digest(evaluation.sequence),
        "pinned": evaluation.pinned,
        "arms": [{"name": arm.name, "feedback": arm.feedback, "guardrails": arm.guardrails,
                  "purpose": arm.purpose} for arm in ARMS],
        "feedback_sequence": evaluation.sequence,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    history = root / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "run_id": evaluation.run_id, "commit": evaluation.commit,
        "preregistration": evaluation.rule.rule,
        "sequence_digest": sequence_digest(evaluation.sequence)[:16],
        "sequence_length": len(evaluation.sequence),
        "detection_identical": evaluation.detection_identical,
        "arms": [arm.row() for arm in evaluation.arms],
        "deltas": results["deltas"],
        "guardrails_prevented": results["guardrails_prevented"],
    }
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")
    return directory
