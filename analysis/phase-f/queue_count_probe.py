"""Build the operational-queue browser fixture into a temp file; count Tier 1 rows straight from SQL.
Shows whether the screen's 'Active Tier 1' number is right, independent of apps/api/operational_queue.py."""
import sqlite3
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[2] / 'hitl-ids'
sys.path[:0] = [str(HITL), str(HITL / 'tests'), str(HITL / 'apps/web/e2e')]
from operational_queue_fixture import build_queue_fixture  # noqa: E402
from apps.api.operational_queue import summary  # noqa: E402

path = Path(sys.argv[1])
path.unlink(missing_ok=True)
build_queue_fixture(path)
c = sqlite3.connect(path)
c.row_factory = sqlite3.Row
q = lambda sql: c.execute(sql).fetchall()
print('routes', [tuple(r) for r in q("SELECT handling_route, count(*) FROM operational_triage_state_v2 GROUP BY 1")])
print('tier1 by work status', [tuple(r) for r in q(
    "SELECT coalesce(w.status,'none'), count(*) FROM operational_triage_state_v2 t "
    "LEFT JOIN analyst_work w ON w.operational_alert_id=t.operational_alert_id "
    "WHERE t.handling_route='tier1_review' GROUP BY 1")])
s = summary(c).model_dump()
print('summary', {k: s[k] for k in ('total_alerts', 'tier1_review', 'tier1_groups', 'tier1_singles', 'active_alerts',
                                    'completed_work', 'escalated_work', 'tier2_cases', 'critical_alerts')})
