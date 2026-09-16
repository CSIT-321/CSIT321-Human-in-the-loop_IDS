#!/usr/bin/env python3
"""List the alerts a demo can use to show a false positive, and the attacks the detectors missed.

    python scripts/list_false_positives.py                       # the demo database
    python scripts/list_false_positives.py --database data/stress.db
    python scripts/list_false_positives.py --limit 40            # cap the rows printed
    python scripts/list_false_positives.py --json                # machine-readable

**This is a demo preparation aid, not a product capability.** The system never sees ground truth:
it is joined to the queue only by the evaluation harness, and `packages/evaluation/truth.py` refuses
to score a flow it cannot check. The console cannot list its own false positives, because on a real
network it would not know them.

What this script gives a presenter is a shortlist: *these are flows the detector raised that the
capture says were harmless.* Pick one, search its reference in the console, and the demo can show a
verdict, a guardrail and family learning on an alert that is genuinely wrong.

Two lists, because the demo uses both:

    FALSE POSITIVE  a flagged alert whose ground truth is benign     -> dismiss it
    MISSED ATTACK   an unflagged alert whose ground truth is an attack -> confirm it
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

DEFAULT_DB = HITL / "data" / "demo.db"
DEFAULT_TRUTH = HITL / "data" / "processed" / "demo_ground_truth.json"

COLUMNS = """f.source_record_id AS ref, a.attack_category AS attack, a.severity AS severity,
             a.combined_score AS score, a.evidence_class AS evidence, a.queue_class AS band,
             a.family_key AS family, a.requires_review AS review,
             (SELECT COUNT(*) FROM feedback_events fe WHERE fe.alert_id = a.id) AS verdicts"""


def load(conn: sqlite3.Connection, truth: dict[str, bool]) -> tuple[list, list]:
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        f"SELECT {COLUMNS} FROM alerts a JOIN flow_data f ON f.alert_id = a.id")]
    flagged = [r for r in rows if r["evidence"] != "none"]
    unflagged = [r for r in rows if r["evidence"] == "none"]
    false_positives = [r for r in flagged if not truth.get(r["ref"], False)]
    missed = [r for r in unflagged if truth.get(r["ref"], False)]
    false_positives.sort(key=lambda r: -r["score"])
    missed.sort(key=lambda r: -r["score"])
    return false_positives, missed


def show(title: str, rows: list, limit: int | None, note: str) -> None:
    print(f"\n=== {title}: {len(rows)} ===")
    print(f"    {note}")
    if not rows:
        print("    (none)")
        return
    print(f"    {'ref':<12}{'attack':<14}{'severity':<13}{'score':>7}  {'evidence':<19}"
          f"{'band':<17}{'review':<7}{'verdicts':>8}")
    for row in rows[:limit] if limit else rows:
        print(f"    {row['ref']:<12}{str(row['attack']):<14}{row['severity']:<13}"
              f"{row['score']:>7}  {row['evidence']:<19}{row['band']:<17}"
              f"{str(bool(row['review'])):<7}{row['verdicts']:>8}")
    if limit and len(rows) > limit:
        print(f"    ... {len(rows) - limit} more (--limit 0 for all)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--ground-truth", default=str(DEFAULT_TRUTH))
    parser.add_argument("--limit", type=int, default=25,
                        help="rows to print per list; 0 prints every one")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    database = Path(args.database)
    if not database.exists():
        print(f"missing {database} - build it with: python scripts/run_detection.py",
              file=sys.stderr)
        return 2

    raw = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))
    # A flow is malicious when its capture label says so; `Benign` is the only other value.
    truth = {key: str(value.get("groundTruth", "")).lower().startswith("malicious")
             for key, value in raw.items()}

    conn = sqlite3.connect(database)
    try:
        false_positives, missed = load(conn, truth)
    finally:
        conn.close()

    if args.json:
        print(json.dumps({"database": str(database), "false_positives": false_positives,
                          "missed_attacks": missed}, indent=2))
        return 0

    limit = args.limit or None
    print(f"database  : {database}")
    print(f"ground truth: {args.ground_truth}")
    print("\nUse one of these in the console by searching its reference. Ground truth never reaches "
          "the system:")
    print("the console cannot list these itself, and must not be shown as if it could.")
    show("FALSE POSITIVES - flagged, but the capture says Benign", false_positives, limit,
         "Search one, dismiss it, and the guardrails and family learning are demonstrable on it.")
    show("MISSED ATTACKS - unflagged, but the capture says attack", missed, limit,
         "Search one, confirm it, and it climbs. This is the demo's second verdict path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
