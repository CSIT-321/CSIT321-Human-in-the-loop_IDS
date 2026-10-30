"""Detector evidence stays separate from operational scores and analyst feedback."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.contracts import db, models as m
from packages.contracts.canonical import CanonicalAlert
from packages.detection.adapters import DetectorAdapter
from packages.detection.adapters.current import CurrentDetectorAdapter, CurrentDetectorOutput
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput
from packages.detection.pipeline import store
from test_run import conn, dataset, sample, predictions, detect  # noqa: F401

EVENTS = json.loads((Path(__file__).parent / "fixtures/suricata-alerts.json").read_text())


def adapt(event=None, reference="fixtures/eve.json:1"):
    adapter: DetectorAdapter[SuricataOutput] = SuricataEveAdapter()
    return adapter.adapt(SuricataOutput(copy.deepcopy(EVENTS[0] if event is None else event),
                                       reference, "7.0.14", "fixture-sensor"))


@pytest.mark.parametrize("event", EVENTS)
def test_suricata_native_evidence_and_absent_confidence(event):
    result = adapt(event)
    assert result.confidence is None
    assert result.detector_severity == event["alert"]["severity"]
    assert result.detection_title == event["alert"]["signature"]
    assert result.original_detector_fields == event
    assert result.source_port == event.get("src_port")
    assert result.destination_port == event.get("dest_port")
    assert result.structured_evidence["signatureId"] == event["alert"]["signature_id"]
    assert "combinedScore" not in result.model_dump(by_alias=True)
    assert "detectionScore" not in result.model_dump(by_alias=True)
    assert CanonicalAlert.model_validate_json(result.model_dump_json()) == result


def test_unknown_fields_and_metadata_confidence_are_not_probabilities():
    result = adapt()
    assert result.original_detector_fields["future_extension"]["safe"]
    assert result.structured_evidence["ruleMetadata"]["confidence"] == ["High"]
    assert result.confidence is None


@pytest.mark.parametrize("field", ["timestamp", "event_type", "src_ip", "dest_ip", "proto", "alert"])
def test_missing_eve_fields_fail_clearly(field):
    event = copy.deepcopy(EVENTS[0])
    del event[field]
    with pytest.raises(ValidationError, match=field):
        adapt(event)


@pytest.mark.parametrize("field", ["signature", "signature_id", "category", "severity"])
def test_missing_signature_fields_fail_clearly(field):
    event = copy.deepcopy(EVENTS[0])
    del event["alert"][field]
    with pytest.raises(ValidationError, match=field):
        adapt(event)


@pytest.mark.parametrize("field,value", [
    ("event_type", "dns"), ("src_ip", "invalid"), ("src_port", -1),
    ("dest_port", 65536), ("timestamp", "2026-09-18T06:13:41"),
])
def test_invalid_events_are_rejected(field, value):
    event = copy.deepcopy(EVENTS[0])
    event[field] = value
    with pytest.raises(ValidationError):
        adapt(event)


@pytest.mark.parametrize("field", ["groundTruth", "ground_truth", "Label", "attack_class", "trueAttackType"])
def test_truth_in_unknown_nested_extensions_is_rejected(field):
    event = copy.deepcopy(EVENTS[0])
    event["vendor"] = {"nested": [{field: "Benign"}]}
    with pytest.raises(ValueError, match="ground-truth"):
        adapt(event)


def test_contract_rejects_truth_and_is_deeply_immutable():
    result = adapt()
    with pytest.raises(TypeError, match="immutable"):
        result.original_detector_fields["alert"]["severity"] = 1
    with pytest.raises(TypeError, match="immutable"):
        result.structured_evidence["ruleMetadata"]["deployment"].append("Other")
    with pytest.raises(ValidationError):
        result.confidence = 0.5
    payload = result.model_dump()
    payload["provenance"]["groundTruth"] = "Benign"
    with pytest.raises(ValidationError, match="ground-truth"):
        CanonicalAlert.model_validate(payload)


def test_reference_identity_is_repeatable_and_not_just_flow_id():
    assert adapt().canonical_alert_id == adapt().canonical_alert_id
    assert adapt(reference="fixtures/eve.json:2").canonical_alert_id != adapt().canonical_alert_id


def test_legacy_model_only_confidence_is_recoverable(conn, dataset, sample, predictions):
    detect(conn, sample, predictions, dataset)
    alert = next(a for a in store.queue(conn) if a.evidence_class == "none")
    legacy = alert.model_copy(update={"detector": None})
    flow = store.flow_for_alert(conn, alert.id)
    snapshot = CurrentDetectorAdapter().adapt(CurrentDetectorOutput(
        legacy, flow, "model-version", "rule-version", legacy_projection=True))
    assert snapshot.confidence == alert.confidence
    assert snapshot.provenance["confidenceBasis"] == "legacy-model-confidence"


def test_current_adapter_and_store_preserve_evidence(conn, dataset, sample, predictions):
    detect(conn, sample, predictions, dataset)
    for alert in store.queue(conn):
        snapshot = alert.detector
        assert snapshot is not None
        assert snapshot.canonical_alert_id == alert.alert_ref
        assert snapshot.evidence_class == alert.evidence_class
        assert snapshot.structured_evidence["detectionScore"] == alert.detection_score
        assert snapshot.structured_evidence["mlProbability"] == alert.ml_probability
        assert snapshot.structured_evidence["treeShap"] == alert.shap_attributions.model_dump(mode="json")
        assert snapshot.confidence in (0.97, 0.99)
        assert snapshot.confidence != alert.combined_score
        assert snapshot.provenance["modelVersion"] == "xgb-8class-20260911"
        wire = snapshot.model_dump_json(by_alias=True)
        conn.execute("UPDATE alerts SET combined_score = ? WHERE id = ?", (45, alert.id))
        assert db.get(conn, m.Alert, alert.id).detector.model_dump_json(by_alias=True) == wire
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE alerts SET detector = NULL WHERE id = ?", (alert.id,))


def test_legacy_projection_uses_original_severity_and_own_run(conn, dataset, sample, predictions):
    detect(conn, sample, predictions, dataset)
    alert = store.queue(conn)[0]
    flow = store.flow_for_alert(conn, alert.id)
    legacy = alert.model_copy(update={"detector": None, "severity": "Informational", "combined_score": 0})
    snapshot = store.detector_for_alert(conn, legacy, flow)
    assert snapshot.detector_severity == alert.detector.detector_severity
    assert snapshot.provenance["legacyProjection"]
    assert snapshot.confidence is None  # legacy fused confidence is not a recoverable ML confidence
    assert snapshot.structured_evidence["detectionScore"] == alert.detection_score
