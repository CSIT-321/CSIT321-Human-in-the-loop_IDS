"""C4 field check: the real V2 evidence payload for flow alerts (corroborated, ml_only, signature) on a demo copy.
Prints the paths C4 needs: short name, rule conditions, combined explanation, agreement, legacy confidence."""
import json
import os
import shutil
import sys
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL)]
os.chdir(HITL)
TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c4-fields.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
os.environ["HITL_IDS_DB"] = str(dst)

from fastapi.testclient import TestClient  # noqa: E402
from apps.api import auth  # noqa: E402
from apps.api.main import app  # noqa: E402
from packages.contracts import db  # noqa: E402

with closing(db.connect(str(dst))) as conn:
    db.migrate(conn); auth.ensure_demo_accounts(conn); conn.commit()
    picks = {}
    for cls in ("corroborated", "ml_only", "signature_only", "signature_override", "none"):
        r = conn.execute("""SELECT o.operational_alert_ref FROM operational_alerts_v2 o JOIN alerts a ON a.id = o.legacy_alert_id
                            WHERE a.evidence_class = ? LIMIT 1""", (cls,)).fetchone()
        if r: picks[cls] = r[0]
print("classes found:", list(picks))
c = TestClient(app)
H = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "g.ang", "password": "analyst-demo"}).json()["token"]}


def short(v, n=160):
    s = json.dumps(v); return s if len(s) <= n else s[:n] + "..."


for cls, ref in picks.items():
    ev = c.get(f"/api/v2/alerts/{ref}/evidence", headers=H)
    print(f"\n== {cls} {ref} -> {ev.status_code}")
    if ev.status_code != 200: print(ev.text[:300]); continue
    body = ev.json()
    print("top keys:", list(body))
    d = body["detectorEvidence"]
    print("detectorEvidence keys:", list(d))
    print("sourceRecordReference:", d.get("sourceRecordReference"), "| confidence:", d.get("confidence"))
    print("sourceProvenance:", short(body.get("sourceProvenance"), 300))
    se = d["structuredEvidence"]
    print("structuredEvidence keys:", list(se))
    for k in se:
        if any(w in k.lower() for w in ("rule", "explan", "agree", "fusion", "reason")):
            print(f"  {k}: {short(se[k], 400)}")
