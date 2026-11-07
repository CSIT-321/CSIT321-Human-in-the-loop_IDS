"""Seed for the admin claimed-list live check: copy the routed demo DB and make 2 claims by g.ang.
Real `data/demo.db` untouched. Prints the claimed refs."""
import os, shutil, sys
from uuid import uuid4

TMP = os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review")
DB = os.path.join(TMP, "claimed-ui.db")
shutil.copyfile(os.path.join(TMP, "run-c", "demo.db"), DB)
os.environ["HITL_IDS_DB"] = DB
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from apps.api.main import create_app

with TestClient(create_app(DB)) as client:
    token = client.post("/api/auth/login", json={"username": "g.ang", "password": "analyst-demo"}).json()["token"]
    h = {"Authorization": "Bearer " + token}
    items = client.get("/api/v2/alerts?limit=10&workScope=active&sort=priority_desc", headers=h).json()["items"]
    done = 0
    for item in items:
        if done == 2: break
        if not (item["work"] and item["work"]["canClaim"]): continue
        ref = item["operationalAlertRef"]
        r = client.post(f"/api/v2/alerts/{ref}/work/claim", headers=h,
                        json={"requestId": str(uuid4()), "expectedRevision": item["work"]["revision"]})
        print("claim", ref, r.status_code, r.json().get("outcome")); done += 1
print("db", DB)
