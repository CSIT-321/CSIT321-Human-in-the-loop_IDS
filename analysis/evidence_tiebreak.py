#!/usr/bin/env python3
"""Evidence for the proposed tie-break change. Read-only.

Compares the ORDER BY the code builds today with the proposed one, on the
975 alerts that saturate at detection_score = 100.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "hitl-ids" / "data" / "demo.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

WHERE = " WHERE a.detection_score = 100"      # the saturated group: 975 alerts
CURRENT = "a.detection_score {d}, a.id ASC"                      # today
PROPOSED = "a.detection_score {d}, a.evidence_priority ASC, a.requires_review DESC, a.id {d}"

SQL = ("SELECT a.id, a.evidence_class AS ec, a.requires_review AS rr, "
       "       a.queue_class AS qc "
       "FROM alerts a JOIN flow_data f ON f.alert_id = a.id" + WHERE +
       " ORDER BY {order} LIMIT 8")


def page(order: str, direction: str):
    rows = conn.execute(SQL.format(order=order.format(d=direction.upper()))).fetchall()
    return [(r["id"], r["ec"], "review" if r["rr"] else "-", r["qc"]) for r in rows]


print("Saturated group: detection_score = 100  (975 alerts, one page = 50)\n")
for label, order in (("CURRENT  ", CURRENT), ("PROPOSED ", PROPOSED)):
    for direction in ("desc", "asc"):
        rows = page(order, direction)
        ids = [r[0] for r in rows]
        print(f"{label} {direction.upper():<4} {ids}")
    d = [r[0] for r in page(order, "desc")]
    a = [r[0] for r in page(order, "asc")]
    print(f"{label} -> direction flips the page? {d != a}\n")

print("PROPOSED, descending — the full row, to show what is being ordered by")
for r in page(PROPOSED, "desc"):
    print(f"   alert {r[0]:>5}  evidence={r[1]:<18} {r[2]:<6} band={r[3]}")

print("\nPROPOSED, ascending — same group, reversed")
for r in page(PROPOSED, "asc"):
    print(f"   alert {r[0]:>5}  evidence={r[1]:<18} {r[2]:<6} band={r[3]}")

print("\n--- the contract queue order, today vs proposed ---")
Q_NOW = "a.queue_priority ASC, a.combined_score DESC, a.id ASC"
Q_NEW = ("a.queue_priority ASC, a.combined_score DESC, "
         "a.evidence_priority ASC, a.requires_review DESC, a.id ASC")
for label, order in (("QUEUE NOW ", Q_NOW), ("QUEUE NEW ", Q_NEW)):
    rows = conn.execute(
        "SELECT a.id, a.evidence_class AS ec, a.requires_review AS rr "
        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        f"ORDER BY {order} LIMIT 6").fetchall()
    print(f"{label} {[(r['id'], r['ec'], int(r['rr'])) for r in rows]}")
