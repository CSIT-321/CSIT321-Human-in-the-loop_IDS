"""B6 behaviour baseline: for every V2 alert in a mixed database, record what each consumer answers.

Run before and after the B6 refactor; the two JSON outputs must be identical. Uses only public functions
that exist both before and after (is_tier1_work, read_verdict.can_record, read_review.eligible_alert,
allowed_actions via the routing view, queue summary counts).
    python b6_baseline.py <out.json>
"""
import json
import shutil
import sqlite3
import sys
import os
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL), str(HITL / "scripts"), str(HITL / "tests")]
os.chdir(HITL)

from packages.contracts import db  # noqa: E402
from packages.detection import analyst_verdict, analyst_work, routing, selective_review  # noqa: E402
from packages.detection.adapters.operational_v2 import read_triage  # noqa: E402
from apps.api import operational_queue  # noqa: E402

src = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\b6-mixed.db"))
out = {}
with closing(db.connect(str(src))) as conn:
    actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
    for alert_id, ref in conn.execute("SELECT id, operational_alert_ref FROM operational_alerts_v2 ORDER BY id"):
        state = read_triage(conn, alert_id)
        try:
            actions = list(routing.allowed_actions(state))
        except TypeError:  # after B6 the status is required
            from packages.detection.tier1_eligibility import tier1_status
            actions = list(routing.allowed_actions(state, tier1_status(conn, alert_id, state)))
        out[str(alert_id)] = {
            "route": [state.handling_route, state.workflow_stage],
            "tier1_work": analyst_work.is_tier1_work(conn, alert_id),
            "can_record": analyst_verdict.read_verdict(conn, ref, actor).can_record,
            "review_eligible": selective_review.read_review(conn, ref).eligible_alert,
            "actions": actions,
        }
    out["summary"] = operational_queue.summary(conn).model_dump(mode="json")
    out["review_metrics"] = selective_review.review_metrics(conn).model_dump(mode="json")
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
print(len(out) - 2, "alerts recorded ->", sys.argv[1])
