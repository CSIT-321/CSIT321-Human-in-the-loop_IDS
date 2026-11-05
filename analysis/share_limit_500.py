"""Does a share limit of 90% over the last 500 arrivals trip on correct E1 bursts? (orchestrator check)

Arrival order: demo.db by capture timestamp (demo_sample.csv) and by alert id; stress.db by alert id.
Reads copies / the stress DB read-only. Never writes.
"""
import csv
import os
import sqlite3
from collections import deque
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
DBS = {"demo": Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review/run-base/demo.db", "stress": HITL / "data/stress.db"}
ts = {}
with (HITL / "data/processed/demo_sample.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        ts[r["alert_id"]] = r["Timestamp"]


def profile(name, seq, window=500, limit=0.90):
    w, hits, peak, trips, first = deque(maxlen=window), 0, 0.0, 0, None
    for i, e1 in enumerate(seq):
        if len(w) == window and w[0]:
            hits -= 1
        w.append(e1)
        hits += e1
        if len(w) == window:
            share = hits / window
            peak = max(peak, share)
            if e1 and share >= limit:
                trips += 1
                first = first if first is not None else i
    print(f"{name:<22} arrivals={len(seq):>5} E1={sum(seq):>4} peak share/{window}={peak:.3f} "
          f"E1 blocked at {limit:.0%}={trips} first_at={first}")


for name, path in DBS.items():
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = c.execute("""SELECT a.id, f.source_record_id, a.evidence_class = 'corroborated' AND a.is_critical = 1
                        FROM alerts a JOIN flow_data f ON f.alert_id = a.id ORDER BY a.id""").fetchall()
    profile(f"{name} by alert id", [r[2] for r in rows])
    if name == "demo":
        profile("demo by capture time", [r[2] for r in sorted(rows, key=lambda r: ts.get(r[1], ""))])
        day = [r for r in sorted(rows, key=lambda r: ts.get(r[1], "")) if ts.get(r[1], "").startswith("2018-02-14")]
        profile("demo 2018-02-14 only", [r[2] for r in day])
