"""SOC workload view of the 5,000 flow alerts: what each automation would remove from Tier 1, and its error.

Ground truth comes only from list_false_positives.py (evaluation join). Reads a copy, never data/demo.db.
"""
import json
import os
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
PY = HITL / ".venv/Scripts/python.exe"
DB = Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review/run-base/demo.db"

out = subprocess.run([str(PY), "scripts/list_false_positives.py", "--database", str(DB), "--json", "--limit", "100000"],
                     cwd=HITL, capture_output=True, text=True, check=True)
fp = {f["ref"] for f in json.loads(out.stdout)["false_positives"]}
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = c.execute("""SELECT f.source_record_id, a.evidence_class, a.is_critical, a.combined_score
                    FROM alerts a JOIN flow_data f ON f.alert_id = a.id""").fetchall()
truth = dict(c.execute("SELECT source_record_id, attack_class FROM flow_data").fetchall()) if False else {}
print(f"{len(rows)} alerts; flagged-benign (false positives) = {len(fp)}")
by = Counter(r[1] for r in rows)
fpby = Counter(r[1] for r in rows if r[0] in fp)
for k in sorted(by):
    print(f"  {k:<20} alerts={by[k]:>5}  benign-among-them={fpby[k]:>4}")
e1 = [r for r in rows if r[1] == "corroborated" and r[2] == 1]
print(f"E1 auto-escalate: {len(e1)} alerts, {sum(r[0] in fp for r in e1)} benign")
