"""Read-only: count every routing branch on a routed copy and pick one real record per branch.
Usage: python flowtree_probe.py <routed copy>"""
import json
import sqlite3
import sys
from collections import Counter

c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
c.row_factory = sqlite3.Row

# 1. routing outcome x first reason rule (from the stored decision + reasons)
rows = c.execute("""SELECT o.operational_alert_ref ref, a.alert_ref al, a.evidence_class ev, a.combined_score sc,
    a.attack_category rule_cat, a.ml_predicted_class ml, a.severity sev, t.handling_route route, t.tier2_recommended rec,
    t.tier2_recommendation_reasons reasons, t.review_reason why, g.member_count n, g.id gid
    FROM operational_alerts_v2 o JOIN alerts a ON a.id=o.legacy_alert_id
    JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
    LEFT JOIN alert_groups g ON g.representative_operational_alert_id=o.id""").fetchall()
def branch(r):
    if r["route"] == "tier2_case": return "auto_E1"
    if r["rec"]:
        keys = sorted({s.split(":")[0] for s in json.loads(r["reasons"])})
        return "candidate:" + "+".join(keys)
    return "routine_group" if r["n"] else "routine_single"
count = Counter(branch(r) for r in rows)
print("branches", dict(count))
print("evidence x branch", dict(Counter((r["ev"], branch(r)) for r in rows)))
for b in count:
    pick = [r for r in rows if branch(r) == b]
    r = sorted(pick, key=lambda r: (-(r["n"] or 1), r["ref"]))[0]
    print(b, {k: r[k] for k in ("ref", "al", "ev", "sc", "rule_cat", "ml", "sev", "n")}, "|", (r["why"] or "")[:220])
# members of groups whose members are NOT all flagged the same way
print("auto groups", [(r["al"], r["n"], r["rule_cat"], r["sc"]) for r in rows if branch(r) == "auto_E1"])
for ref in ("AL-00478", "AL-03086", "AL-00576"):
    r = c.execute("""SELECT a.id, a.alert_ref, a.evidence_class, a.combined_score, a.severity, a.ml_predicted_class,
        a.attack_category, f.src_ip, gm.group_id FROM alerts a JOIN flow_data f ON f.alert_id=a.id
        LEFT JOIN alert_group_members gm ON gm.legacy_alert_id=a.id WHERE f.source_record_id=? OR a.alert_ref=?""",
        (ref, ref)).fetchone()
    print(ref, dict(r) if r else None)
