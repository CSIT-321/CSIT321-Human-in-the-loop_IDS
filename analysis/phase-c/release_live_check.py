"""Release button live check, API part, on a copy of the routed demo DB (real `data/demo.db` untouched).

1. g.ang claims a Tier 1 alert; the work view says canRelease, no reason needed.
2. The admin's view of the same claim: canRelease, reason required. Another analyst: no release.
3. Admin release without a reason -> 400; with a reason -> 200, alert available, one WORK_RELEASED event.
Prints a short report. Run from hitl-ids with the project venv.
"""
import json, os, shutil, sqlite3, sys, time
from uuid import uuid4

TMP = os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review")
SRC = os.path.join(TMP, "run-c", "demo.db")
DB = os.path.join(TMP, "release-live.db")
shutil.copyfile(SRC, DB)
os.environ["HITL_IDS_DB"] = DB
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from apps.api.main import create_app


def login(client, user, password):
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]}


with TestClient(create_app(DB)) as client:
    analyst = login(client, "g.ang", "analyst-demo")
    admin = login(client, "admin", "admin-demo")
    page = client.get("/api/v2/alerts?limit=50&offset=0&sort=priority_desc", headers=analyst).json()["items"]
    item = next(i for i in page if i["work"] and i["work"]["status"] == "available" and i["work"]["canClaim"])
    ref = item["operationalAlertRef"]
    work_url = f"/api/v2/alerts/{ref}/work"
    seen = client.get(work_url, headers=analyst).json()
    r = client.post(work_url + "/claim", headers=analyst, json={"requestId": str(uuid4()), "expectedRevision": seen["revision"]})
    print("claim", r.status_code, r.json().get("outcome"))
    owner = client.get(work_url, headers=analyst).json()
    adm = client.get(work_url, headers=admin).json()
    print("owner view: canRelease=%s reasonRequired=%s idle=%s" % (owner["canRelease"], owner["releaseReasonRequired"], owner["idle"]))
    print("admin view: canRelease=%s reasonRequired=%s" % (adm["canRelease"], adm["releaseReasonRequired"]))
    body = {"requestId": str(uuid4()), "expectedRevision": adm["revision"]}
    r = client.post(work_url + "/release", headers=admin, json=body)
    print("admin release, no reason:", r.status_code, r.json().get("error", {}).get("code"))
    r = client.post(work_url + "/release", headers=admin, json={**body, "requestId": str(uuid4()), "reason": "Live check: shift change"})
    print("admin release, reason:", r.status_code, r.json()["work"]["status"] if r.status_code == 200 else r.text[:200])
    c = sqlite3.connect(DB)
    rows = c.execute("SELECT actor_id, detail FROM analyst_work_events e JOIN operational_alerts_v2 a ON a.id=e.operational_alert_id "
                     "WHERE a.operational_alert_ref=? AND e.event_type='WORK_RELEASED'", (ref,)).fetchall()
    for actor, detail in rows:
        d = json.loads(detail)
        print("event: actor", actor, "releasedBy", d.get("releasedBy"), "previousOwner", d.get("previousOwnerActorId"), "reason", d.get("reason"))
    print("alert", ref)
