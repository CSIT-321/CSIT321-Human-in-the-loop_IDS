"""Project flagged flow alerts into the operational queue as groups (phase A, method B).

The operational workstation reads only ``operational_alerts_v2``. Detection writes ``alerts``, so on a
detection database the workstation is empty until this runs. The grouping, projection and routing code is
packages/detection/flow_queue.py; this file is its command line.

    python scripts/materialize_flow_queue.py --database data/demo.db
"""
from __future__ import annotations

import argparse
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.contracts import db  # noqa: E402
from packages.detection.flow_queue import (  # noqa: E402,F401  (re-exported: the tests import them from here)
    group_flagged, materialize_flagged, materialize_unflagged, route_flagged, route_unflagged,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.exists():
        print(f"no database at {args.database}", file=sys.stderr)
        return 2
    with closing(db.connect(args.database)) as conn:
        members, new_groups, existing = materialize_flagged(conn)
        counts = route_flagged(conn)
        singles = materialize_unflagged(conn)
        single_counts = route_unflagged(conn)
    print(f"grouped {members} alerts into {new_groups} new groups, already grouped {existing}")
    print("routed: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"projected {singles} unflagged flows as single items")
    print("routed unflagged: " + ", ".join(f"{k} {v}" for k, v in single_counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
