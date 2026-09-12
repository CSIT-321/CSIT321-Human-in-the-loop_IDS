"""
Run the three-arm evaluation over a detection database (plan step S15).

    python scripts/run_evaluation.py                      # the demo database, all three arms
    python scripts/run_evaluation.py --dry-run            # print the pre-registered sequence only
    python scripts/run_evaluation.py --no-export          # run and print, write nothing

    A - control          no feedback      guardrails on
    B - treatment        scripted         guardrails on
    C - guardrail probe  same scripted    guardrails OFF

The three arms are byte copies of one detection database, so dataset, model version, rule-set
version and seed are identical by construction; the feedback sequence and the guardrail flag are
the only variables.

Whatever arm C shows is printed and stored as measured. A suppression count of zero means the
guardrails did not bind on this sequence - that is a result, not a failed run, and it is never a
reason to re-sample (plan S15, the v0.3 FIX).

Inputs:  data/demo.db (build it with scripts/run_detection.py),
         data/processed/demo_ground_truth.json
Output:  evaluation/three-arm/runs/<run id>/{config,results}.json, a line in history.jsonl,
         and the arm databases as data/eval-<arm>.db (gitignored)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts import db  # noqa: E402
from packages.evaluation.harness import evaluate, export  # noqa: E402
from packages.evaluation.scenario import Preregistration, build_sequence  # noqa: E402
from packages.evaluation.truth import GroundTruth  # noqa: E402

DEFAULT_DB = HITL / "data" / "demo.db"
DEFAULT_TRUTH = HITL / "data" / "processed" / "demo_ground_truth.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--ground-truth", default=str(DEFAULT_TRUTH))
    parser.add_argument("--size", type=int, default=Preregistration.size,
                        help="pre-registered sequence length")
    parser.add_argument("--max-per-family", type=int, default=Preregistration.max_per_family)
    parser.add_argument("--min-family-size", type=int, default=Preregistration.min_family_size)
    parser.add_argument("--workdir", default=None, help="where the arm databases are written")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="derive and print the pre-registered sequence; run no arm")
    parser.add_argument("--no-export", action="store_true", help="print results, write no files")
    args = parser.parse_args()

    database = Path(args.database)
    if not database.exists():
        print(f"missing {database} - build it with: python scripts/run_detection.py",
              file=sys.stderr)
        return 2
    truth_path = Path(args.ground_truth)
    if not truth_path.exists():
        print(f"missing {truth_path} - see data/README.md", file=sys.stderr)
        return 2

    truth = GroundTruth.load(truth_path)
    rule = Preregistration(size=args.size, max_per_family=args.max_per_family,
                           min_family_size=args.min_family_size)

    if args.dry_run:
        conn = db.connect(database)
        try:
            sequence = build_sequence(conn, truth, rule=rule)
        finally:
            conn.close()
        print(json.dumps({"preregistration": rule.snapshot(), "length": len(sequence),
                          "sequence": sequence}, indent=2))
        return 0

    evaluation = evaluate(database, truth=truth, rule=rule, workdir=args.workdir,
                          run_id=args.run_id)
    results = evaluation.results()

    print(f"pre-registration : {rule.rule}  ({len(evaluation.sequence)} verdicts)")
    print(f"detection identical across arms: "
          f"{results['detection_metrics_identical_across_arms']}\n")
    header = f"{'arm':<18}{'verdicts':>9}{'P@50':>8}{'FP@50':>7}{'MRR':>12}{'mean rank':>11}"
    print(header)
    print("-" * len(header))
    for row in results["arms"]:
        print(f"{row['arm']:<18}{row['verdicts']:>9}{row['precision_at_50']:>8.3f}"
              f"{row['false_positives_in_top_50']:>7}{row['mrr_true_positives']:>12.6f}"
              f"{row['mean_rank_true_positives']:>11.1f}")
    print("\ndeltas (B - A):", json.dumps(results["deltas"]["B_minus_A"]))
    print("deltas (C - B):", json.dumps(results["deltas"]["C_minus_B"]))
    print("\nwhat the guardrails prevented, as measured:")
    print(json.dumps(results["guardrails_prevented"], indent=2))
    print("\nmovement in B (the S7b claim):")
    print(json.dumps(results["movement"]["B-treatment"], indent=2))

    if not args.no_export:
        directory = export(evaluation)
        print(f"\nreport: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
