"""Admission policy is distinct from detector confidence and current fusion."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.detection.adapters.admission_policy import AdmissionPolicy, load_admission_policy
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput


def canonical(severity=2):
    event = json.loads((Path(__file__).parent / "fixtures/suricata-alerts.json").read_text())[0]
    event["alert"]["severity"] = severity
    return SuricataEveAdapter().adapt(SuricataOutput(event, "fixture:1", sensor_id="sensor-a"))


@pytest.mark.parametrize("severity,priority", [(1, 85), (2, 65), (3, 40), (4, 20)])
def test_policy_keeps_native_severity_and_confidence_separate(severity, priority):
    alert = canonical(severity)
    before = alert.model_dump_json()
    decision = load_admission_policy().decide(alert)
    assert decision.native_severity == severity
    assert decision.initial_operational_priority == priority
    assert decision.requires_review
    assert decision.evidence_class == "external_rule"
    assert not decision.learning_eligible
    assert decision.learning_reason
    assert not decision.evaluation_included
    assert decision.policy_snapshot["version"] == decision.policy_version
    assert alert.confidence is None
    assert alert.model_dump_json() == before


def test_mapping_is_configurable():
    data = load_admission_policy().model_dump()
    data["version"] = "local-review-policy-v2"
    data["severity_to_priority"]["2"] = 55
    policy = AdmissionPolicy.model_validate(data)
    assert policy.decide(canonical()).initial_operational_priority == 55
    assert policy.decide(canonical()).policy_version == "local-review-policy-v2"


@pytest.mark.parametrize("severity", [0, 5, 99])
def test_unmapped_native_severity_fails_clearly(severity):
    with pytest.raises(ValueError, match="no admission mapping"):
        load_admission_policy().decide(canonical(severity))


@pytest.mark.parametrize("change", [
    {"detector_source": "current_flow"}, {"confidence": 0.8}, {"evidence_class": "none"},
])
def test_unaccepted_detector_or_evidence_is_rejected(change):
    with pytest.raises(ValueError):
        load_admission_policy().decide(canonical().model_copy(update=change))


@pytest.mark.parametrize("change", [
    {"requires_review": False}, {"learning_eligible": True}, {"evaluation_included": True},
    {"severity_to_priority": {"2": float("nan")}},
    {"severity_to_priority": {"2": float("inf")}},
    {"severity_to_priority": {"2": 101}},
    {"severity_to_priority": {"02": 65}},
    {"accepted_sources": ["current_flow"]},
])
def test_unsafe_policy_is_rejected(change):
    data = load_admission_policy().model_dump()
    data.update(change)
    with pytest.raises(ValidationError):
        AdmissionPolicy.model_validate(data)
