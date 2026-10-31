"""Read-only V2 triage-policy preview. Does not apply policy or admit alerts to the queue."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.adapters.staging import open_readonly
from packages.detection.triage_policy import TriageContext, evaluate_triage, load_triage_policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--operational-alert-id", type=int, required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    try:
        context = TriageContext.model_validate_json(args.context.read_text(encoding="utf-8")) if args.context else TriageContext()
        policy = load_triage_policy(args.policy) if args.policy else load_triage_policy()
        with closing(open_readonly(args.database)) as conn:
            alert = read_projection(conn, args.operational_alert_id)
            result = evaluate_triage(alert, context, policy)
        print(json.dumps({"mode": "preview_only", "operationalAdmission": "pending",
                          "context": context.model_dump(mode="json", by_alias=True),
                          "result": result.model_dump(mode="json", by_alias=True)}, indent=2))
        return 0
    except (OSError, ValueError, LookupError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
