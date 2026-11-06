"""A synthetic capture with known groups (method B, analysis/phase-b/GROUPING-METHOD-REVIEW.md).

The shared capture (conftest.ROWS) puts every flow on one source IP. This fixture re-addresses it so the grouping
rule - same source IP, next alert within 30 minutes of the group's last one - gives four known groups:

    brute-a    AL-0001..0004  18.221.219.4   12:01-12:04   rule + model Brute Force (E1)
    brute-b    AL-0005..0009  13.58.98.64    12:01-12:05   rule + model Brute Force (E1), same first minute as brute-a
    botnet-1   AL-0010..0014  10.0.0.66      12:10-12:14   model-only Botnet (E3 candidate)
    botnet-2   AL-0015        10.0.0.66      12:55         same source, 41 minutes later -> a new group
AL-0016..0021 are unflagged and join no group.
"""
import csv

import pytest

from conftest import COLUMNS, FTP_RULE, ROWS
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import open_database, run_detection
from packages.detection.pipeline.source import CsvReplaySource
from test_api import T0

SOURCE = {**{f"AL-{i:04d}": "18.221.219.4" for i in range(1, 5)},
          **{f"AL-{i:04d}": "13.58.98.64" for i in range(5, 10)},
          **{f"AL-{i:04d}": "10.0.0.66" for i in range(10, 16)}}
MINUTE = {**{f"AL-{i:04d}": i - 4 for i in range(5, 10)}, "AL-0015": 55}
GROUPS = {"brute-a": [f"AL-{i:04d}" for i in range(1, 5)],
          "brute-b": [f"AL-{i:04d}" for i in range(5, 10)],
          "botnet-1": [f"AL-{i:04d}" for i in range(10, 15)],
          "botnet-2": ["AL-0015"]}


@pytest.fixture
def grouped_database(tmp_path, predictions):
    sample = tmp_path / "grouped.csv"
    with sample.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in ROWS:
            row = dict(row)
            ref = row["alert_id"]
            if ref in SOURCE:
                row["Src IP"] = SOURCE[ref]
            if ref in MINUTE:
                row["Timestamp"] = f"2018-03-01 12:{MINUTE[ref]:02d}:42.329367"
            writer.writerow(row)
    path = tmp_path / "grouped.db"
    conn = open_database(str(path))
    try:
        dataset_id = store.register_dataset(conn, name="grouped synthetic capture", version="test-groups",
                                            source_file="grouped.csv", total_records=len(ROWS),
                                            class_distribution={}, now=T0)
        store.register_model(conn, version="xgb-8class-20260911", model_file="models/xgboost_ids_model.json", now=T0)
        conn.commit()
        run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions), dataset_id=dataset_id,
                      rules=[FTP_RULE], seed=20260911, now=T0)
    finally:
        conn.close()
    return path
