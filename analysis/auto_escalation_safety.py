"""Measure how safe automatic Tier 2 escalation would be on data/demo.db and data/stress.db.

Ground truth comes only from list_false_positives.py (the evaluation join); the product never sees it.
Rules measured, each on its own and in order of strictness:
  E1  corroborated (rule AND model) AND is_critical (score >= 80)
  E3  score >= 90 AND attack-class CVSS severity >= 7.0
  tier2_candidate  the stored band (E1 or E3 or promotion by feedback)
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
PY = HITL / ".venv/Scripts/python.exe"
TMP = Path(os.environ["LOCALAPPDATA"]) / "Temp/hitl-review"
DBS = {"demo": TMP / "run-base/demo.db", "stress": HITL / "data/stress.db"}

chart = json.loads((HITL / "config/severity-chart.json").read_text(encoding="utf-8"))
print("severity chart keys:", list(chart)[:6])

for name, path in DBS.items():
    out = subprocess.run([str(PY), "scripts/list_false_positives.py", "--database", str(path), "--json",
                          "--limit", "100000"], cwd=HITL, capture_output=True, text=True)
    if out.returncode != 0:
        print(name, "FAILED", out.stderr[-400:])
        continue
    gt = json.loads(out.stdout)
    fp_refs = {f["ref"] for f in gt["false_positives"]}
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = c.execute("""SELECT f.source_record_id, a.evidence_class, a.is_critical, a.combined_score,
                               a.detection_score, a.queue_class, a.severity, a.ml_predicted_class
                        FROM alerts a JOIN flow_data f ON f.alert_id = a.id""").fetchall()
    print(f"\n== {name}: {len(rows)} alerts, {len(fp_refs)} flagged-benign (false positives)")
    def report(label, pred):
        hit = [r for r in rows if pred(r)]
        fps = [r for r in hit if r[0] in fp_refs]
        print(f"  {label:<44} escalated={len(hit):>5}  false positives={len(fps):>4}"
              f"  precision={(1 - len(fps) / len(hit)) if hit else float('nan'):.4f}"
              f"  e.g. {[r[0] for r in fps[:3]]}")
    report("E1 corroborated AND critical", lambda r: r[1] == "corroborated" and r[2] == 1)
    report("E1 + detection score == 100", lambda r: r[1] == "corroborated" and r[2] == 1 and r[4] >= 100)
    report("E3 score>=90 AND severity High/Critical", lambda r: r[3] >= 90 and r[6] in ("High", "Critical"))
    report("ml_only AND score>=90 AND High/Critical", lambda r: r[1] == "ml_only" and r[3] >= 90 and r[6] in ("High", "Critical"))
    report("stored queue_class = tier2_candidate", lambda r: r[5] == "tier2_candidate")
    report("signature_override (rule only)", lambda r: r[1] == "signature_override")
