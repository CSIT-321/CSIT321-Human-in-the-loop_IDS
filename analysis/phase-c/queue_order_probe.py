"""D4 condition 2 in code: measure the queue order before vs after on routed copies. Read-only on copies.

For each database: full order with the old ORDER BY and with the new one; the first position of an unflagged item
and the last position of a flagged one; how many positions changed; and the time of queue_page(50) and of the
last page.
"""
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

TEMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
OLD = f"{q.VALID_PRIORITY} DESC, queue_occurred_at(a.occurred_at) DESC, a.operational_alert_ref ASC"


def order(conn, clause):
    conn.create_function("queue_occurred_at", 1, q.occurred_key, deterministic=True)
    return [r[0] for r in conn.execute(f"SELECT a.id {q.SOURCE} ORDER BY {clause}")]


for name in ("run-c/demo.db", "run-d4-stress/stress.db"):
    src = TEMP / name
    if not src.exists():
        print(name, "MISSING"); continue
    dst = TEMP / ("q-order-" + src.name)
    shutil.copy(src, dst)
    with closing(db.connect(str(dst))) as conn:
        unflagged = {r[0] for r in conn.execute(
            "SELECT o.id FROM operational_alerts_v2 o JOIN alerts a ON a.id=o.legacy_alert_id WHERE a.evidence_class='none'")}
        before, after = order(conn, OLD), order(conn, q.QUEUE_ORDER)
        def edges(seq):
            first_unflagged = next((i for i, x in enumerate(seq, 1) if x in unflagged), None)
            last_flagged = max((i for i, x in enumerate(seq, 1) if x not in unflagged), default=None)
            return first_unflagged, last_flagged
        moved = sum(1 for x, y in zip(before, after) if x != y)
        t0 = time.perf_counter(); q.queue_page(conn, limit=50, offset=0); t1 = time.perf_counter()
        q.queue_page(conn, limit=50, offset=max(0, len(after) - 50)); t2 = time.perf_counter()
        print(f"{name}: items {len(after)}, unflagged {len(unflagged)}")
        print(f"  before: first unflagged rank, last flagged rank = {edges(before)}")
        print(f"  after:  first unflagged rank, last flagged rank = {edges(after)}")
        print(f"  positions changed: {moved}; same set: {set(before) == set(after)}")
        print(f"  queue_page(50) first page {1000*(t1-t0):.0f} ms, last page {1000*(t2-t1):.0f} ms")
