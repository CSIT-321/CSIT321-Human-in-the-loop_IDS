"""Call route_flow_alert with SQL tracing to catch which statement violates the reason CHECK."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from packages.contracts import db
from packages.detection.flow_routing import load_flow_routing_policy, route_flow_alert
from packages.detection.ranking.severity import load_severity_chart
from materialize_flow_queue import UNROUTED, MEMBERS

path = r"C:\Users\Glenn Ang\AppData\Local\Temp\hitl-review\run-c\demo.db"
conn = db.connect(path)
conn.set_trace_callback(lambda stmt: print("STMT: " + stmt[:300].replace("\n", " "), flush=True))
policy = load_flow_routing_policy()
chart = load_severity_chart()
for group_id, first_seen, rep in conn.execute(UNROUTED).fetchall():
    members = [db.from_row(__import__("packages.contracts.models", fromlist=["Alert"]).Alert, row)
               for row in conn.execute(MEMBERS, (group_id,))]
    print(f"\n=== group {group_id} members {len(members)} rep {rep}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        outcome, qualifying = route_flow_alert(conn, rep, policy=policy, chart=chart, group_members=members,
                                               qualifying_member_alert_id=members[0].id)
        print("outcome", outcome)
        conn.commit()
    except Exception as e:
        print("FAILED:", e)
        conn.rollback()
        break
