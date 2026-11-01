"""Conservative offline EVE correlation. No campaign, host, time, or ML inference."""
from datetime import datetime
import hashlib
import json
from typing import get_args
from uuid import NAMESPACE_URL, uuid5
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress
from packages.contracts.canonical import CanonicalAlert, reject_ground_truth
from packages.contracts.suricata_bundle import EveType, SuricataRecord, RelatedSignature, SuricataEvidenceBundle
from .suricata import EveAlert

SUPPORTED = frozenset(get_args(EveType))


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


class EveRecord(BaseModel):
    model_config = ConfigDict(extra='ignore')
    event_type: EveType
    timestamp: AwareDatetime
    flow_id: int | None = Field(default=None, strict=True, ge=0)
    tx_id: int | None = Field(default=None, strict=True, ge=0)
    src_ip: IPvAnyAddress | None = None
    dest_ip: IPvAnyAddress | None = None
    src_port: int | None = Field(default=None, strict=True, ge=0, le=65535)
    dest_port: int | None = Field(default=None, strict=True, ge=0, le=65535)


def parse_record(raw: dict, sensor_id: str) -> SuricataRecord:
    if not sensor_id.strip():
        raise ValueError('sensor identity is required')
    reject_ground_truth(raw)
    event = EveRecord.model_validate(raw)
    if event.event_type == 'alert':
        EveAlert.model_validate(raw)
    elif not isinstance(raw.get(event.event_type), dict):
        raise ValueError('EVE record requires its event-specific object')
    ref = 'eve-sha256:' + hashlib.sha256(canonical_json(raw).encode()).hexdigest()
    return SuricataRecord(source_record_ref=ref, sensor_id=sensor_id, event_type=event.event_type,
        timestamp=raw['timestamp'], flow_id=str(event.flow_id) if event.flow_id is not None else None,
        tx_id=str(event.tx_id) if event.tx_id is not None else None, raw=raw)


def correlation_key(record: SuricataRecord):
    return (record.sensor_id, 'flow', record.flow_id) if record.flow_id is not None else (
        record.sensor_id, 'record', record.source_record_ref)


def build_bundle(records, *, detector_version=None) -> CanonicalAlert:
    # Reparse raw input: derived ids, fields and nested data must never be caller-authoritative.
    records = [parse_record(record.raw, record.sensor_id) for record in records]
    records = list({record.source_record_ref: record for record in records}.values())
    if not records or len({correlation_key(record) for record in records}) != 1:
        raise ValueError('bundle must have exactly one safe correlation identity')
    records.sort(key=lambda r: (datetime.fromisoformat(r.timestamp.replace('Z', '+00:00')), r.source_record_ref))
    alerts = [r for r in records if r.event_type == 'alert']
    if not alerts:
        raise ValueError('evidence without an alert is not a detection')
    root = min(alerts, key=lambda r: (r.raw['alert']['severity'],
        datetime.fromisoformat(r.timestamp.replace('Z', '+00:00')), r.source_record_ref))
    event = EveAlert.model_validate(root.raw)
    signatures = tuple(RelatedSignature(source_record_ref=r.source_record_ref, timestamp=r.timestamp,
        signature_id=r.raw['alert']['signature_id'], signature=r.raw['alert']['signature'],
        native_category=r.raw['alert']['category'], native_severity=r.raw['alert']['severity'],
        action=r.raw['alert'].get('action'), metadata=r.raw['alert'].get('metadata', {})) for r in alerts)
    transactions = {}
    if root.flow_id is not None:
        for record in records:
            if record.tx_id is not None:
                transactions.setdefault(record.tx_id, []).append(record.source_record_ref)
    bundle = SuricataEvidenceBundle(sensor_id=root.sensor_id, flow_id=root.flow_id,
        correlation_basis='sensor_flow_id' if root.flow_id is not None else 'independent_record',
        primary_record_ref=root.source_record_ref, native_severity=event.alert.severity,
        related_signatures=signatures, records=tuple(records), transaction_records=transactions,
        evidence_types=tuple(sorted({r.event_type for r in records})))
    raw = {'events': [r.raw for r in records]}
    reference = 'eve-bundle-sha256:' + hashlib.sha256(canonical_json(raw).encode()).hexdigest()
    return CanonicalAlert(canonical_alert_id=uuid5(NAMESPACE_URL,
        canonical_json(['suricata-bundle-v1', *correlation_key(root)])),
        occurred_at=root.timestamp, detector_source='suricata', detector_name='Suricata',
        detector_version=detector_version, detection_title=event.alert.signature,
        detection_category=event.alert.category, detector_severity=event.alert.severity, confidence=None,
        source_ip=str(event.src_ip), destination_ip=str(event.dest_ip), source_port=event.src_port,
        destination_port=event.dest_port, protocol=event.proto, evidence_class='external_signature',
        structured_evidence={'suricataBundle': bundle.model_dump(mode='json', by_alias=True)},
        provenance={'adapterVersion': 'suricata-bundle-v1', 'sensorId': root.sensor_id,
            'severityScale': 'suricata-rule-priority', 'timestampBasis': 'event-offset'},
        source_record_reference=reference, original_detector_fields=raw)


def bundle_for(canonical) -> SuricataEvidenceBundle | None:
    value = canonical.structured_evidence.get('suricataBundle')
    return SuricataEvidenceBundle.model_validate(value) if value is not None else None
