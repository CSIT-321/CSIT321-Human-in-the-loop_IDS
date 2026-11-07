"""C1 queue-delta precheck on a copy of the routed demo DB. Read-only.

Option 1 (user, 2026-11-07): flow alert queue score = operational_priority + verdict delta. Before any verdict
the delta must be 0, or the queue moves with no verdict. Measure combined_score - detection_score per alert.
"""
import os
import sqlite3
from collections import Counter
from pathlib import Path

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
c = sqlite3.connect(TEMP / "c1-facts.db")
cols = [r[1] for r in c.execute("PRAGMA table_info(alerts)")]
print("alerts score columns:", [x for x in cols if "score" in x or "confidence" in x])
rows = c.execute("SELECT id, detection_score, combined_score, evidence_class FROM alerts").fetchall()
diff = [(i, d, s, e) for i, d, s, e in rows if d is None or s is None or abs(s - d) > 1e-9]
print(f"alerts {len(rows)}; combined != detection: {len(diff)}")
print("by evidence class:", Counter(e for *_, e in diff))
print("examples:", diff[:6])
fb = c.execute("SELECT alert_id, category, original_score, actual_delta FROM feedback_events").fetchall()
print("feedback rows:", fb)
proj = c.execute("""SELECT count(*), sum(abs(a.combined_score - a.detection_score) > 1e-9)
    FROM operational_alerts_v2 o JOIN alerts a ON a.id = o.legacy_alert_id""").fetchone()
print(f"projected flow alerts {proj[0]}; with nonzero delta now: {proj[1]}")
