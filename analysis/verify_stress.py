#!/usr/bin/env python3
"""Measure the stress database against ground truth. Read-only.

Answers the question the stress run exists for: does the queue now hold enough false positives
that analyst feedback has something to correct? Compares data/stress.db with data/demo.db.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

HITL = Path(__file__).resolve().parent / "hitl-ids"
SAMPLE = HITL / "data" / "processed" / "demo_sample.csv"

truth: dict[str, str] = {}
with SAMPLE.open(encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        truth[row["alert_id"]] = row["attack_class"] or "Benign"


def load(db: str):
    conn = sqlite3.connect(HITL / "data" / db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT a.id, a.detection_score AS ds, a.combined_score AS cs, a.queue_class AS qc, "
        "       a.evidence_class AS ec, f.source_record_id AS rec "
        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        "ORDER BY a.queue_priority ASC, a.combined_score DESC, a.id ASC").fetchall()
    conn.close()
    return [(r["rec"], round(r["ds"], 2), r["qc"], r["ec"]) for r in rows]


def report(db: str) -> None:
    rows = load(db)
    flagged = [r for r in rows if r[2] != "none"]
    tp = [r for r in flagged if truth.get(r[0], "Benign") != "Benign"]
    fp = [r for r in flagged if truth.get(r[0], "Benign") == "Benign"]
    scores = [r[1] for r in flagged]
    saturated = sum(1 for s in scores if s >= 100)
    print(f"\n=== {db} ===")
    print(f"  flagged {len(flagged)}  |  true positives {len(tp)}  |  FALSE POSITIVES {len(fp)}")
    if flagged:
        print(f"  precision among flagged: {len(tp) / len(flagged):.3f}")
    print(f"  at exactly 100.0: {saturated} of {len(flagged)}  "
          f"({saturated / max(len(flagged), 1):.1%})")
    print(f"  distinct detection scores among flagged: {len(set(scores))}")
    for k in (10, 50, 100, 200):
        top = flagged[:k]
        hits = sum(1 for r in top if truth.get(r[0], "Benign") != "Benign")
        print(f"  precision@{k:<4} {hits / max(len(top), 1):.3f}   "
              f"({k - hits} false positives in the top {len(top)})")
    print(f"  evidence classes: "
          f"{ {c: sum(1 for r in flagged if r[3] == c) for c in sorted({r[3] for r in flagged})} }")
    print("  first 8 flagged rows (record, detection score, band, evidence):")
    for r in flagged[:8]:
        mark = "FP" if truth.get(r[0], "Benign") == "Benign" else "TP"
        print(f"    {r[0]}  {r[1]:>7}  {r[2]:<18} {r[3]:<18} {mark}")


report("demo.db")
report("stress.db")
