"""Detector-neutral evidence envelope; operational state belongs to the HITL platform."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from pydantic.alias_generators import to_camel


TIMESTAMP_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)?$"
)


def timestamp_offset(value: str) -> str | None:
    """Validate source text without changing it; normalize only explicit offset metadata."""
    if not re.fullmatch(TIMESTAMP_PATTERN, value):
        raise ValueError("occurredAt must be a valid ISO source timestamp")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("occurredAt must be a valid ISO source timestamp") from exc
    if value.endswith("Z"):
        return "+00:00"
    offset = re.search(r"([+-]\d{2}):?(\d{2})$", value)
    return None if offset is None else f"{offset[1]}:{offset[2]}"


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

    occurredAt preserves validated source text; a null offset means the timezone is unknown.
    Severity keeps the detector's native scale. No cross-detector severity conversion is implied.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False,
        alias_generator=to_camel, populate_by_name=True,
    )

    canonical_alert_id: UUID
    occurred_at: str = Field(
        strict=True, pattern=TIMESTAMP_PATTERN,
        description="Validated source timestamp preserved verbatim. May be source-local; "
                    "not an RFC 3339 date-time promise.")
    occurred_at_timezone_offset: str | None = Field(
        default=None, pattern=r"^[+-](?:[01]\d|2[0-3]):[0-5]\d$",
        description="Explicit source offset as +/-HH:MM; null when unknown. Never inferred.")
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

    @model_validator(mode="before")
    @classmethod
    def _offset_for_existing_snapshots(cls, value):
        if isinstance(value, dict):
            stamp = value.get("occurredAt", value.get("occurred_at"))
            if isinstance(stamp, str):
                offset = timestamp_offset(stamp)
                if not {"occurredAtTimezoneOffset", "occurred_at_timezone_offset"} & value.keys():
                    value = {**value, "occurred_at_timezone_offset": offset}
        return value

    @model_validator(mode="after")
    def _offset_matches_source(self):
        if self.occurred_at_timezone_offset != timestamp_offset(self.occurred_at):
            raise ValueError("occurredAtTimezoneOffset must match the explicit source offset")
        return self

    @field_validator("structured_evidence", "provenance", "original_detector_fields")
    @classmethod
    def _immutable_safe_json(cls, value):
        reject_ground_truth(value)
        return _freeze(value)
