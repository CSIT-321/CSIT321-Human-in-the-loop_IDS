"""Read-only: pick the SOC-flow spec's alerts on a routed demo copy, the way the fixture will."""
import os, sqlite3, sys
p = sys.argv[1] if len(sys.argv) > 1 else os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review\walk.db')
c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
print(c.execute("SELECT handling_route, tier2_recommended, decision_source, count(*) FROM operational_triage_state_v2 GROUP BY 1,2,3").fetchall())
base = """SELECT o.operational_alert_ref, g.member_count, o.detection_category, t.operational_priority, t.priority_band
FROM alert_groups g JOIN operational_alerts_v2 o ON o.id=g.representative_operational_alert_id
JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id"""
for label, where in (('auto', "t.handling_route='tier2_case'"),
                     ('recommended', "t.handling_route='tier1_review' AND t.tier2_recommended=1"),
                     ('routine', "t.handling_route='tier1_review' AND t.tier2_recommended=0")):
    rows = c.execute(f"{base} WHERE {where} ORDER BY t.operational_priority DESC, g.member_count DESC, o.operational_alert_ref LIMIT 4").fetchall()
    print(label, rows)
print('cases', c.execute("SELECT case_ref, decision_source, owner_actor_id FROM tier2_cases").fetchall())
