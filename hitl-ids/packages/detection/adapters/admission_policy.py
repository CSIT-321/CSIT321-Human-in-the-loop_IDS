"""Offline admission decisions. Native severity maps to priority, never confidence."""
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from packages.contracts.canonical import CanonicalAlert
from packages.contracts.models import Contract, Score


DEFAULT_POLICY = Path(__file__).resolve().parents[3] / "config" / "external-admission.json"


class AdmissionPolicy(Contract):
    version: str = Field(min_length=1, max_length=100)
    accepted_sources: tuple[Literal["suricata"], ...] = Field(min_length=1)
    severity_to_priority: dict[str, Score] = Field(min_length=1)
    requires_review: Literal[True]
    evidence_class: Literal["external_rule"]
    duplicate_handling: Literal["canonical_identity"]
    learning_eligible: Literal[False]
    learning_reason: str = Field(min_length=1)
    evaluation_included: Literal[False]

    @field_validator("severity_to_priority")
    @classmethod
    def valid_native_severities(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not key.isascii() or not key.isdigit() or str(int(key)) != key for key in value):
            raise ValueError("severity keys must be canonical nonnegative integer strings")
        return value

    def decide(self, alert: CanonicalAlert) -> "AdmissionDecision":
        if alert.detector_source not in self.accepted_sources:
            raise ValueError(f"detector source {alert.detector_source!r} is not accepted")
        if alert.confidence is not None:
            raise ValueError("Suricata admission requires null confidence")
        if alert.evidence_class != "external_signature":
            raise ValueError("Suricata admission requires external signature evidence")
        native = alert.detector_severity
        if type(native) is not int or str(native) not in self.severity_to_priority:
            raise ValueError(f"native severity {native!r} has no admission mapping")
        return AdmissionDecision(
            policy_version=self.version, detector_source=alert.detector_source,
            native_severity=native, initial_operational_priority=self.severity_to_priority[str(native)],
            requires_review=self.requires_review, evidence_class=self.evidence_class,
            learning_eligible=self.learning_eligible, learning_reason=self.learning_reason,
            evaluation_included=self.evaluation_included, policy_snapshot=self.model_dump(mode="json"))


class AdmissionDecision(Contract):
    policy_version: str
    detector_source: str
    native_severity: int
    initial_operational_priority: Score
    requires_review: Literal[True]
    evidence_class: Literal["external_rule"]
    learning_eligible: Literal[False]
    learning_reason: str
    evaluation_included: Literal[False]
    policy_snapshot: dict


def load_admission_policy(path: Path = DEFAULT_POLICY) -> AdmissionPolicy:
    return AdmissionPolicy.model_validate_json(path.read_text(encoding="utf-8"))
