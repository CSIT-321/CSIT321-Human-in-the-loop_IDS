"""Regression tests for source-local timestamps and unambiguous external identities."""
import copy
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from apps.api.contract.openapi import openapi_document
from packages.contracts.canonical import CanonicalAlert
from packages.detection.adapters.current import CurrentDetectorAdapter, CurrentDetectorOutput
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput
from packages.detection.pipeline import store
from test_run import conn, dataset, sample, predictions, detect  # noqa: F401

EVENTS = json.loads((Path(__file__).parent / "fixtures/suricata-alerts.json").read_text(encoding="utf-8"))


def eve(timestamp=None, sensor="fixture", reference="eve.json:1", event=None):
    event = copy.deepcopy(EVENTS[0] if event is None else event)
    if timestamp is not None:
        event["timestamp"] = timestamp
    return SuricataEveAdapter().adapt(SuricataOutput(event, reference, sensor_id=sensor))


@pytest.mark.parametrize("stamp,offset", [
    ("2018-02-14T12:28:54.334391", None),
    ("2018-02-14 12:28:54.334391", None),
    ("2026-10-29T15:30:10.123456+08:00", "+08:00"),
    ("2026-10-29T15:30:10.123456+0800", "+08:00"),
    ("2026-10-29T15:30:10.123456-04:30", "-04:30"),
    ("2026-10-29T15:30:10Z", "+00:00"),
    ("2026-10-29T15:30:10.123456789+08:00", "+08:00"),
])
def test_canonical_timestamp_preserves_text_and_explicit_offset(stamp, offset):
    payload = eve().model_dump()
    payload["occurred_at"] = stamp
    payload.pop("occurred_at_timezone_offset")
    result = CanonicalAlert.model_validate(payload)
    wire = result.model_dump(mode="json", by_alias=True)
    assert wire["occurredAt"] == stamp
    assert wire["occurredAtTimezoneOffset"] == offset
    assert CanonicalAlert.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("stamp", [
    "", "not-a-time", "2026-02-30T12:00:00", "2026-01-01T25:00:00",
    "2026-01-01T12:00:00+08:99", "2026-01-01", "2026-01-01X12:00:00",
])
def test_invalid_canonical_timestamp_fails_clearly(stamp):
    payload = eve().model_dump()
    payload["occurred_at"] = stamp
    with pytest.raises(ValidationError, match="occurredAt"):
        CanonicalAlert.model_validate(payload)


def test_canonical_offset_cannot_claim_utc_for_source_local_time():
    payload = eve().model_dump()
    payload.update(occurred_at="2018-02-14T12:28:54.334391",
                   occurred_at_timezone_offset="+00:00")
    with pytest.raises(ValidationError, match="explicit source offset"):
        CanonicalAlert.model_validate(payload)


@pytest.mark.parametrize("stamp", [
    "2026-10-29T15:30:10.123456+08:00", "2026-10-29T15:30:10.123456+0800",
])
def test_suricata_preserves_offset_and_raw_timestamp(stamp):
    result = eve(stamp)
    assert result.occurred_at == stamp
    assert result.occurred_at_timezone_offset == "+08:00"
    assert result.original_detector_fields["timestamp"] == stamp


def test_current_timestamp_and_operational_queue_are_unchanged(conn, dataset, sample, predictions):
    detect(conn, sample, predictions, dataset)
    queue_before = [(a.alert_ref, a.created_at, a.updated_at, a.combined_score) for a in store.queue(conn)]
    for alert in store.queue(conn):
        flow = store.flow_for_alert(conn, alert.id)
        result = alert.detector
        assert result.occurred_at == flow.flow_features["Timestamp"]
        assert result.occurred_at_timezone_offset is None
        assert not result.occurred_at.endswith("Z")
        assert result.model_dump(by_alias=True)["occurredAtTimezoneOffset"] is None
        legacy = alert.model_copy(update={"detector": None})
        projected = store.detector_for_alert(conn, legacy, flow)
        assert projected.occurred_at == result.occurred_at
        assert projected.occurred_at_timezone_offset is None
        no_capture = flow.model_copy(update={"flow_features": {}})
        fallback = CurrentDetectorAdapter().adapt(CurrentDetectorOutput(
            legacy, no_capture, "model-v1", "rule-v1"))
        assert fallback.occurred_at == alert.created_at.isoformat()
        assert fallback.occurred_at_timezone_offset == "+00:00"
    assert [(a.alert_ref, a.created_at, a.updated_at, a.combined_score) for a in store.queue(conn)] == queue_before


def test_openapi_and_generated_types_expose_source_text_and_nullable_offset():
    schema = openapi_document()["components"]["schemas"]["CanonicalAlert"]["properties"]
    assert schema["occurredAt"]["type"] == "string"
    assert "format" not in schema["occurredAt"]
    assert {"type": "null"} in schema["occurredAtTimezoneOffset"]["anyOf"]
    assert any(option.get("type") == "string" for option in schema["occurredAtTimezoneOffset"]["anyOf"])
    generated = (Path(__file__).parents[1] / "apps/web/src/api/schema.d.ts").read_text(encoding="utf-8")
    assert "occurredAt: string;" in generated
    assert "occurredAtTimezoneOffset: string | null;" in generated


@pytest.mark.parametrize("sensor,reference", [
    ("fixture", "eve.json:1"), ("a", "b:c"), ("a:b", "c"),
    ("传感器:一", "路径/事件:一|二"), ('a"b\\c', 'x:y|z["item"]'),
])
def test_suricata_identity_uses_deterministic_json_components(sensor, reference):
    expected = uuid5(NAMESPACE_URL, json.dumps(
        ["suricata", sensor, reference], ensure_ascii=False, separators=(",", ":")))
    assert eve(sensor=sensor, reference=reference).canonical_alert_id == expected
    assert eve(sensor=sensor, reference=reference).canonical_alert_id == expected


def test_delimiter_pairs_do_not_collide():
    assert eve(sensor="a", reference="b:c").canonical_alert_id != eve(sensor="a:b", reference="c").canonical_alert_id


def test_different_sensors_with_same_reference_have_different_ids():
    assert eve(sensor="first").canonical_alert_id != eve(sensor="second").canonical_alert_id


@pytest.mark.parametrize("index", range(len(EVENTS)))
def test_representative_fixture_identity_is_repeatable(index):
    assert eve(event=EVENTS[index]).canonical_alert_id == eve(event=EVENTS[index]).canonical_alert_id
