"""Reproduce the routing failure and print the reason lengths per group."""
import sqlite3
import sys
from contextlib import closing

sys.path.insert(0, ".")
from packages.contracts import db
from packages.detection.flow_routing import load_flow_routing_policy, route_group
from packages.detection.ranking.severity import load_severity_chart
import scripts.materialize_flow_queue as mq

path = r"C:\Users\Glenn Ang\AppData\Local\Temp\hitl-review\run-c\demo.db"
conn = sqlite3.connect(path)
policy = load_flow_routing_policy()
chart = load_severity_chart()
rows = conn.execute("""SELECT g.id, gm.legacy_alert_id, a.evidence_class, a.combined_score, a.ml_predicted_class, a.attack_category
                       FROM alert_group_members gm JOIN alert_groups g ON g.id = gm.group_id JOIN alerts a ON a.id = gm.legacy_alert_id
                       ORDER BY g.first_seen_at, g.id, gm.occurred_at, gm.legacy_alert_id""").fetchall()
from collections import defaultdict
groups = defaultdict(list)
for gid, aid, ev, score, ml, cat in rows:
    groups[gid].append((aid, ev, score, ml, cat))
print("groups:", {k: len(v) for k, v in groups.items()})
import packages.contracts.models as m
for gid, members in groups.items():
    ms = [m.Alert.model_construct(evidence_class=ev, combined_score=score, ml_predicted_class=ml, attack_category=cat)
          for _, ev, score, ml, cat in members]
    route = route_group(ms, policy, chart)
    reason = " ".join(route.decision.reasons + route.tier2_reasons)
    print(gid, "route:", route.decision.route, "members:", len(members), "reason_len:", len(reason), "tier2_reasons:", len(route.tier2_reasons))
