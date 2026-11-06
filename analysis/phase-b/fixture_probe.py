"""Reproduce the fixture exactly and inspect the trigger before the failing UPDATE."""
import csv
import os
import shutil
import sqlite3
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path("tests")))
from conftest import COLUMNS, FTP_RULE, ROWS  # noqa: E402
from packages.detection.pipeline import store  # noqa: E402
from packages.detection.pipeline.predictor import ReplayPredictor  # noqa: E402
from packages.detection.pipeline.runner import open_database, run_detection  # noqa: E402
from packages.detection.pipeline.source import CsvReplaySource  # noqa: E402
from test_api import T0  # noqa: E402

tmp = Path(tempfile.mkdtemp())
sample = tmp / "s.csv"
with sample.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    w.writerows(ROWS)
predictions = tmp / "p.json"
import json  # noqa: E402
records = {}
for entry in ROWS:
    predicted = str(entry["_predicted"])
    records[entry["alert_id"]] = {"id": entry["alert_id"], "predictionStatus": "available",
                                  "predictedClassIndex": 0 if predicted == "Benign" else 2,
                                  "predictedAttackType": predicted, "modelConfidence": 0.99,
                                  "classProbabilities": {predicted: 0.99, "Benign": 0.01},
                                  "mlExplanation": {"status": "available", "method": "xgboost_native_treeshap_pred_contribs",
                                                    "outputSpace": "raw_margin", "explainedClass": predicted,
                                                    "explainedClassIndex": 0 if predicted == "Benign" else 2,
                                                    "baseValue": 0.29, "rawModelMargin": 6.1,
                                                    "topSupportingFeatures": [{"featureName": "Dst Port",
                                                                               "featureValue": 80.0,
                                                                               "shapContribution": 1.2,
                                                                               "direction": "supports_prediction"}],
                                                    "topOpposingFeatures": [], "additivityCheck": {"passed": True,
                                                                                                     "difference": 1e-6,
                                                                                                     "tolerance": 1e-4}}}
predictions.write_text(json.dumps(records))
db_path = tmp / "g.db"
conn = open_database(str(db_path))
try:
    dataset_id = store.register_dataset(conn, name="x", version="t", source_file="s.csv", total_records=len(ROWS),
                                        class_distribution={}, now=T0)
    store.register_model(conn, version="xgb-8class-20260911", model_file="models/xgboost_ids_model.json", now=T0)
    conn.commit()
    run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions), dataset_id=dataset_id,
                  rules=[FTP_RULE], seed=20260911, now=T0)
finally:
    conn.close()
conn = sqlite3.connect(db_path)
print("user_version after detection:", conn.execute("PRAGMA user_version").fetchone()[0])
print("trigger:", conn.execute("SELECT sql FROM sqlite_master WHERE name='trg_groups_no_update'").fetchone()[0].replace("\n", " ")[:400])
conn.execute("INSERT INTO alert_groups (group_ref, grouping_key, first_seen_at, last_seen_at, member_count, representative_operational_alert_id, qualifying_member_alert_id, case_ref, created_at) VALUES ('g1','1.1.1.1','t','t',1,NULL,NULL,NULL,'t')")
try:
    conn.execute("UPDATE alert_groups SET representative_operational_alert_id=7 WHERE group_ref='g1'")
    print("rep update: OK")
except Exception as e:
    print("rep update FAILED:", e)
