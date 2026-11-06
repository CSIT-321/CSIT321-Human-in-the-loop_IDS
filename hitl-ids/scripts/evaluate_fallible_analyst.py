"""
Guardrail stress test with a fallible analyst (a separate experiment, not part of S15's headline).

    python scripts/evaluate_fallible_analyst.py                  # demo.db and stress.db
    python scripts/evaluate_fallible_analyst.py --dry-run        # print the fallible sequence only
    python scripts/evaluate_fallible_analyst.py --no-export      # run and print, write nothing

**Why this exists.** The S15 three-arm evaluation could not test the guardrails
(docs/evaluation-report.md, findings 5 and 6): its scripted analyst is an oracle who is never
wrong, so no verdict ever pushed a true positive *down*, and every guardrail that could have bound
protects against downward pressure. Arm C (guardrails off) came out identical to arm B in every
metric. That is a property of the sequence, not evidence that the guardrails are unnecessary. This
script gives the guardrails something to do.

**The error model, fixed before any run (never tuned against a result).** Take the same
pre-registered oracle sequence S15 uses. Among the verdicts that confirm or escalate a real attack,
every 4th one (the 4th, 8th, 12th ... counted in sequence order) is replaced by
``mark_false_positive``: the analyst wrongly dismisses a true attack. That is 25% of the attack
verdicts, deterministic, and it is the only change. Verdicts on benign flows are left correct.

**Arms.** Unchanged from S15, via the same ``run_arm``: A control (no feedback), B (fallible
verdicts, guardrails on), C (same verdicts, guardrails off).

**Measures.** S15's ``critical_floor_breaches`` is NOT used here. It compares a score with
``critical_alert_threshold`` (80), not with the guardrail's actual floor ``critical_alert_floor``
(70), and it also counts benign alerts that were correctly dismissed, so under dismissals it
reports a floor breach when an alert merely lands on the floor. It was harmless in S15 only
because the oracle never pushed a score down. This script measures directly, on real attacks only
(ground truth), each arm against the control: how many fell in score, how many points were lost,
how many were pushed below the real critical floor (70), how many Infiltration alerts were pushed
below their floor (75), and how many of the drops hit an alert the analyst never judged
(collateral, through family learning). This replacement was decided after a first run exposed the
S15 metric's definition; the error model was not touched. It runs on both detection databases: ``demo.db`` (the real detector)
and ``data/stress.db`` (SYNTHETIC degraded detector, see build_stress_detection.py). An oracle
reference run on each database is printed beside the fallible one so the effect of the error
model is visible, not assumed.

**What a result means.** Whatever arm C shows is reported as measured. If the guardrails do not
bind, that is a result. It is also not a claim about a real analyst: 25% is a stress level
chosen for the test, not an estimate of how often analysts are wrong.

Inputs:  data/demo.db, data/stress.db (scripts/run_detection.py), data/processed/demo_ground_truth.json
Output:  evaluation/fallible-analyst/runs/<run id>/{config,results}.json and a history.jsonl line
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts import db
from packages.evaluation import harness
from packages.evaluation import metrics as mx
from packages.evaluation.harness import ARMS, Evaluation, export, run_arm
from packages.evaluation.scenario import (
    Preregistration,
    build_sequence,
    pinned_run_config,
)
from packages.evaluation.truth import GroundTruth

DEFAULT_TRUTH = HITL / "data" / "processed" / "demo_ground_truth.json"
DATABASES = {"demo": HITL / "data" / "demo.db", "stress": HITL / "data" / "stress.db"}
RESULTS = HITL / "evaluation" / "fallible-analyst"

#: The attack verdicts the oracle gives; a fallible analyst may wrongly dismiss one of these.
ATTACK_CATEGORIES = ("confirm_true_positive", "escalate")
DISMISSAL = "mark_false_positive"
ERROR_EVERY = 4
ERROR_MODEL = (f"Every {ERROR_EVERY}th attack verdict in the S15 oracle sequence is replaced by "
               f"{DISMISSAL}; benign verdicts are unchanged. 25% of attack verdicts, "
               "deterministic, fixed before any run.")


def fallible_sequence(sequence: list[dict[str, Any]], every: int = ERROR_EVERY) -> list[dict[str, Any]]:
    """The oracle sequence with every ``every``-th attack verdict wrongly turned into a dismissal."""
    out: list[dict[str, Any]] = []
    attacks_seen = 0
    for entry in sequence:
        entry = dict(entry, oracle_category=entry["category"], analyst_error=False)
        if entry["category"] in ATTACK_CATEGORIES:
            attacks_seen += 1
            if attacks_seen % every == 0:
                entry["category"] = DISMISSAL
                entry["analyst_error"] = True
        out.append(entry)
    return out


def attack_measures(control: list[mx.QueuedAlert], arm: list[mx.QueuedAlert], judged: set[str],
                    *, critical_floor: float, infiltration_floor: float) -> dict[str, Any]:
    """What an arm did to real attacks, measured against the control (arm A)."""
    before = {a.alert_id: a for a in control}
    attacks = [a for a in arm if a.malicious]
    dropped = [a for a in attacks if a.combined_score < before[a.alert_id].combined_score]
    below_critical = [a for a in attacks
                      if before[a.alert_id].combined_score >= critical_floor
                      and a.combined_score < critical_floor]
    infiltration = [a for a in attacks if a.truth_class == "Infiltration"
                    and before[a.alert_id].combined_score >= infiltration_floor
                    and a.combined_score < infiltration_floor]
    return {
        "attacks": len(attacks),
        "attacks_dropped": len(dropped),
        "points_lost": round(sum(before[a.alert_id].combined_score - a.combined_score
                                 for a in dropped), 3),
        "attacks_below_critical_floor": len(below_critical),
        "infiltration_below_floor": len(infiltration),
        "dropped_but_never_judged": sum(1 for a in dropped if a.source_record_id not in judged),
    }


def evaluate_sequence(baseline: Path, truth: GroundTruth, rule: Preregistration,
                      sequence: list[dict[str, Any]], *,
                      run_id: str) -> tuple[Evaluation, dict[str, dict[str, Any]]]:
    """S15's three arms over one database, with a given verdict sequence, plus the measures."""
    conn = db.connect(baseline)
    try:
        pinned = pinned_run_config(conn)
    finally:
        conn.close()
    results = []
    measures: dict[str, dict[str, Any]] = {}
    control_queue = None
    judged = {entry["source_record_id"] for entry in sequence}
    with tempfile.TemporaryDirectory(prefix="fallible-") as workdir:
        for arm in ARMS:
            result = run_arm(baseline, arm, sequence, truth, workdir=Path(workdir), rule=rule,
                             control_queue=control_queue)
            conn = db.connect(result.database)
            try:
                config = {row["config_key"]: row["config_value"]
                          for row in conn.execute("SELECT * FROM guardrail_config")}
                queue = mx.read_queue(conn, truth)
            finally:
                conn.close()
            if control_queue is None:
                control_queue = queue
            measures[arm.name] = attack_measures(
                control_queue, queue, judged,
                critical_floor=float(config["critical_alert_floor"]),
                infiltration_floor=float(config["infiltration_alert_floor"]))
            results.append(result)
    detection = [json.dumps(r.metrics["detection"], sort_keys=True) for r in results]
    evaluation = Evaluation(run_id=run_id, baseline=baseline, sequence=sequence, rule=rule,
                            arms=results, pinned=pinned,
                            detection_identical=len(set(detection)) == 1,
                            commit=harness._commit())
    return evaluation, measures


