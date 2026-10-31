"""Read-only prospective-recorded export/evaluation. Never opens a collection run."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from packages.evaluation.prospective_recorded import RecordedArchive,load_recorded_database,evaluate_recorded,render_recorded_markdown


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--database',type=Path)
    source.add_argument('--archive',type=Path)
    parser.add_argument('--run-ref')
    parser.add_argument('--export',action='store_true')
    parser.add_argument('--format',choices=('json','markdown'),default='json')
    args=parser.parse_args()
    if args.database and not args.run_ref: parser.error('--database requires --run-ref')
    if args.archive and args.run_ref: parser.error('--run-ref cannot override a frozen archive')
    archive=load_recorded_database(args.database,args.run_ref) if args.database else RecordedArchive.model_validate_json(args.archive.read_text(encoding='utf-8'))
    if args.export:
        if args.format!='json': parser.error('archives are JSON')
        print(json.dumps(archive.model_dump(mode='json',by_alias=True),indent=2,sort_keys=True,allow_nan=False))
    else:
        report=evaluate_recorded(archive)
        print(render_recorded_markdown(report) if args.format=='markdown' else json.dumps(report,indent=2,sort_keys=True,allow_nan=False))


if __name__=='__main__': main()
