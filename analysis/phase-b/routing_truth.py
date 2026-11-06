"""Check phase B routing outcomes against ground truth (evaluation join only; the product never sees truth).

Copies the database first; routes the copy with the committed policy; reports each outcome's false positives.
    python routing_truth.py <demo|stress>
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
PY = HITL / ".venv/Scripts/python.exe"
name = sys.argv[1]
src = HITL / "data" / f"{name}.db"
copy = Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review/run-b" / f"{name}-routed.db"
copy.parent.mkdir(parents=True, exist_ok=True)
shutil.copy(src, copy)
run = subprocess.run([str(PY), "scripts/materialize_flow_queue.py", "--database", str(copy)], cwd=HITL,
                     capture_output=True, text=True)
print(run.stdout.strip() or run.stderr[-600:])
gt = json.loads(subprocess.run([str(PY), "scripts/list_false_positives.py", "--database", str(copy), "--json",
                                "--limit", "100000"], cwd=HITL, capture_output=True, text=True, check=True).stdout)
fps = {f["ref"] for f in gt["false_positives"]}
with closing(sqlite3.connect(f"file:{copy}?mode=ro", uri=True)) as c:
    rows = c.execute("""SELECT f.source_record_id, t.handling_route, t.tier2_recommended
                        FROM operational_alerts_v2 o JOIN flow_data f ON f.alert_id = o.legacy_alert_id
                        JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id""").fetchall()
outcome = lambda r: "auto_escalated" if r[1] == "tier2_case" else "candidate" if r[2] else "routine"
for o in ("auto_escalated", "candidate", "routine"):
    sel = [r for r in rows if outcome(r) == o]
    wrong = [r[0] for r in sel if r[0] in fps]
    print(f"{name:<7} {o:<15} {len(sel):>5}  false positives {len(wrong):>4}  e.g. {wrong[:3]}")
print(f"{name:<7} flagged false positives in total: {len(fps)}")
