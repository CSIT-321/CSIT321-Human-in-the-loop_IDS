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

FLAGGED = "SELECT id FROM alerts WHERE evidence_class != 'none' ORDER BY id"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.exists():
        print(f"no database at {args.database}", file=sys.stderr)
        return 2
    with closing(db.connect(args.database)) as conn:
        created, existing = materialize_flagged(conn)
    print(f"created {created}, already present {existing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
