"""Offline Suricata staging and read-only inbox inspection; operational admission is pending."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.detection.adapters.admission_policy import load_admission_policy
from packages.detection.adapters.staging import import_file, inspect_inbox


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--sensor-id")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", dest="listing")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.listing and (args.input or args.sensor_id or args.policy or args.dry_run):
        parser.error("--list cannot be combined with import options")
    if not args.listing and (args.input is None or args.sensor_id is None):
        parser.error("import requires --input and --sensor-id")
    try:
        if args.listing:
            print(json.dumps(inspect_inbox(args.database, args.limit), indent=2))
            return 0
        policy = load_admission_policy(args.policy) if args.policy else load_admission_policy()
        result = import_file(args.input, args.sensor_id, args.database,
                             policy=policy, dry_run=args.dry_run)
        print(json.dumps(result.as_dict(), indent=2))
        return 2 if result.invalid or result.rejected_by_policy else 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc), "operational_admission": "pending"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
