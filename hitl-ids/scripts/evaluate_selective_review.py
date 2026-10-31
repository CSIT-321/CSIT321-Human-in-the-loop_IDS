"""Read-only V2 counterfactual. Optional labels are evaluation-only UUID->outcome JSON."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from packages.evaluation.selective_review import evaluate_counterfactual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--labels',type=Path)
    args=parser.parse_args()
    labels=json.loads(args.labels.read_text(encoding='utf-8')) if args.labels else None
    if labels is not None and not isinstance(labels,dict):raise ValueError('labels must be a UUID-to-outcome object')
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        conn.execute('BEGIN')
        print(json.dumps(evaluate_counterfactual(conn,labels),indent=2))


if __name__=='__main__':main()
