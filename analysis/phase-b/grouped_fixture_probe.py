"""Run the grouped fixture through materialize+route and print what actually happened."""
import csv
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from conftest import COLUMNS, FTP_RULE, ROWS
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import open_database, run_detection
from packages.detection.pipeline.source import CsvReplaySource
from test_api import T0
from flow_group_fixture import SOURCE, MINUTE

tmp = Path(tempfile.mkdtemp())
sample = tmp / "s.csv"
with sample.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for row in ROWS:
        row = dict(row)
        if row["alert_id"] in SOURCE:
            row["Src IP"] = SOURCE[row["alert_id"]]
        if row["alert_id"] in MINUTE:
            row["Timestamp"] = f"2018-03-01 12:{MINUTE[row['alert_id']]:02d}:42.329367"
        w.writerow(row)
predictions = tmp / "p.json"
records = {entry["alert_id"]: {"id": entry["alert_id"], "predictionStatus": "available",
             "predictedClassIndex": 0 if entry["_predicted"] == "Benign" else 2,
             "predictedAttackType": entry["_predicted"], "modelConfidence": 0.99,
             "classProbabilities": {entry["_predicted"]: 0.99, "Benign": 0.01},
             "mlExplanation": {"status": "available", "method": "x", "outputSpace": "raw_margin",
                               "explainedClass": entry["_predicted"], "explainedClassIndex": 0,
                               "baseValue": 0.29, "rawModelMargin": 6.1, "topSupportingFeatures": [],
                               "topOpposingFeatures": [], "additivityCheck": {"passed": True, "difference": 1e-6, "tolerance": 1e-4}}}
           for entry in ROWS}
predictions.write_text(json.dumps(records))
db_path = tmp / "g.db"
conn = open_database(str(db_path))
try:
    dataset_id = store.register_dataset(conn, name="x", version="t", source_file="s.csv", total_records=len(ROWS), class_distribution={}, now=T0)
    store.register_model(conn, version="xgb-8class-20260911", model_file="models/xgboost_ids_model.json", now=T0)
    conn.commit()
    run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions), dataset_id=dataset_id, rules=[FTP_RULE], seed=20260911, now=T0)
finally:
    conn.close()

sys.path.insert(0, "scripts")
from materialize_flow_queue import materialize_flagged, route_flagged, UNROUTED, MEMBERS
from packages.contracts import db

conn = db.connect(db_path)
print("materialize:", materialize_flagged(conn))
print("groups:", conn.execute("SELECT id, grouping_key, first_seen_at, last_seen_at, member_count, representative_operational_alert_id FROM alert_groups ORDER BY id").fetchall())
print("members:", conn.execute("SELECT group_id, legacy_alert_id, source_ip, occurred_at FROM alert_group_members ORDER BY group_id, occurred_at").fetchall())
print("unrouted:", conn.execute(UNROUTED).fetchall())
try:
    print("route:", route_flagged(conn))
except Exception as e:
    import traceback; traceback.print_exc()
print("after route, groups:", conn.execute("SELECT id, qualifying_member_alert_id, case_ref FROM alert_groups ORDER BY id").fetchall())
print("routing rows:", conn.execute("SELECT operational_alert_id, decision_source FROM operational_system_routing ORDER BY operational_alert_id").fetchall())
print("triage:", conn.execute("SELECT operational_alert_id, handling_route, tier2_recommended FROM operational_triage_state_v2 ORDER BY operational_alert_id").fetchall())
