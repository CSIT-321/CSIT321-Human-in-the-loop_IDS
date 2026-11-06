"""Review checks for commit 82263b2 (grouping, method B), run on the routed copy run-c/demo.db.

R1  representative = first member by (occurred_at, legacy_alert_id)?
R2  qualifying member = the member that met E1 (escalated groups)?
R3  all E1 flows sit in escalated groups?
R4  timestamp format and missing timestamps
"""
import os
import sqlite3
import sys
from collections import Counter

path = os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\run-c\demo.db")
c = sqlite3.connect(path)

print("R1 representative vs first member")
bad = 0
groups = c.execute("SELECT id, representative_operational_alert_id, qualifying_member_alert_id, case_ref, member_count FROM alert_groups").fetchall()
for gid, rep, qual, case_ref, n in groups:
    first = c.execute("SELECT legacy_alert_id FROM alert_group_members WHERE group_id=? "
                      "ORDER BY occurred_at, legacy_alert_id LIMIT 1", (gid,)).fetchone()[0]
    rep_legacy = c.execute("SELECT legacy_alert_id FROM operational_alerts_v2 WHERE id=?", (rep,)).fetchone()[0]
    if rep_legacy != first:
        bad += 1
print(f"  groups {len(groups)}, representative is not the first member in {bad}")

print("R2 qualifying member in escalated groups")
E1 = "a.evidence_class='corroborated' AND a.combined_score >= 80"
for gid, rep, qual, case_ref, n in groups:
    if case_ref is None:
        continue
    first_e1 = c.execute(f"SELECT gm.legacy_alert_id FROM alert_group_members gm JOIN alerts a ON a.id=gm.legacy_alert_id "
                         f"WHERE gm.group_id=? AND {E1} ORDER BY gm.occurred_at, gm.legacy_alert_id LIMIT 1", (gid,)).fetchone()
    qual_is_e1 = c.execute(f"SELECT COUNT(*) FROM alerts a WHERE a.id=? AND {E1}", (qual,)).fetchone()[0]
    print(f"  group {gid} n={n} qualifying={qual} first E1 member={first_e1[0] if first_e1 else None} qualifying meets E1={bool(qual_is_e1)}")
nonesc_qual = c.execute("SELECT COUNT(*) FROM alert_groups g JOIN operational_system_routing s "
                        "ON s.operational_alert_id=g.representative_operational_alert_id "
                        "WHERE g.case_ref IS NULL AND g.qualifying_member_alert_id IS NOT NULL "
                        "AND json_array_length(COALESCE((SELECT tier2_recommendation_reasons FROM operational_triage_state_v2 t "
                        "WHERE t.operational_alert_id=g.representative_operational_alert_id),'[]'))=0").fetchone()[0]
print(f"  routine groups that still carry a 'qualifying' member: {nonesc_qual}")

print("R3 E1 flows by group route")
rows = c.execute(f"""SELECT CASE WHEN g.case_ref IS NULL THEN 'not escalated' ELSE 'escalated' END, COUNT(*)
                     FROM alerts a JOIN alert_group_members gm ON gm.legacy_alert_id=a.id
                     JOIN alert_groups g ON g.id=gm.group_id WHERE {E1} GROUP BY 1""").fetchall()
print("  ", rows, " total E1 flagged:", c.execute(f"SELECT COUNT(*) FROM alerts a WHERE {E1}").fetchone()[0])
print("   escalated groups:", c.execute("SELECT grouping_key, member_count FROM alert_groups WHERE case_ref IS NOT NULL").fetchall())

print("R4 timestamps")
ts = [r[0] for r in c.execute("SELECT json_extract(flow_features,'$.Timestamp') FROM flow_data f JOIN alerts a ON a.id=f.alert_id "
                              "WHERE a.evidence_class != 'none'")]
print("  missing:", sum(1 for t in ts if not t), " sample:", ts[:2])
print("  group first_seen sample:", c.execute("SELECT first_seen_at FROM alert_groups LIMIT 2").fetchall())
print("  member occurred_at = 0001-01-01 (missing ts):",
      c.execute("SELECT COUNT(*) FROM alert_group_members WHERE occurred_at LIKE '0001%'").fetchone()[0])

print("R5 unflagged alerts in queue (decision D4 = all 5,000)")
print("  alerts:", c.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
      " flagged:", c.execute("SELECT COUNT(*) FROM alerts WHERE evidence_class != 'none'").fetchone()[0],
      " operational_alerts_v2:", c.execute("SELECT COUNT(*) FROM operational_alerts_v2").fetchone()[0])
