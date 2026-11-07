"""C7 live check on a copy of the routed demo database, through the real API (TestClient):
claim a flow group as g.ang, try release as admin without a reason (400), release as admin with a reason (200),
check the work is available, the audit feed names both people, and the second analyst can then claim.
"""
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL)]
os.chdir(HITL)
TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "demo-c7-live.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
os.environ["HITL_IDS_DB"] = str(dst)

from contextlib import closing  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from apps.api import auth  # noqa: E402
from apps.api.main import app  # noqa: E402
from packages.contracts import db, models as m  # noqa: E402

with closing(db.connect(str(dst))) as conn:
    print("migrations applied now:", db.migrate(conn))
    auth.ensure_demo_accounts(conn)
    if not conn.execute("SELECT 1 FROM users WHERE username='analyst2'").fetchone():
        db.insert(conn, m.User(username="analyst2", password_hash=auth.hash_password("analyst2-demo"),
                               display_name="Second Analyst", email="a2@example.test", role="security_analyst"))
    conn.commit()
    ref = conn.execute("""SELECT o.operational_alert_ref FROM alert_groups g
                          JOIN operational_alerts_v2 o ON o.id = g.representative_operational_alert_id
                          JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id
                          WHERE t.handling_route = 'tier1_review' ORDER BY g.member_count DESC LIMIT 1""").fetchone()[0]

client = TestClient(app)


def login(user, password):
    token = client.post("/api/auth/login", json={"username": user, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


analyst, admin, second = login("g.ang", "analyst-demo"), login("admin", "admin-demo"), login("analyst2", "analyst2-demo")
base = f"/api/v2/alerts/{ref}/work"
w = client.get(base, headers=analyst).json()
r = client.post(base + "/claim", headers=analyst, json={"requestId": str(uuid4()), "expectedRevision": w["revision"]})
print("claim by g.ang:", r.status_code, r.json()["work"]["status"])
rev = r.json()["work"]["revision"]
print("second analyst claim while owned:", client.post(base + "/claim", headers=second,
      json={"requestId": str(uuid4()), "expectedRevision": rev}).status_code)
print("admin release without reason:", client.post(base + "/release", headers=admin,
      json={"requestId": str(uuid4()), "expectedRevision": rev}).status_code)
r = client.post(base + "/release", headers=admin,
                json={"requestId": str(uuid4()), "expectedRevision": rev, "reason": "Analyst left the shift"})
print("admin release with reason:", r.status_code, r.json()["work"]["status"])
audit = client.get("/api/admin/audit/current?limit=50", headers=admin).json()
lines = [i["summary"] for i in audit["items"] if i.get("eventType") == "WORK_RELEASED"]
print("audit:", lines)
w = client.get(base, headers=second).json()
r = client.post(base + "/claim", headers=second, json={"requestId": str(uuid4()), "expectedRevision": w["revision"]})
print("second analyst claim after release:", r.status_code, r.json()["work"]["ownerName"])
