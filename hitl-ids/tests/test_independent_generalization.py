"""Generalisation check: do the retuned signature rules and the committed 8-class model still work
on a capture that was never used for training, rule calibration, or the demo sample?

Both S4b's rule thresholds and S4's trained model have only ever been measured against splits of
the one corrected CSE-CIC-IDS2018 capture this project uses throughout - demo_sample.csv,
train_sample.csv, and the held-out split inside S15's evaluation are all drawn from the same
source zip (see data/README.md). Scoring well there proves the rules and the model fit *that*
capture; it does not prove either generalises to a different one.

This test does not assert a pass/fail accuracy bar. Nobody has agreed what "good enough" looks
like on unseen data yet, and baking a number in here would be deciding that unilaterally instead
of with the team. It runs the real pipeline and computes the real metrics
(packages.evaluation.metrics, the same module S15's evaluation uses), then writes a report - so
the question has a concrete, reproducible answer the moment an independent capture exists, instead
of staying a stated-but-unverified gap.

To actually run this: point INDEPENDENT_CAPTURE at a flow-feature CSV in demo_sample.csv's own
shape (alert_id, attack_class, is_attempted, then the corrected release's own columns), and
INDEPENDENT_TRUTH at ground truth in demo_ground_truth.json's shape - both from a capture that was
not used in training, rule calibration, or the demo/train samples. Until then this test is
skipped, honestly, rather than silently not existing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.contracts import models as m
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import MODEL_FILE, MODEL_VERSION, XgboostPredictor
from packages.detection.pipeline.runner import open_database, run_detection, run_summary_row
from packages.detection.pipeline.source import CsvReplaySource
from packages.evaluation.metrics import detection_metrics, read_queue
from packages.evaluation.truth import GroundTruth

HITL = Path(__file__).resolve().parents[1]
#: Not committed, and not expected to exist until someone provides a genuinely independent
#: capture. This pair of paths is the one thing a reader needs to change to actually run this.
INDEPENDENT_CAPTURE = HITL / "data" / "independent" / "capture.csv"
INDEPENDENT_TRUTH = HITL / "data" / "independent" / "ground_truth.json"
REPORT_PATH = HITL / "data" / "processed" / "independent-generalization-report.json"


@pytest.mark.skipif(
    not (INDEPENDENT_CAPTURE.exists() and INDEPENDENT_TRUTH.exists()),
    reason="no independent capture yet - see this file's module docstring")
def test_rules_and_model_on_a_capture_they_were_never_tuned_against(tmp_path):
    conn = open_database(str(tmp_path / "independent.db"))
    try:
        now = m.utc_now()
        store.register_model(conn, version=MODEL_VERSION, model_file=MODEL_FILE, metrics={},
                             now=now)
        dataset_id = store.register_dataset(
            conn, name="independent capture", version="independent-1",
            source_file=str(INDEPENDENT_CAPTURE.relative_to(HITL)),
            total_records=0, class_distribution={}, preparation_meta=None, now=now)
        conn.commit()

        source = CsvReplaySource(INDEPENDENT_CAPTURE)
        summary = run_detection(conn, source, XgboostPredictor(), dataset_id=dataset_id, now=now)

        truth = GroundTruth.load(INDEPENDENT_TRUTH)
        queue = read_queue(conn, truth)
        metrics = detection_metrics(queue)
    finally:
        conn.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps({"run_summary": run_summary_row(summary), "detection_metrics": metrics},
                  indent=2),
        encoding="utf-8")
    print(json.dumps(metrics, indent=2))

    # Sanity, not a verdict: the pipeline must run end to end and produce metrics in range.
    # Whether the numbers are *good enough* is a team decision once there are real numbers to
    # look at - deliberately not decided here.
    assert summary.alerts > 0
    assert 0.0 <= metrics["macro_f1"] <= 1.0
