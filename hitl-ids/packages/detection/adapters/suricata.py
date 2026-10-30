"""Fixture-only EVE alert adapter. No capture or response actions."""
from dataclasses import dataclass
import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress
from packages.contracts.canonical import CanonicalAlert, reject_ground_truth


class EveSignature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    signature: str = Field(min_length=1)
    signature_id: int = Field(strict=True, ge=0)
    category: str = Field(min_length=1)
    severity: int = Field(strict=True, ge=0)
    action: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EveAlert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event_type: Literal["alert"]
    timestamp: AwareDatetime
    src_ip: IPvAnyAddress
    dest_ip: IPvAnyAddress
    src_port: int | None = Field(default=None, strict=True, ge=0, le=65535)
    dest_port: int | None = Field(default=None, strict=True, ge=0, le=65535)
    proto: str = Field(min_length=1)
    flow_id: int | None = Field(default=None, strict=True, ge=0)
    alert: EveSignature


@dataclass(frozen=True)
class SuricataOutput:
    event: dict[str, Any]
    raw_event_reference: str
    detector_version: str | None = None
    sensor_id: str = "fixture"


class SuricataEveAdapter:
    def adapt(self, output: SuricataOutput) -> CanonicalAlert:
        if not output.raw_event_reference.strip() or not output.sensor_id.strip():
            raise ValueError("raw event reference and sensor id must be nonempty")
        reject_ground_truth(output.event)
        event = EveAlert.model_validate(output.event)
        signature = event.alert
        # A reference identifies a record (file+line), not a flow containing many alerts.
        identity = json.dumps(
            ["suricata", output.sensor_id, output.raw_event_reference],
            ensure_ascii=False, separators=(",", ":"))
        return CanonicalAlert(
            canonical_alert_id=uuid5(NAMESPACE_URL, identity),
            occurred_at=output.event["timestamp"], detector_source="suricata", detector_name="Suricata",
            detector_version=output.detector_version, detection_title=signature.signature,
            detection_category=signature.category, detector_severity=signature.severity,
            confidence=None, source_ip=str(event.src_ip), destination_ip=str(event.dest_ip),
            source_port=event.src_port, destination_port=event.dest_port, protocol=event.proto,
            evidence_class="external_signature",
            structured_evidence={
                "signatureId": signature.signature_id, "flowId": event.flow_id,
                "action": signature.action, "ruleMetadata": signature.metadata,
            },
            provenance={"adapterVersion": "suricata-eve-v1", "sensorId": output.sensor_id,
                        "severityScale": "suricata-rule-priority", "timestampBasis": "event-offset"},
            source_record_reference=output.raw_event_reference,
            original_detector_fields=output.event,
        )
