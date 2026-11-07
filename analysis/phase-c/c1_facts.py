"""C1 facts on a copy of the routed demo database. Read-only on a copy.

1. Groups: members per group, and whether members share the representative's family_key.
2. Families: how many legacy alerts a group's verdict could touch through family learning.
3. Existing feedback rows (would a V2 verdict amend an earlier legacy verdict?).
"""
import os
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c1-facts.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
c = sqlite3.connect(dst)
c.row_factory = sqlite3.Row

print("alert_groups columns:", [r[1] for r in c.execute("PRAGMA table_info(alert_groups)")])
print("alert_group_members columns:", [r[1] for r in c.execute("PRAGMA table_info(alert_group_members)")])

groups = c.execute("""SELECT g.id, g.representative_operational_alert_id rep, o.legacy_alert_id rep_legacy,
    a.family_key rep_family, a.evidence_class, t.handling_route
    FROM alert_groups g JOIN operational_alerts_v2 o ON o.id = g.representative_operational_alert_id
    JOIN alerts a ON a.id = o.legacy_alert_id
    JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id""").fetchall()
member_col = [r[1] for r in c.execute("PRAGMA table_info(alert_group_members)")]
legacy_col = next(x for x in member_col if "alert_id" in x and "group" not in x)
print(f"groups {len(groups)}; member column used: {legacy_col}")

sizes, same_family, mixed_family, family_sizes = Counter(), 0, [], []
for g in groups:
    members = c.execute(f"""SELECT m.{legacy_col} mid, a.family_key FROM alert_group_members m
        JOIN alerts a ON a.id = m.{legacy_col} WHERE m.group_id = ?""", (g["id"],)).fetchall()
    sizes[len(members)] += 1
    fams = {m["family_key"] for m in members}
    if fams == {g["rep_family"]}:
        same_family += 1
    else:
        mixed_family.append((g["id"], len(members), len(fams), g["handling_route"]))
    fam_n = c.execute("SELECT count(*) FROM alerts WHERE family_key = ?", (g["rep_family"],)).fetchone()[0] \
        if g["rep_family"] else 0
    family_sizes.append(fam_n)

print("members per group (size: groups):", dict(sorted(sizes.items())))
print(f"groups whose members all share the representative's family: {same_family} of {len(groups)}")
print("groups with members in other families (id, members, families, route), first 10:", mixed_family[:10])
print("routes of mixed groups:", Counter(x[3] for x in mixed_family))
print(f"representative family size: min {min(family_sizes)}, max {max(family_sizes)}, "
      f"total alerts in those families {sum(family_sizes)}")
print("routes:", Counter(g["handling_route"] for g in groups))
print("feedback_events rows:", c.execute("SELECT count(*) FROM feedback_events").fetchone()[0])
print("analyst_verdict_events rows:", c.execute("SELECT count(*) FROM analyst_verdict_events").fetchone()[0])
print("unflagged singles with family_key:", c.execute("""SELECT count(*) FROM operational_alerts_v2 o JOIN alerts a
    ON a.id=o.legacy_alert_id WHERE a.evidence_class='none' AND a.family_key IS NOT NULL""").fetchone()[0])
