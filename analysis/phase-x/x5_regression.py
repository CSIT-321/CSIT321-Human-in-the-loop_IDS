"""X5 regression check: build a fresh demo db with the new runner and compare every alert's score, band and
is_critical with the real data/demo.db (read-only). Live config = defaults, so nothing may move."""
import os, sqlite3, subprocess, sys, time
HITL = r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids"
NEW = os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\x5-fresh.db")
if os.path.exists(NEW):
    os.remove(NEW)
t = time.time()
r = subprocess.run([os.path.join(HITL, ".venv", "Scripts", "python.exe"), "scripts/run_detection.py", "--database", NEW,
                    "--replay", "data/processed/demo_ml_predictions_shap.json"], cwd=HITL, capture_output=True, text=True)
print("build exit", r.returncode, f"{time.time() - t:.0f}s", r.stderr[-400:] if r.returncode else "")
q = ("SELECT f.source_record_id, a.detection_score, a.queue_class, a.is_critical, a.severity "
     "FROM alerts a JOIN flow_data f ON f.alert_id = a.id")
old = {row[0]: row[1:] for row in sqlite3.connect(f"file:{HITL}/data/demo.db?mode=ro", uri=True).execute(q)}
new = {row[0]: row[1:] for row in sqlite3.connect(NEW).execute(q)}
diff = [k for k in old if old[k] != new.get(k)]
print("alerts old/new:", len(old), len(new), "| differing:", len(diff), diff[:5])
# second run on the same db must be refused (X4) and store nothing
r2 = subprocess.run([os.path.join(HITL, ".venv", "Scripts", "python.exe"), "scripts/run_detection.py", "--database", NEW,
                     "--replay", "data/processed/demo_ml_predictions_shap.json"], cwd=HITL, capture_output=True, text=True)
print("second run exit", r2.returncode, "|", (r2.stderr.strip().splitlines() or [""])[-1][:200])
print("alerts after second run:", sqlite3.connect(NEW).execute("SELECT COUNT(*) FROM alerts").fetchone()[0])
