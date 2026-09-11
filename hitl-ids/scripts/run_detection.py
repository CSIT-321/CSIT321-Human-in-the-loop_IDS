"""
Run batch detection over a sample and populate a demo database (plan step S9).

    python scripts/run_detection.py                        # the 5,000-flow demo sample
    python scripts/run_detection.py --limit 200            # a short run
    python scripts/run_detection.py --replay data/processed/demo_ml_predictions_shap.json

The default path computes predictions and TreeSHAP explanations in the run itself (D8). `--replay`
reuses predictions an earlier run wrote, for a machine without xgboost; the summary records which of
the two it was.

Inputs:  data/processed/demo_sample.csv, data/processed/sample_manifest.json,
         models/ (the committed 8-class model), rules/rule-set-s4b-1.json
Output:  a SQLite database (default data/demo.db) plus a printed summary
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts import models as m  # noqa: E402
from packages.detection.pipeline import store  # noqa: E402
from packages.detection.pipeline.predictor import (  # noqa: E402
    MODEL_FILE,
    MODEL_VERSION,
    ReplayPredictor,
    XgboostPredictor,
)
from packages.detection.pipeline.runner import (  # noqa: E402
    open_database,
    run_detection,
    run_summary_row,
)
from packages.detection.pipeline.source import CsvReplaySource  # noqa: E402

PROCESSED = HITL / "data" / "processed"
MODELS = HITL / "models"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(HITL / "data" / "demo.db"))
    parser.add_argument("--sample", default=str(PROCESSED / "demo_sample.csv"))
    parser.add_argument("--limit", type=int, default=None, help="first N flows, timestamp order")
    parser.add_argument("--replay", default=None,
                        help="predictions JSON from run_ml_inference.py (skips model loading)")
    parser.add_argument("--seed", type=int, default=None, help="the sample's seed, for the run row")
    args = parser.parse_args()

    sample = Path(args.sample)
    if not sample.exists():
        print(f"missing {sample} - see data/README.md", file=sys.stderr)
        return 2

    manifest_path = PROCESSED / "sample_manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})
    demo = manifest.get("demo", {})
    seed = args.seed if args.seed is not None else manifest.get("seed")

    metrics_path = MODELS / "training-metrics.json"
    metrics = (json.loads(metrics_path.read_text(encoding="utf-8"))
               if metrics_path.exists() else {})

    source = CsvReplaySource(sample, limit=args.limit)
    predictor = ReplayPredictor(args.replay) if args.replay else XgboostPredictor()

    conn = open_database(args.database)
    try:
        now = m.utc_now()
        store.register_model(conn, version=MODEL_VERSION, model_file=MODEL_FILE, metrics=metrics,
                             now=now)
        dataset_id = store.register_dataset(
            conn, name="CSE-CIC-IDS2018 corrected - demo sample",
            version=f"demo-{seed}" if seed else "demo",
            source_file=f"data/processed/{sample.name}",
            total_records=int(demo.get("rows", 0)) or _row_count(sample),
            class_distribution=demo.get("classes", {}),
            preparation_meta={"seed": seed, "archive": manifest.get("archive"),
                              "attempted": demo.get("attempted")},
            now=now)
        conn.commit()
        summary = run_detection(conn, source, predictor, dataset_id=dataset_id, seed=seed, now=now)
    finally:
        conn.close()

    print(json.dumps(run_summary_row(summary), indent=2))
    print(f"\ndatabase: {args.database}")
    return 0


def _row_count(sample: Path) -> int:
    with sample.open(encoding="utf-8") as handle:
        return max(0, sum(1 for _ in handle) - 1)


if __name__ == "__main__":
    raise SystemExit(main())
