"""Detector-neutral evidence envelope; operational state belongs to the HITL platform."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel


def reject_ground_truth(value: Any) -> None:
    """Reject label metadata recursively, including unknown vendor extension objects."""
    forbidden = {
        "groundtruth", "groundtruthlabel", "label", "rawlabel", "trueattacktype",
        "attackclass", "attacktype", "attemptedcategory", "isattempted", "mappedattacktype",
        "truelabel", "groundtruthclass",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            folded = "".join(c for c in key.casefold() if c.isalnum())
            if folded in forbidden:
                raise ValueError(f"ground-truth field is forbidden: {key}")
            reject_ground_truth(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_ground_truth(item)


class _FrozenDict(dict):
    def _refuse(self, *args, **kwargs):
        raise TypeError("detector evidence is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _refuse

    def __deepcopy__(self, memo):
        return self


class _FrozenList(list):
    def _refuse(self, *args, **kwargs):
        raise TypeError("detector evidence is immutable")

    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = sort = reverse = _refuse
    __iadd__ = __imul__ = _refuse

    def __deepcopy__(self, memo):
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


class CanonicalAlert(BaseModel):
    """Immutable detector facts, never a ranking score or an analyst verdict.

    A naive occurredAt preserves a capture-local timestamp; provenance states its basis.
    Severity keeps the detector's native scale. No cross-detector severity conversion is implied.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False,
        alias_generator=to_camel, populate_by_name=True,
    )

    canonical_alert_id: UUID
    occurred_at: datetime
    detector_source: str = Field(min_length=1)
    detector_name: str = Field(min_length=1)
    detector_version: str | None = None
    detection_title: str = Field(min_length=1)
    detection_category: str | None = None
    detector_severity: str | int
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    source_ip: str = Field(min_length=1)
    destination_ip: str = Field(min_length=1)
    source_port: Annotated[int, Field(strict=True, ge=0, le=65535)] | None = None
    destination_port: Annotated[int, Field(strict=True, ge=0, le=65535)] | None = None
    protocol: str = Field(min_length=1)
    evidence_class: str = Field(min_length=1)
    structured_evidence: dict[str, JsonValue]
    provenance: dict[str, JsonValue]
    source_record_reference: str = Field(min_length=1)
    original_detector_fields: dict[str, JsonValue]

    @field_validator("structured_evidence", "provenance", "original_detector_fields")
    @classmethod
    def _immutable_safe_json(cls, value):
        reject_ground_truth(value)
        return _freeze(value)
