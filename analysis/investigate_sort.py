#!/usr/bin/env python3
"""Phase 1 repro: does the direction flip the detection-score order?

Runs the exact ORDER BY that store.queue_page builds, for both directions,
and compares the returned id sequences and scores. Read-only.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent / "hitl-ids" / "data" / "demo.db"

if not DB.exists():
    sys.exit(f"missing {DB} - run python scripts/run_detection.py first")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print(f"database: {DB}")
print("alerts:", conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])

# ---- score distribution -------------------------------------------------
print("\n--- detection_score distribution (all alerts) ---")
rows = conn.execute(
    "SELECT detection_score AS s, COUNT(*) AS n FROM alerts "
    "GROUP BY s ORDER BY n DESC LIMIT 8").fetchall()
for r in rows:
    print(f"  score {r['s']:>7} : {r['n']:>5} alerts")
distinct = conn.execute("SELECT COUNT(DISTINCT detection_score) FROM alerts").fetchone()[0]
print(f"  distinct detection_score values: {distinct}")

flagged = conn.execute(
    "SELECT COUNT(*) FROM alerts WHERE queue_class != 'none'").fetchone()[0]
at100 = conn.execute(
    "SELECT COUNT(*) FROM alerts WHERE detection_score >= 100").fetchone()[0]
print(f"  flagged alerts: {flagged}  |  at exactly 100: {at100}")

# ---- the actual ORDER BY, both directions -------------------------------
def seq(order: str, where: str = "", params: list | None = None, limit: int = 50):
    sql = (f"SELECT a.id, a.detection_score AS s, a.combined_score AS c "
           f"FROM alerts a JOIN flow_data f ON f.alert_id = a.id{where} "
           f"ORDER BY {order} LIMIT ?")
    return [(r["id"], round(r["s"], 2), round(r["c"], 2))
            for r in conn.execute(sql, [*(params or []), limit])]


CASES = [
    ("governs: no filter", "", []),
    ("detectionMaxScore=100 (the console's ceiling)", " WHERE a.detection_score <= ?", [100.0]),
    ("detectionMaxScore=99.999", " WHERE a.detection_score <= ?", [99.999]),
]

for label, where, params in CASES:
    desc = seq("a.detection_score DESC, a.id ASC", where, params)
    asc = seq("a.detection_score ASC, a.id ASC", where, params)
    same_ids = [i for i, _, _ in desc] == [i for i, _, _ in asc]
    print(f"\n--- {label} ---")
    print(f"  DESC first 6: {desc[:6]}")
    print(f"  ASC  first 6: {asc[:6]}")
    print(f"  identical id order after flipping direction? {same_ids}")
    desc_scores = [s for _, s, _ in desc]
    asc_scores = [s for _, s, _ in asc]
    print(f"  DESC score range on page: {min(desc_scores)} .. {max(desc_scores)}")
    print(f"  ASC  score range on page: {min(asc_scores)} .. {max(asc_scores)}")
    print(f"  page is all one score value (DESC)? {len(set(desc_scores)) == 1}"
          f"   (ASC)? {len(set(asc_scores)) == 1}")

# ---- how many alerts share the top score --------------------------------
print("\n--- ties at the top ---")
top = conn.execute("SELECT MAX(detection_score) FROM alerts").fetchone()[0]
n_top = conn.execute("SELECT COUNT(*) FROM alerts WHERE detection_score = ?",
                     (top,)).fetchone()[0]
print(f"  max detection_score {top} is shared by {n_top} alerts")
print(f"  a 50-row page therefore shows only {50} of those {n_top}, "
      f"chosen solely by the a.id ASC tie-break")
