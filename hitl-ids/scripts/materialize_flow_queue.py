"""Project every flagged flow alert into the operational queue (tier views, phase A).

The operational workstation reads only ``operational_alerts_v2``. Detection writes ``alerts``, so on a
detection database the workstation is empty until this runs. It calls the existing
``materialize_source`` once per flagged alert: idempotent, one short transaction each, and it never
writes the legacy workflow's tables.

Unflagged flows (``evidence_class = 'none'``) are not queue work and are not projected.

    python scripts/materialize_flow_queue.py --database data/demo.db
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.contracts import db  # noqa: E402
from packages.detection.adapters.operational_v2 import materialize_source  # noqa: E402
from packages.detection.flow_routing import load_flow_routing_policy, route_flow_alert  # noqa: E402
from packages.detection.ranking.severity import load_severity_chart  # noqa: E402

FLAGGED = "SELECT id FROM alerts WHERE evidence_class != 'none' ORDER BY id"
UNROUTED = """SELECT o.id FROM operational_alerts_v2 o
    JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id
    LEFT JOIN operational_system_routing s ON s.operational_alert_id = o.id
    WHERE o.source_kind = 'legacy_flow_alert' AND s.operational_alert_id IS NULL
      AND t.handling_route = 'unassigned' AND t.workflow_stage = 'staged'
    ORDER BY o.id"""


def materialize_flagged(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (created, already present). Re-running creates nothing."""
    db.migrate(conn)
    present = {row[0] for row in conn.execute(
        "SELECT legacy_alert_id FROM operational_alerts_v2 WHERE source_kind = 'legacy_flow_alert'")}
    created = existing = 0
    for (alert_id,) in conn.execute(FLAGGED).fetchall():
        if alert_id in present:
            existing += 1
            continue
        materialize_source(conn, "legacy_flow_alert", alert_id)
        created += 1
    return created, existing


def route_flagged(conn: sqlite3.Connection, *, policy=None) -> dict[str, int]:
    """Give every projected, not yet routed flow alert its one system routing decision (phase B).

    One transaction per alert, so a failure leaves earlier decisions in place and a re-run continues.
    Returns counts by outcome; a second run returns all zeros.
    """
    policy = policy or load_flow_routing_policy()
    chart = load_severity_chart()
    counts = {"auto_escalated": 0, "candidate": 0, "routine": 0}
    for (operational_id,) in conn.execute(UNROUTED).fetchall():
        conn.execute("BEGIN IMMEDIATE")
        try:
            counts[route_flow_alert(conn, operational_id, policy=policy, chart=chart)] += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.exists():
        print(f"no database at {args.database}", file=sys.stderr)
        return 2
    with closing(db.connect(args.database)) as conn:
        created, existing = materialize_flagged(conn)
        counts = route_flagged(conn)
    print(f"created {created}, already present {existing}")
    print("routed: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
