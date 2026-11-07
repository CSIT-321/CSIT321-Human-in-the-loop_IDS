"""B6 live check: call the real API (TestClient) on a copy of the routed demo database and record the routing view's
actions per alert. Run once against the code before B6 (a git worktree) and once after; the outputs must match.

    B6_HITL=<hitl-ids dir> B6_TAG=before|after python b6_live_check.py

Read-only: GET requests only, on a copy of run-c/demo.db. Sample: up to 10 alerts per handling route, plus one
claimed Tier 1 alert (claimed on the copy) so the owner's actions are compared too.
"""
import json
import os
import shutil
import sys
from contextlib import closing
from pathlib import Path

DEFAULT = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
HITL = Path(os.environ.get("B6_HITL") or DEFAULT)
TAG = os.environ.get("B6_TAG", "after")
sys.path[:0] = [str(HITL)]
os.chdir(HITL)
TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / f"demo-b6-live-{TAG}.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
os.environ["HITL_IDS_DB"] = str(dst)

from fastapi.testclient import TestClient  # noqa: E402
from apps.api import auth  # noqa: E402
from apps.api.main import app  # noqa: E402
from packages.contracts import db  # noqa: E402

import packages.detection.routing as routing_module  # noqa: E402
print("code under test:", Path(routing_module.__file__).resolve())

with closing(db.connect(str(dst))) as conn:
    db.migrate(conn)
    auth.ensure_demo_accounts(conn)
    conn.commit()
    picked = []
    for (route,) in conn.execute("SELECT DISTINCT handling_route FROM operational_triage_state_v2 ORDER BY 1"):
        picked += [r[0] for r in conn.execute(
            """SELECT o.operational_alert_ref FROM operational_alerts_v2 o
               JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id
               WHERE t.handling_route = ? ORDER BY o.id LIMIT 10""", (route,))]

client = TestClient(app)
token = client.post("/api/auth/login", json={"username": "g.ang", "password": "analyst-demo"}).json()["token"]
headers = {"Authorization": f"Bearer {token}"}
claim_ref = picked[0]
view = client.get(f"/api/v2/alerts/{claim_ref}/triage-state", headers=headers).json()
claim = client.post(f"/api/v2/alerts/{claim_ref}/work/claim", headers=headers,
                    json={"requestId": "00000000-0000-4000-8000-0000000000b6",
                          "expectedRevision": (view.get("work") or {}).get("revision", 0)})
out = {"claim_status": claim.status_code}
for ref in picked:
    r = client.get(f"/api/v2/alerts/{ref}/triage-state", headers=headers)
    body = r.json()
    out[ref] = [r.status_code, body.get("state", {}).get("handlingRoute"), body.get("allowedActions"),
                (body.get("work") or {}).get("status")]
(TEMP / f"b6-live-{TAG}.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
print(TAG, "alerts:", len(picked), "claim:", claim.status_code,
      "with actions:", sum(1 for k, v in out.items() if k != "claim_status" and v[2]))