def summarise(label: str, evaluation: Evaluation,
              measures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    arms = {r.arm.name: r.metrics for r in evaluation.arms}
    row: dict[str, Any] = {
        "label": label, "verdicts": len(evaluation.sequence),
        "wrong_dismissals": sum(1 for e in evaluation.sequence if e.get("analyst_error"))}
    for name in ("B-treatment", "C-guardrails-off"):
        row[name] = dict(measures[name],
                         guardrail_actions=arms[name]["safety"]["guardrail_actions"])
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ground-truth", default=str(DEFAULT_TRUTH))
    parser.add_argument("--dry-run", action="store_true",
                        help="print the fallible sequence for each database; run no arm")
    parser.add_argument("--no-export", action="store_true", help="print results, write no files")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    truth = GroundTruth.load(Path(args.ground_truth))
    rule = Preregistration()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    summaries: list[dict[str, Any]] = []
    evaluations: dict[str, Evaluation] = {}

    for name, path in DATABASES.items():
        if not path.exists():
            print(f"missing {path} - build it with scripts/run_detection.py", file=sys.stderr)
            return 2
        conn = db.connect(path)
        try:
            oracle = build_sequence(conn, truth, rule=rule)
        finally:
            conn.close()
        fallible = fallible_sequence(oracle)
        if args.dry_run:
            wrong = [e for e in fallible if e["analyst_error"]]
            print(f"{name}: {len(oracle)} verdicts, {len(wrong)} wrongly dismissed "
                  f"({ERROR_MODEL})")
            for e in wrong:
                print(f"   #{e['position']:>2} {e['alert_ref']} {e['ground_truth']:<14} "
                      f"oracle={e['oracle_category']} -> {e['category']}")
            continue
        for kind, sequence in (("oracle", oracle), ("fallible", fallible)):
            label = f"{name}/{kind}"
            evaluation, measures = evaluate_sequence(path, truth, rule, sequence,
                                                     run_id=f"{run_id}-{name}-{kind}")
            evaluations[label] = evaluation
            summaries.append(summarise(label, evaluation, measures))
    if args.dry_run:
        return 0

    print(f"error model: {ERROR_MODEL}\n")
    for s in summaries:
        print(f"{s['label']:<16} verdicts={s['verdicts']} wrong_dismissals={s['wrong_dismissals']}")
        for arm in ("B-treatment", "C-guardrails-off"):
            a = s[arm]
            print(f"   {arm:<17} attacks_dropped={a['attacks_dropped']:<3} "
                  f"points_lost={a['points_lost']:<7} below_crit_floor="
                  f"{a['attacks_below_critical_floor']:<3} infiltration_below_floor="
                  f"{a['infiltration_below_floor']:<2} collateral={a['dropped_but_never_judged']:<3} "
                  f"actions={json.dumps(a['guardrail_actions'])}")
    if not args.no_export:
        for label, evaluation in evaluations.items():
            directory = export(evaluation, root=RESULTS)
            print(f"report: {directory}")
        (RESULTS / "summary.json").write_text(
            json.dumps({"error_model": ERROR_MODEL, "run_id": run_id, "rows": summaries},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
