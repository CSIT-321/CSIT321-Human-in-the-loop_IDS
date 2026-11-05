"""Can spike criterion 4 (E1 fires) pass on 2018-02-14? Count E1 alerts per capture day in the demo data."""
import csv
import os
import sqlite3
from collections import Counter
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
DB = Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review/run-base/demo.db"
day = {}
cls = {}
with (HITL / "data/processed/demo_sample.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        day[r["alert_id"]] = r["Timestamp"].split(" ")[0]
        cls[r["alert_id"]] = r["attack_class"]
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = c.execute("""SELECT f.source_record_id, a.evidence_class, a.is_critical
                    FROM alerts a JOIN flow_data f ON f.alert_id = a.id""").fetchall()
e1 = Counter((day[r[0]], cls[r[0]]) for r in rows if r[1] == "corroborated" and r[2] == 1)
flagged = Counter(day[r[0]] for r in rows if r[1] != "none")
for (d, k), n in sorted(e1.items()):
    print(f"E1 {d} {k:<12} {n}")
print("flagged per day:", dict(sorted(flagged.items())))
