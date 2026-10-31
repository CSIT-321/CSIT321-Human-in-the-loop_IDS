"""Read-only temporal holdout; JSON/Markdown to stdout, never writes the source database."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from packages.evaluation.temporal_fixture import SCENARIOS, synthetic_archive
from packages.evaluation.temporal_review import TemporalArchive, evaluate_temporal, render_markdown
from packages.evaluation.temporal_source import load_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic', choices=SCENARIOS)
    source.add_argument('--archive', type=Path)
    source.add_argument('--database', type=Path)
    parser.add_argument('--policy-history', type=Path)
    parser.add_argument('--holdout-start')
    parser.add_argument('--holdout-end')
    parser.add_argument('--format', choices=('json', 'markdown'), default='json')
    args = parser.parse_args()
    if args.database:
        if not all((args.policy_history, args.holdout_start, args.holdout_end)):
            parser.error('--database requires --policy-history, --holdout-start and --holdout-end; dates are never inferred')
        archive = load_database(args.database, json.loads(args.policy_history.read_text(encoding='utf-8')),
            args.holdout_start, args.holdout_end)
    else:
        if any((args.policy_history, args.holdout_start, args.holdout_end)):
            parser.error('database history arguments cannot override an archive or synthetic scenario')
        archive = synthetic_archive(args.synthetic) if args.synthetic else TemporalArchive.model_validate_json(args.archive.read_text(encoding='utf-8'))
    report = evaluate_temporal(archive)
    print(render_markdown(report) if args.format=='markdown' else json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
