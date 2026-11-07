"""C9 effect on a copy of the routed demo database: old order (D4 only) vs new order (severity first).
Also: a Suricata alert's stored native_severity and category, as the real EVE adapter wrote them (fixture file).
Read-only on copies.
"""
import json
import os
import shutil
import sys
import time
from contextlib import closing
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path[:0] = [str(HITL)]
from apps.api import operational_queue as q  # noqa: E402
from packages.contracts import db  # noqa: E402
from packages.detection.queue_severity import severity_label, severity_rank  # noqa: E402
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput  # noqa: E402

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
dst = TEMP / "c9-after.db"
shutil.copy(TEMP / "run-c" / "demo.db", dst)
OLD = f"{q.UNFLAGGED_LAST} ASC, {q.VALID_PRIORITY} DESC, queue_occurred_at(a.occurred_at) DESC, a.operational_alert_ref ASC"
SEV = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Informational": 0}

with closing(db.connect(str(dst))) as conn:
    conn.create_function("queue_occurred_at", 1, q.occurred_key, deterministic=True)
    conn.create_function("queue_severity_rank", 4, severity_rank, deterministic=True)
    info = {r[0]: r for r in conn.execute(
        "SELECT o.id, x.severity, x.evidence_class FROM operational_alerts_v2 o JOIN alerts x ON x.id=o.legacy_alert_id")}
    old = [r[0] for r in conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {OLD}")]
    new = [r[0] for r in conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {q.QUEUE_ORDER}")]
    for _ in range(2):
        t = time.perf_counter(); q.queue_page(conn, limit=50, offset=0); a = time.perf_counter() - t
        t = time.perf_counter(); conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {OLD} LIMIT 50").fetchall(); b = time.perf_counter() - t
        print(f"first page: new {1000*a:.0f} ms, old order {1000*b:.0f} ms")


def inversions(order):
    worst_below, count = -1, 0
    for x in reversed(order):
        s = SEV[info[x][1]]
        count += s < worst_below
        worst_below = max(worst_below, s)
    return count


def tiers(order):
    first_unflagged = next(i for i, x in enumerate(order, 1) if info[x][2] == "none")
    last_flagged = max(i for i, x in enumerate(order, 1) if info[x][2] != "none")
    return first_unflagged, last_flagged


print(f"items {len(new)}; same set {set(old) == set(new)}; positions changed {sum(a != b for a, b in zip(old, new))}")
print(f"severity inversions: old {inversions(old)}, new {inversions(new)}")
print(f"(first unflagged rank, last flagged rank): old {tiers(old)}, new {tiers(new)}")
crit_old = [i for i, x in enumerate(old, 1) if info[x][1] == "Critical"]
crit_new = [i for i, x in enumerate(new, 1) if info[x][1] == "Critical"]
print(f"Critical ranks: old max {max(crit_old)}, new max {max(crit_new)} (count {len(crit_new)})")
print("new top 50 by severity:", {k: sum(1 for x in new[:50] if info[x][1] == k) for k in SEV})
unflagged_above = [(i, info[x][1]) for i, x in enumerate(new, 1) if info[x][2] == "none" and i <= tiers(new)[1]]
print("unflagged items above the last flagged one (new):", unflagged_above[:10])

# Suricata path with real adapter output from the committed fixture.
events = json.loads((HITL / "tests/fixtures/suricata-alerts.json").read_text(encoding="utf-8"))
events = events if isinstance(events, list) else events.get("events", events)
for i, e in enumerate(events[:4]):
    c = SuricataEveAdapter().adapt(SuricataOutput(event=e, raw_event_reference=f"fixture:{i}"))
    native = json.dumps(c.detector_severity)
    print(f"suricata fixture {i}: category={c.detection_category!r} native={native} -> "
          f"{severity_label('external_nids_alert', None, native, c.detection_category)}")
