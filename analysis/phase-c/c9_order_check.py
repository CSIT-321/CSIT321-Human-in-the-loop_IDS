"""C9 check: does the served Tier 1 queue order match the approved severity-first order (settled decision 8)?

Approved: packages/contracts/db.py queue_order() = severity worst first, then combined_score DESC, then id.
Served:   apps/api/operational_queue.py QUEUE_ORDER = unflagged last, then operational_priority DESC, time, ref.
Compare on a copy of the routed demo database, over the legacy flow alerts in the queue. Read-only on a copy.
"""
import os
import shutil
import sys
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL)]
from apps.api import operational_queue as q  # noqa: E402
from packages.contracts import db  # noqa: E402

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c9-demo.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
SEV = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

with closing(db.connect(str(dst))) as conn:
    conn.create_function("queue_occurred_at", 1, q.occurred_key, deterministic=True)
    served = [r[0] for r in conn.execute(f"SELECT a.legacy_alert_id {q.SOURCE} ORDER BY {q.QUEUE_ORDER}")]
    approved = [r[0] for r in conn.execute(
        f"SELECT a.id FROM alerts a WHERE a.id IN (SELECT legacy_alert_id FROM operational_alerts_v2) "
        f"ORDER BY {db.queue_order('a')}")]
    info = {r["id"]: r for r in conn.execute("SELECT id, alert_ref, severity, combined_score, evidence_class FROM alerts")}
    pr = {r[0]: r[1] for r in conn.execute(
        "SELECT o.legacy_alert_id, t.operational_priority FROM operational_alerts_v2 o "
        "JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id")}

print(f"queue items: served {len(served)}, approved-order set {len(approved)}")
# Flagged groups appear in the queue by their representative only, so compare on the served set.
served_set = set(served)
approved = [x for x in approved if x in served_set]
same = sum(1 for a, b in zip(served, approved) if a == b)
print(f"same position: {same} of {len(served)}")

# Severity inversions in the served order: a lower severity item placed above a higher severity one.
inversions, examples, worst = 0, [], 0
max_after = 0
for i in range(len(served) - 1, -1, -1):
    s = SEV.get(info[served[i]]["severity"], 0)
    if s < max_after:
        inversions += 1
    max_after = max(max_after, s)
seen_max_below = {}
print(f"items placed above some higher-severity item (served order): {inversions}")

for label, order in (("served", served), ("approved", approved)):
    print(f"\n{label} top 12:")
    for x in order[:12]:
        r = info[x]
        print(f"  {r['alert_ref']:9} sev={r['severity']:8} combined={r['combined_score']:6.2f} "
              f"opprio={pr.get(x)} evidence={r['evidence_class']}")

# Where do the highest-severity items sit in the served order?
crit = [i for i, x in enumerate(served, 1) if info[x]["severity"] == "Critical"]
high = [i for i, x in enumerate(served, 1) if info[x]["severity"] == "High"]
print(f"\nCritical: {len(crit)} items, served ranks {crit[:10]}{' ...' if len(crit) > 10 else ''}")
print(f"High: {len(high)} items, served ranks min {min(high) if high else None} max {max(high) if high else None}")
from collections import Counter
print("severity by tier (served):", Counter((info[x]["evidence_class"] != "none", info[x]["severity"]) for x in served))
