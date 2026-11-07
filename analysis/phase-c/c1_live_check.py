"""C1 live check on a copy of the routed demo database, through the real API (TestClient). Read-only on the real DB.

1. Queue cost: first page of 50, old score key vs new (routing priority + verdict delta), 3 runs each.
2. Claim the top Tier 1 group as an analyst, record a 'false_positive' verdict through POST .../verdict.
3. Check: one approved feedback row on the representative's legacy alert, mapped category, guardrailed delta,
   approved audit row with the analyst; family members moved; the group's queue position before vs after.
"""
import json
import os
import shutil
import sys
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL), str(HITL / "tests")]
os.chdir(HITL)
TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c1-live.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
os.environ["HITL_IDS_DB"] = str(dst)

from apps.api import operational_queue as q  # noqa: E402
from packages.contracts import db  # noqa: E402
from packages.detection.queue_severity import severity_rank  # noqa: E402

OLD = (f"{q.SEVERITY} DESC, {q.UNFLAGGED_LAST} ASC, {q.ROUTING_PRIORITY} DESC, "
       "queue_occurred_at(a.occurred_at) DESC, a.operational_alert_ref ASC")
with closing(db.connect(str(dst))) as conn:
    conn.create_function("queue_occurred_at", 1, q.occurred_key, deterministic=True)
    conn.create_function("queue_severity_rank", 4, severity_rank, deterministic=True)
    for _ in range(3):
        t = time.perf_counter(); conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {OLD} LIMIT 50").fetchall()
        old_ms = 1000 * (time.perf_counter() - t)
        t = time.perf_counter(); conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {q.QUEUE_ORDER} LIMIT 50").fetchall()
        new_ms = 1000 * (time.perf_counter() - t)
        print(f"first page of 50: old key {old_ms:.0f} ms, new key {new_ms:.0f} ms")

from fastapi.testclient import TestClient  # noqa: E402
from apps.api.main import app  # noqa: E402
from apps.api import auth  # noqa: E402

with closing(db.connect(str(dst))) as conn:
    print("migrations applied now:", db.migrate(conn))
    auth.ensure_demo_accounts(conn)
    conn.commit()

client = TestClient(app)
r = client.post("/api/auth/login", json={"username": "g.ang", "password": "analyst-demo"})
print("login g.ang", r.status_code)
if r.status_code != 200:
    print("FAILED: login; stop", r.text[:300]); sys.exit(1)
H = {"Authorization": f"Bearer {r.json()['token']}"}

page = client.get("/api/v2/alerts", params={"limit": 200}, headers=H).json()
items = page.get("items", page)
ref_of = lambda it: it.get("operationalAlertRef") or it.get("operational_alert_ref")  # noqa: E731
with closing(db.connect(str(dst))) as conn:
    tier1 = {r[0] for r in conn.execute("""SELECT o.operational_alert_ref FROM alert_groups g
        JOIN operational_alerts_v2 o ON o.id = g.representative_operational_alert_id
        JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id WHERE t.handling_route = 'tier1_review'""")}
target = next(ref_of(it) for it in items if ref_of(it) in tier1)
before_pos = [ref_of(it) for it in items].index(target)
print("target group", target, "queue position before", before_pos + 1)

work = client.get(f"/api/v2/alerts/{target}/work", headers=H).json()
r = client.post(f"/api/v2/alerts/{target}/work/claim", headers=H, json={"requestId": str(uuid4()), "expectedRevision": work["revision"]})
print("claim", r.status_code, r.json().get("outcome"))
if r.json().get("outcome") == "pending":
    time.sleep(1.2)
    r = client.post(f"/api/v2/alerts/{target}/work/claim", headers=H, json={"requestId": str(uuid4()), "expectedRevision": work["revision"]})
    print("claim again", r.status_code, r.json().get("outcome"))
view = client.get(f"/api/v2/alerts/{target}/verdict", headers=H).json()
r = client.post(f"/api/v2/alerts/{target}/verdict", headers=H, json={
    "requestId": str(uuid4()), "expectedRevision": view["revision"],
    "expectedStateVersion": view["sourceStateVersion"], "outcome": "false_positive",
    "reason": "C1 live check: known scanner"})
print("verdict", r.status_code, r.text[:200] if r.status_code != 200 else "")

with closing(db.connect(str(dst))) as conn:
    legacy = conn.execute("SELECT legacy_alert_id FROM operational_alerts_v2 WHERE operational_alert_ref = ?",
                          (target,)).fetchone()[0]
    fb = conn.execute("SELECT * FROM feedback_events WHERE alert_id = ? ORDER BY id DESC LIMIT 1", (legacy,)).fetchone()
    print("approved feedback:", fb and dict(category=fb["category"], requested=fb["requested_delta"],
          actual=fb["actual_delta"], guardrail=fb["guardrail_action"], note=fb["note"], user=fb["user_id"]))
    audit = conn.execute("SELECT event_type, actor_id FROM audit_log WHERE feedback_id = ?", (fb["id"],)).fetchall()
    print("approved audit rows:", [tuple(a) for a in audit])
    a = conn.execute("SELECT detection_score, combined_score, severity FROM alerts WHERE id = ?", (legacy,)).fetchone()
    print("legacy alert: detection", a[0], "combined", a[1], "severity", a[2])
    learn = conn.execute("SELECT details FROM audit_log WHERE feedback_id = ? AND event_type LIKE '%LEARN%'",
                         (fb["id"],)).fetchone()
    print("family learning:", json.loads(learn[0]).get("membersMoved") if learn else "no learning event")

page = client.get("/api/v2/alerts", params={"limit": 200}, headers=H).json()
order = [ref_of(it) for it in page.get("items", page)]
print("queue position after", order.index(target) + 1 if target in order else "not in first 200")
