"""Read-only V2 projection/inspection. Does not materialize, migrate, route, or change the queue."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.detection.adapters.operational_v2 import preview_source, read_projection, read_triage
from packages.detection.adapters.staging import open_readonly


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--legacy-alert-id", type=int)
    source.add_argument("--external-inbox-id", type=int)
    source.add_argument("--operational-alert-id", type=int)
    args = parser.parse_args()
    try:
        with closing(open_readonly(args.database)) as conn:
            conn.execute("BEGIN")
            if args.operational_alert_id is not None:
                alert = read_projection(conn, args.operational_alert_id)
                triage = read_triage(conn, args.operational_alert_id).model_dump(mode="json", by_alias=True)
            else:
                legacy = args.legacy_alert_id is not None
                alert = preview_source(conn, "legacy_flow_alert" if legacy else "external_nids_alert",
                                       args.legacy_alert_id if legacy else args.external_inbox_id)
                triage = None
            print(json.dumps({"operationalAdmission": "pending", "routingPolicy": "inactive",
                              "alert": alert.model_dump(mode="json", by_alias=True), "triage": triage}, indent=2))
        return 0
    except (OSError, ValueError, LookupError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
