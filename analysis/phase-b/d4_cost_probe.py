"""D4 cost probe: project and route every unflagged flow as its own queue item, on a copy.

Copies run-c/demo.db (already grouped and routed), then for each unflagged flow alert:
materialize_source -> route_flow_alert(group_members=[alert]). Measures time, routes, the
queue page and summary timings, and where the 6 missed attacks land. Product code is unchanged.
"""
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL), str(HITL / "scripts")]
os.chdir(HITL)

from packages.contracts import db, models as m  # noqa: E402
from packages.detection.flow_routing import load_flow_routing_policy, route_flow_alert  # noqa: E402
from packages.detection.ranking.severity import load_severity_chart  # noqa: E402
from packages.detection.adapters.operational_v2 import materialize_source  # noqa: E402

src = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\run-c\demo.db"))
dst = src.with_name("demo-d4.db")
shutil.copy(src, dst)

with closing(db.connect(str(dst))) as conn:
    policy, chart = load_flow_routing_policy(), load_severity_chart()
    ids = [r[0] for r in conn.execute("SELECT id FROM alerts WHERE evidence_class='none' ORDER BY id")]
    t0 = time.perf_counter()
    outcomes = Counter()
    for legacy_id in ids:
        projected = materialize_source(conn, "legacy_flow_alert", legacy_id)
        conn.execute("BEGIN IMMEDIATE")
        try:
            alert = db.from_row(m.Alert, conn.execute("SELECT * FROM alerts WHERE id=?", (legacy_id,)).fetchone())
            outcome, _ = route_flow_alert(conn, projected.id, policy=policy, chart=chart, group_members=[alert])
            outcomes[outcome] += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    elapsed = time.perf_counter() - t0
    print(f"projected+routed {len(ids)} unflagged in {elapsed:.1f} s ({elapsed / len(ids) * 1000:.0f} ms each): {dict(outcomes)}")
    print("operational_alerts_v2 rows:", conn.execute("SELECT COUNT(*) FROM operational_alerts_v2").fetchone()[0])

    from apps.api import operational_queue  # noqa: E402
    t0 = time.perf_counter()
    total, page = operational_queue.queue_page(conn, limit=50, offset=0)
    print(f"queue_page(50): total {total}, {1000 * (time.perf_counter() - t0):.0f} ms")

    truth = json.load(open(HITL / "data/processed/demo_ground_truth.json"))
    missed = [r for r in conn.execute(
        """SELECT f.source_record_id, t.handling_route, t.queue_priority, t.tier2_recommended
           FROM operational_alerts_v2 o JOIN flow_data f ON f.alert_id=o.legacy_alert_id
           JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id""")
        if truth[r[0]]["groundTruth"] != "benign" and r[0] in {
            x[0] for x in conn.execute("SELECT f.source_record_id FROM alerts a JOIN flow_data f ON f.alert_id=a.id "
                                       "WHERE a.evidence_class='none'")}]
    print("missed attacks now in the queue:", missed)
    print("priority bands, flagged groups vs unflagged:",
          conn.execute("""SELECT CASE WHEN a.evidence_class='none' THEN 'unflagged' ELSE 'group' END,
                                 MIN(t.queue_priority), MAX(t.queue_priority)
                          FROM operational_alerts_v2 o JOIN alerts a ON a.id=o.legacy_alert_id
                          JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id GROUP BY 1""").fetchall())
