"""C2/C3 relevance check on a copy of the routed demo DB. Read-only on a copy.

Plan C2: queue tab "Tier 2 candidates" (tier2Recommended filter). Plan C3: "Why Tier 2" panel with
Escalate / Keep in Tier 1 / Record verdict (approve_tier2 / reject_tier2). The web labels these "Historical".
Count: routes, tier2_recommended rows, and approve/reject decisions actually recorded.
"""
import os
import shutil
import sqlite3
from pathlib import Path

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c2-check.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
c = sqlite3.connect(dst)
cols = [r[1] for r in c.execute("PRAGMA table_info(operational_triage_state_v2)")]
print("triage columns with tier2:", [x for x in cols if "tier2" in x])
print("routes:", c.execute("SELECT handling_route, count(*) FROM operational_triage_state_v2 GROUP BY 1").fetchall())
if "tier2_recommended" in cols:
    print("tier2_recommended:", c.execute("SELECT tier2_recommended, count(*) FROM operational_triage_state_v2 GROUP BY 1").fetchall())
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
for t in tables:
    tcols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    if "action" in tcols:
        print(t, "actions:", c.execute(f"SELECT action, count(*) FROM {t} GROUP BY 1").fetchall())
print("system routing classes:", c.execute(
    "SELECT route_class, count(*) FROM operational_system_routing GROUP BY 1").fetchall()
    if "operational_system_routing" in tables else "no table")
