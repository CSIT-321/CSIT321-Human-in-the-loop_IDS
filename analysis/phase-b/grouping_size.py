"""Grouping method review: size of each method on demo.db and on the replay window.

Group rule (D3b): same source IP, next alert within 30 minutes of the group's last alert.
Also counts groups whose first flagged member is not E1 but a later member is (the 'late escalation' case).
"""
import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
GAP = timedelta(minutes=30)


def groups(rows):
    """rows: (when, src, e1). Returns list of groups, each a list of e1 flags in arrival order."""
    open_, out = {}, []
    for when, src, e1 in sorted(rows):
        g = open_.get(src)
        if g is None or when - g["last"] > GAP:
            g = {"last": when, "members": []}
            open_[src] = g
            out.append(g)
        g["members"].append(e1)
        g["last"] = when
    return [g["members"] for g in out]


def report(name, rows):
    gs = groups(rows)
    late = sum(1 for g in gs if not g[0] and any(g[1:]))
    sizes = sorted((len(g) for g in gs), reverse=True)
    print(f"{name:<30} flagged={len(rows):>7,} groups={len(gs):>6,} singletons={sum(s == 1 for s in sizes):>5,} "
          f"largest={sizes[:3]} late-escalation groups={late}")


ts = {}
with (HITL / "data/processed/demo_sample.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        ts[r["alert_id"]] = datetime.strptime(r["Timestamp"][:19], "%Y-%m-%d %H:%M:%S")
c = sqlite3.connect(f"file:{Path(os.environ['LOCALAPPDATA']) / 'Temp/hitl-review/run-base/demo.db'}?mode=ro", uri=True)
demo = [(ts[r[0]], r[1], r[2] == "corroborated" and r[3] >= 80) for r in c.execute(
    "SELECT f.source_record_id, f.src_ip, a.evidence_class, a.combined_score FROM alerts a JOIN flow_data f "
    "ON f.alert_id = a.id WHERE a.evidence_class != 'none'")]
report("demo.db (flagged)", demo)

base = HITL / "data/spike/Wednesday-14-02-2018"
s = sqlite3.connect(f"file:{base / 'spike.db'}?mode=ro", uri=True)
win = {r["alert_id"] for r in csv.DictReader((base / "replay-window/flows.csv").open(newline="", encoding="utf-8"))}
spike = []
for ref, ev, score, feats in s.execute("SELECT f.source_record_id, a.evidence_class, a.combined_score, f.flow_features "
                                       "FROM alerts a JOIN flow_data f ON f.alert_id = a.id WHERE a.evidence_class != 'none'"):
    x = json.loads(feats)
    spike.append((ref, datetime.strptime(x["Timestamp"][:19], "%Y-%m-%d %H:%M:%S"), x["Src IP"], ev == "corroborated" and score >= 80))
report("replay window (flagged)", [(w, src, e1) for ref, w, src, e1 in spike if ref in win])
report("spike full day (flagged)", [(w, src, e1) for ref, w, src, e1 in spike])
