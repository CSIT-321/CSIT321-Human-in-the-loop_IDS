"""S9 - the batch detection run: one command, one populated database, reproducibly.

The pipeline's parts are already tested (S5 matching, S6 fusion, S7 feedback). These tests pin what
S9 adds: the ingest seam's ordering and leakage rules, that every flow becomes an alert with a family
and a queue band, that the run row carries what a replay needs, that the whole run is one
transaction, and that the same source twice gives the same scores (NFR-05 at run level).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import DEFAULT_BATCH, open_database, run_detection
from packages.detection.pipeline.source import (
    NON_FEATURE_COLUMNS,
    CsvReplaySource,
    Flow,
    flow_record,
    parse_timestamps,
)
from packages.detection.signature.observable import project_record

T0 = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
HITL = Path(__file__).resolve().parents[1]
DEMO_SAMPLE = HITL / "data" / "processed" / "demo_sample.csv"
DEMO_PREDICTIONS = HITL / "data" / "processed" / "demo_ml_predictions_shap.json"

# One rule, so these tests own the signature side: FTP brute force on TCP/21.
FTP_RULE = m.SignatureRule(
    rule_id="SIG-FTP-BRUTE-FORCE", name="FTP Brute Force Flow Pattern", severity="Medium",
    conditions={"protocol": "TCP", "destinationPort": 21, "totalFwdPackets": {"min": 1}},
    version="test-1", attack_category="Brute Force",
    rationale="Repeated short TCP flows against port 21.")

COLUMNS = ["alert_id", "attack_class", "is_attempted", "Flow ID", "Src IP", "Src Port", "Dst IP",
           "Dst Port", "Protocol", "Timestamp", "Flow Duration", "Total Fwd Packet",
           "Total Bwd packets", "Total Length of Fwd Packet", "Total Length of Bwd Packet",
           "Flow Bytes/s", "Flow Packets/s", "Packet Length Mean", "Fwd Packet Length Mean",
           "SYN Flag Count", "ACK Flag Count", "FIN Flag Count", "RST Flag Count", "Label",
           "Attempted Category"]


def row(alert_id: str, *, when: str, dst_port: int, protocol: int = 6, attack: str = "Benign",
        packets: int = 4, bytes_per_second: str = "1000.5") -> dict[str, object]:
    return {
        "alert_id": alert_id, "attack_class": attack, "is_attempted": 0,
        "Flow ID": f"flow-{alert_id}", "Src IP": "172.31.69.25", "Src Port": 51514,
        "Dst IP": "18.221.219.4", "Dst Port": dst_port, "Protocol": protocol, "Timestamp": when,
        "Flow Duration": 420000, "Total Fwd Packet": packets, "Total Bwd packets": 2,
        "Total Length of Fwd Packet": 3000, "Total Length of Bwd Packet": 190,
        "Flow Bytes/s": bytes_per_second, "Flow Packets/s": 54.2, "Packet Length Mean": 120.5,
        "Fwd Packet Length Mean": 118.0, "SYN Flag Count": 1, "ACK Flag Count": 1,
        "FIN Flag Count": 0, "RST Flag Count": 0, "Label": attack, "Attempted Category": "-",
    }


ROWS = [
    # deliberately out of timestamp order, and 1 March must not be read as 3 January
    row("AL-0003", when="2018-03-01 12:15:42.329367", dst_port=21, attack="Brute Force"),
    row("AL-0001", when="2018-02-14 16:21:49.364081", dst_port=443),
    row("AL-0002", when="2018-02-14 16:22:01.000000", dst_port=53, protocol=17,
        bytes_per_second="Infinity"),
    row("AL-0004", when="2018-03-01 12:15:43.000000", dst_port=21, attack="Brute Force"),
]


@pytest.fixture
def sample(tmp_path) -> Path:
    path = tmp_path / "sample.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ROWS)
    return path


@pytest.fixture
def predictions(tmp_path) -> Path:
    """Predictions in the shape ml/inference.py emits, one per flow."""
    path = tmp_path / "predictions.json"
    records = {}
    for entry in ROWS:
        malicious = entry["attack_class"] != "Benign"
        predicted = "Brute Force" if malicious else "Benign"
        confidence = 0.97 if malicious else 0.99
        records[entry["alert_id"]] = {
            "id": entry["alert_id"], "predictionStatus": "available",
            "predictedClassIndex": 2 if malicious else 0, "predictedAttackType": predicted,
            "modelConfidence": confidence,
            "classProbabilities": {predicted: confidence,
                                   "Benign" if malicious else "DoS": round(1 - confidence, 4)},
            "mlExplanation": {
                "status": "available", "method": "xgboost_native_treeshap_pred_contribs",
                "outputSpace": "raw_margin", "explainedClass": predicted,
                "explainedClassIndex": 2 if malicious else 0, "baseValue": 0.29,
                "rawModelMargin": 6.1,
                "topSupportingFeatures": [{"featureName": "Dst Port", "featureValue": 21.0,
                                           "shapContribution": 1.2,
                                           "direction": "supports_prediction"}],
                "topOpposingFeatures": [],
                "additivityCheck": {"passed": True, "difference": 1e-6, "tolerance": 1e-4},
            },
        }
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


@pytest.fixture
def conn(tmp_path):
    connection = open_database(str(tmp_path / "demo.db"))
    yield connection
    connection.close()


def registered(conn, *, name: str = "test sample", version: str = "test-1") -> int:
    dataset_id = store.register_dataset(
        conn, name=name, version=version, source_file="sample.csv", total_records=len(ROWS),
        class_distribution={"Benign": 2, "Brute Force": 2}, now=T0)
    store.register_model(conn, version="xgb-8class-20260911",
                         model_file="models/xgboost_ids_model.json", now=T0)
    conn.commit()
    return dataset_id


@pytest.fixture
def dataset(conn) -> int:
    return registered(conn)


def detect(conn, sample, predictions, dataset, **kwargs):
    return run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions),
                         dataset_id=dataset, rules=[FTP_RULE], seed=20260911, now=T0, **kwargs)


# --------------------------------------------------------------------------------------------
# The ingest seam (S3, built with S9)
# --------------------------------------------------------------------------------------------


def test_flows_arrive_in_timestamp_order_never_day_first(sample):
    ids = [flow.source_record_id for flow in CsvReplaySource(sample).flows()]
    assert ids == ["AL-0001", "AL-0002", "AL-0003", "AL-0004"]  # 1 March sorts after 14 February
    assert [stamp.month for stamp in parse_timestamps(
        pd.Series(["2018-03-01 12:15:42.329367"]))] == [3]


def test_a_flow_never_carries_ground_truth(sample):
    for flow in CsvReplaySource(sample).flows():
        assert not set(flow.features) & NON_FEATURE_COLUMNS
        assert "Label" not in flow.features and "attack_class" not in flow.features


def test_the_limit_takes_the_first_flows_in_order(sample):
    assert [flow.source_record_id for flow in CsvReplaySource(sample, limit=2).flows()] == [
        "AL-0001", "AL-0002"]


def test_a_missing_column_is_refused(tmp_path):
    path = tmp_path / "thin.csv"
    path.write_text("alert_id,Timestamp\nAL-1,2018-03-01 12:15:42.329367\n", encoding="utf-8")
    with pytest.raises(KeyError, match="columns detection needs"):
        list(CsvReplaySource(path).flows())


def test_a_non_finite_feature_is_stored_as_null_and_read_as_zero(sample):
    flows = {flow.source_record_id: flow for flow in CsvReplaySource(sample).flows()}
    udp = flows["AL-0002"]
    assert udp.features["Flow Bytes/s"] == float("inf")  # the model sees what it was trained on
    stored = flow_record(udp)
    assert stored.flow_features["Flow Bytes/s"] is None  # the contract refuses non-finite floats
    assert project_record(udp.features)["flowBytesPerSecond"] == 0  # the tuned-on view, unchanged
    assert (stored.protocol, stored.dst_port, stored.packets, stored.bytes) == ("UDP", 53, 6, 3190)
    assert stored.duration == pytest.approx(0.42)


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------


def test_every_flow_becomes_an_alert_with_a_family_and_a_band(conn, sample, predictions, dataset):
    summary = detect(conn, sample, predictions, dataset)
    assert (summary.flows, summary.alerts) == (4, 4)
    assert summary.by_evidence == {"corroborated": 2, "none": 2}
    assert summary.predictions_unavailable == 0
    alerts = store.queue(conn, run_id=summary.run_id)
    assert len(alerts) == 4
    assert all(alert.family_key is not None for alert in alerts)
    assert set(summary.by_queue_class) <= set(m.QUEUE_PRIORITY)
    # the two corroborated Brute Force flows share one family; the benign flows have their own
    assert len({alert.family_key for alert in alerts}) == 3
    assert conn.execute("SELECT COUNT(*) FROM flow_data").fetchone()[0] == 4


def test_the_queue_is_served_in_band_then_score_order(conn, sample, predictions, dataset):
    summary = detect(conn, sample, predictions, dataset)
    alerts = store.queue(conn, run_id=summary.run_id)
    keys = [(alert.queue_priority, -alert.combined_score, alert.id) for alert in alerts]
    assert keys == sorted(keys)
    assert alerts[0].evidence_class == "corroborated"  # an agreed detection outranks the rest


def test_the_run_row_carries_what_a_replay_needs(conn, sample, predictions, dataset):
    summary = detect(conn, sample, predictions, dataset)
    run = db.get(conn, m.DetectionRun, summary.run_id)
    assert (run.status, run.alert_count, run.seed) == ("completed", 4, 20260911)
    assert run.dataset_id == dataset and run.model_version == "xgb-8class-20260911"
    assert run.rule_set_version == "test-1"
    assert run.fusion_weights["scheme"].startswith("cef-")
    assert run.guardrail_config["critical_alert_floor"] == 70
    assert run.completed_at is not None
    entries = AuditWriter(conn).query(event_types=["DETECTION_RUN"])
    assert len(entries) == 1
    assert (entries[0].details["run_id"], entries[0].details["alert_count"]) == (summary.run_id, 4)


def test_a_failed_run_stores_nothing(conn, sample, predictions, dataset):
    class Failing(ReplayPredictor):
        def predict(self, flows):
            raise RuntimeError("model unavailable")

    with pytest.raises(RuntimeError, match="model unavailable"):
        run_detection(conn, CsvReplaySource(sample), Failing(predictions), dataset_id=dataset,
                      rules=[FTP_RULE], now=T0)
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM detection_runs").fetchone()[0] == 0


def test_the_same_source_twice_gives_the_same_scores(tmp_path, sample, predictions):
    runs = []
    for name in ("first.db", "second.db"):
        conn = open_database(str(tmp_path / name))
        try:
            summary = detect(conn, sample, predictions, registered(conn))
            assert summary.alerts == 4
            runs.append([(alert.combined_score, alert.queue_class, alert.family_key,
                          alert.explanation)
                         for alert in store.queue(conn, run_id=summary.run_id)])
        finally:
            conn.close()
    assert runs[0] == runs[1]


def test_batching_does_not_change_the_result(tmp_path, sample, predictions):
    summaries = []
    for name, size in (("one.db", 1), ("many.db", DEFAULT_BATCH)):
        conn = open_database(str(tmp_path / name))
        try:
            summaries.append(detect(conn, sample, predictions, registered(conn), batch=size))
        finally:
            conn.close()
    assert summaries[0].by_evidence == summaries[1].by_evidence
    assert summaries[0].by_queue_class == summaries[1].by_queue_class


def test_registration_is_idempotent(conn):
    first = registered(conn)
    assert registered(conn) == first
    assert conn.execute("SELECT COUNT(*) FROM ml_models").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 1


def test_a_run_needs_an_enabled_rule(conn, sample, predictions, dataset):
    disabled = FTP_RULE.model_copy(update={"enabled": False})
    with pytest.raises(ValueError, match="enabled signature rule"):
        run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions),
                      dataset_id=dataset, rules=[disabled], now=T0)


def test_a_replay_predictor_refuses_a_flow_it_has_no_prediction_for(predictions):
    with pytest.raises(LookupError, match="AL-9999"):
        ReplayPredictor(predictions).predict([Flow(source_record_id="AL-9999", features={})])


def test_opening_a_missing_database_can_be_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_database(str(tmp_path / "absent.db"), create=False)


# --------------------------------------------------------------------------------------------
# The real demo sample, when its inputs are present
# --------------------------------------------------------------------------------------------


@pytest.mark.skipif(not (DEMO_SAMPLE.exists() and DEMO_PREDICTIONS.exists()),
                    reason="demo sample or its predictions are absent (see data/README.md)")
def test_the_demo_sample_runs_end_to_end(tmp_path):
    conn = open_database(str(tmp_path / "demo.db"))
    try:
        dataset_id = store.register_dataset(
            conn, name="demo", version="demo-20260911", source_file="demo_sample.csv",
            total_records=200, class_distribution={}, now=T0)
        store.register_model(conn, version="xgb-8class-20260911",
                             model_file="models/xgboost_ids_model.json", now=T0)
        conn.commit()
        summary = run_detection(conn, CsvReplaySource(DEMO_SAMPLE, limit=200),
                                ReplayPredictor(DEMO_PREDICTIONS), dataset_id=dataset_id,
                                seed=20260911, now=T0)
        assert summary.flows == summary.alerts == 200
        assert summary.predictions_unavailable == 0
        assert sum(summary.by_evidence.values()) == 200
        assert set(summary.by_evidence) <= {"corroborated", "signature_override", "ml_only", "none"}
        queue = store.queue(conn, run_id=summary.run_id, limit=10)
        assert [alert.queue_priority for alert in queue] == sorted(
            alert.queue_priority for alert in queue)
        assert all(alert.shap_attributions is not None for alert in queue
                   if alert.evidence_class != "none")
    finally:
        conn.close()
