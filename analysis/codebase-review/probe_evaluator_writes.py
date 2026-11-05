"""Probe: can the evaluator account (role 'evaluator') write analyst verdicts, notes and status?

Runs against a throw-away copy of the synthetic test database via TestClient. Never touches data/demo.db.
"""
import shutil
import sys
import tempfile
from pathlib import Path

H = Path(__file__).resolve().parents[2] / "hitl-ids"
sys.path.insert(0, str(H))
sys.path.insert(0, str(H / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from apps.api import auth  # noqa: E402
from apps.api.main import create_app  # noqa: E402
from packages.contracts import db, models as m  # noqa: E402

source = Path(sys.argv[1])
work = Path(tempfile.mkdtemp()) / "probe.db"
shutil.copy(source, work)
conn = db.connect(str(work))
db.migrate(conn)
auth.ensure_demo_accounts(conn)
user = db.from_row(m.User, conn.execute("SELECT * FROM users WHERE username='evaluator'").fetchone())
ref = conn.execute("SELECT alert_ref FROM alerts WHERE evidence_class != 'none' ORDER BY id LIMIT 1").fetchone()[0]
conn.commit()
conn.close()
api = TestClient(create_app(work))
api.headers.update({"Authorization": f"Bearer {auth.encode_token(user)}"})
print("caller role:", user.role, "| alert", ref)
calls = {
    "feedback": api.post(f"/api/alerts/{ref}/feedback",
                         json={"category": "mark_false_positive", "note": "probe by evaluator"}),
    "note": api.post(f"/api/alerts/{ref}/notes", json={"body": "probe note by evaluator"}),
    "status": api.post(f"/api/alerts/{ref}/status", json={"status": "in_progress"}),
}
for name, response in calls.items():
    print(f"{name:<9} -> {response.status_code} {response.text[:160]}")
check = db.connect(str(work))
print("feedback_events by evaluator:", check.execute(
    "SELECT count(*) FROM feedback_events WHERE user_id=?", (user.id,)).fetchone()[0])
