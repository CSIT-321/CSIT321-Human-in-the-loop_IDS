"""Read-only readiness check for the two running instances. Prints one line per check."""
import json

import httpx

CASES = [("flow lane (Tier 1/2 product)", "http://127.0.0.1:8000"),
         ("suricata lane", "http://127.0.0.1:8001")]
USERS = [("g.ang", "analyst-demo", "security_analyst"),
         ("admin", "admin-demo", "system_admin"),
         ("evaluator", "evaluator-demo", "evaluator")]

for label, base in CASES:
    print(f"== {label}  {base}")
    with httpx.Client(base_url=base, timeout=20) as c:
        for username, password, role in USERS:
            r = c.post("/api/auth/login", json={"username": username, "password": password})
            token = r.json().get("token") if r.status_code == 200 else None
            if not token:
                print(f"  LOGIN FAIL {username} {r.status_code} {r.text[:120]}")
                continue
            h = {"Authorization": f"Bearer {token}"}
            me = c.get("/api/auth/session", headers=h)
            rq = c.get("/api/v2/alerts", headers=h, params={"limit": 1})
            total = rq.json().get("page", {}).get("total") if rq.status_code == 200 else None
            print(f"  login {username:9} role {role:16} session {me.status_code} "
                  f"queue_total {total} ({rq.status_code})")
        if "8001" in base:
            adm = c.post("/api/auth/login", json={"username": "g.ang", "password": "analyst-demo"}).json()["token"]
            h = {"Authorization": f"Bearer {adm}"}
            ext = c.get("/api/v2/external-alerts", headers=h, params={"limit": 5})
            if ext.status_code == 200:
                d = ext.json()
                statuses = {}
                for item in d.get("items", []):
                    statuses[item.get("status")] = statuses.get(item.get("status"), 0) + 1
                print(f"  external inbox total {d.get('page', {}).get('total')} statuses {statuses}")
            else:
                print(f"  external inbox FAIL {ext.status_code} {ext.text[:120]}")
