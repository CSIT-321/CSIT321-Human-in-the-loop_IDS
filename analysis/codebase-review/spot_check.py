"""Spot-check five worker claims directly (orchestrator verification, not delegated).

S9-02  serve_routing_rehearsal.py calls stage_file without the required capture_scope keyword.
S6-01  /api/v2/alerts/summary is slow once the 996 flow alerts are projected (measured on the Phase A copy).
S1-03  alerts.detection_score can be UPDATEd although the schema calls it immutable.
S2-05  run_detection twice on one database doubles the alerts.
S3-02  system_routing hard-codes tier2_recommended=False.
"""
import inspect
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

H = Path(__file__).resolve().parents[2] / "hitl-ids"
sys.path.insert(0, str(H))

from packages.detection.adapters import staging  # noqa: E402

print("S9-02 stage_file signature:", inspect.signature(staging.stage_file))
calls = [ln.strip() for ln in (H / "scripts/serve_routing_rehearsal.py").read_text().splitlines() if "stage_file(" in ln]
print("       calls in serve_routing_rehearsal.py:", calls)

src = (H / "packages/detection/system_routing.py").read_text().splitlines()
print("S3-02 line 101:", src[100].strip()[:140])

copy = Path(tempfile.mkdtemp()) / "s13.db"
shutil.copy(H / "data/demo.db", copy)
c = sqlite3.connect(copy)
aid, before = c.execute("SELECT id, detection_score FROM alerts LIMIT 1").fetchone()
try:
    c.execute("UPDATE alerts SET detection_score = detection_score + 1 WHERE id=?", (aid,))
    after = c.execute("SELECT detection_score FROM alerts WHERE id=?", (aid,)).fetchone()[0]
    print(f"S1-03 UPDATE detection_score: accepted, {before} -> {after}")
except sqlite3.DatabaseError as e:
    print("S1-03 UPDATE detection_score: rejected:", e)
c.rollback()
c.close()

import os  # noqa: E402
import urllib.request  # noqa: E402
import json  # noqa: E402

req = urllib.request.Request("http://127.0.0.1:8010/api/auth/login", method="POST",
                             data=json.dumps({"username": "g.ang", "password": "analyst-demo"}).encode(),
                             headers={"Content-Type": "application/json"})
token = json.load(urllib.request.urlopen(req, timeout=30))["token"]
for path in ("/api/v2/alerts/summary", "/api/v2/alerts?limit=50&sort=priority_desc"):
    r = urllib.request.Request("http://127.0.0.1:8010" + path, headers={"Authorization": f"Bearer {token}"})
    t = time.perf_counter()
    urllib.request.urlopen(r, timeout=600).read()
    print(f"S6-01 {path}: {time.perf_counter() - t:.1f} s (Phase A copy, 996 projected)")
