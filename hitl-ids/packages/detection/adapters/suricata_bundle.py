"""Conservative offline EVE correlation. No campaign, host, time, or ML inference."""
from datetime import datetime
from ipaddress import ip_address
import hashlib
import json
from typing import get_args
from uuid import NAMESPACE_URL, uuid5
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, TypeAdapter
from packages.contracts.canonical import CanonicalAlert, reject_ground_truth
from packages.contracts.suricata_bundle import EveType, SuricataRecord, RelatedSignature, SuricataEvidenceBundle
from .suricata import EveAlert

SUPPORTED = frozenset(get_args(EveType))
FLOW_START = TypeAdapter(AwareDatetime)


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
    proto: str | None = Field(default=None, min_length=1)


def parse_record(raw: dict, sensor_id: str, capture_scope: str | None = None) -> SuricataRecord:
    if not sensor_id.strip():
        raise ValueError('sensor identity is required')
    if capture_scope is not None and (not capture_scope.strip() or capture_scope != capture_scope.strip()):
        raise ValueError('capture scope must be nonblank without surrounding whitespace')
    reject_ground_truth(raw)
    event = EveRecord.model_validate(raw)
    if event.event_type == 'alert':
        EveAlert.model_validate(raw)
    elif not isinstance(raw.get(event.event_type), dict):
        raise ValueError('EVE record requires its event-specific object')
    ref = 'eve-sha256:' + hashlib.sha256(canonical_json(raw).encode()).hexdigest()
    return SuricataRecord(source_record_ref=ref, sensor_id=sensor_id, capture_scope=capture_scope, event_type=event.event_type,
        timestamp=raw['timestamp'], flow_id=str(event.flow_id) if event.flow_id is not None else None,
        tx_id=str(event.tx_id) if event.tx_id is not None else None, raw=raw)


def correlation_key(record: SuricataRecord):
    scope = (record.sensor_id,) if record.capture_scope is None else (record.sensor_id, record.capture_scope)
    return (*scope, 'flow', record.flow_id) if record.flow_id is not None else (
        *scope, 'record', record.source_record_ref)


def validate_flow(records):
    """Reject contradictory anchors; never infer a flow from similarity or time proximity.

    Keep all consistent orientations of partial endpoints. Do not choose a direction
    from missing data. Only explicit flow.start timestamps are session-start anchors.
    """
    possibilities = {(None, None, None, None)}
    previous_protocol = previous_start = None
    for record in records:
        raw = record.raw
        endpoints = tuple(str(ip_address(raw[k])) if raw.get(k) is not None else None
                          for k in ('src_ip', 'dest_ip'))
        forward = (endpoints[0], raw.get('src_port'), endpoints[1], raw.get('dest_port'))
        protocol = raw.get('proto')
        protocol = protocol.upper() if isinstance(protocol, str) else None
        start = raw.get('flow', {}).get('start') if isinstance(raw.get('flow'), dict) else None
        if start is not None:
            start = FLOW_START.validate_python(start)
        reverse = (forward[2], forward[3], forward[0], forward[1])
        compatible = set()
        for previous in possibilities:
            for direction in (forward, reverse):
                if all(a is None or b is None or a == b for a, b in zip(previous, direction)):
                    compatible.add(tuple(a if a is not None else b for a, b in zip(previous, direction)))
        if (not compatible
                or (protocol is not None and previous_protocol is not None and protocol != previous_protocol)
                or (start is not None and previous_start is not None and start != previous_start)):
            raise ValueError('contradictory flow anchors within sensor/capture/flow identity')
        possibilities = compatible
        previous_protocol = protocol if protocol is not None else previous_protocol
        previous_start = start if start is not None else previous_start


def build_bundle(records, *, detector_version=None) -> CanonicalAlert:
    # Reparse raw input: derived ids, fields and nested data must never be caller-authoritative.
    records = [parse_record(record.raw, record.sensor_id, record.capture_scope) for record in records]
    if not records or len({correlation_key(record) for record in records}) != 1:
        raise ValueError('bundle must have exactly one safe correlation identity')
    records = list({(record.sensor_id, record.capture_scope, record.source_record_ref): record for record in records}.values())
    if records[0].flow_id is not None and records[0].capture_scope is not None:
        validate_flow(records)
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
    version = 'suricata-bundle-v2' if root.capture_scope is not None else 'suricata-bundle-v1'
    bundle = SuricataEvidenceBundle(schema_version=version, sensor_id=root.sensor_id, capture_scope=root.capture_scope, flow_id=root.flow_id,
        correlation_basis=('sensor_capture_flow_id' if root.capture_scope is not None else 'sensor_flow_id') if root.flow_id is not None else 'independent_record',
        primary_record_ref=root.source_record_ref, native_severity=event.alert.severity,
        related_signatures=signatures, records=tuple(records), transaction_records=transactions,
        evidence_types=tuple(sorted({r.event_type for r in records})))
    raw = {'events': [r.raw for r in records]}
    reference = 'eve-bundle-sha256:' + hashlib.sha256(canonical_json(raw).encode()).hexdigest()
    return CanonicalAlert(canonical_alert_id=uuid5(NAMESPACE_URL,
        canonical_json([version, *correlation_key(root)])),
        occurred_at=root.timestamp, detector_source='suricata', detector_name='Suricata',
        detector_version=detector_version, detection_title=event.alert.signature,
        detection_category=event.alert.category, detector_severity=event.alert.severity, confidence=None,
        source_ip=str(event.src_ip), destination_ip=str(event.dest_ip), source_port=event.src_port,
        destination_port=event.dest_port, protocol=event.proto, evidence_class='external_signature',
        structured_evidence={'suricataBundle': bundle.model_dump(mode='json', by_alias=True,
            exclude={'capture_scope': True, 'records': {'__all__': {'capture_scope'}}} if root.capture_scope is None else None)},
        provenance={'adapterVersion': version, 'sensorId': root.sensor_id,
            **({'captureScope': root.capture_scope} if root.capture_scope is not None else {}),
            'severityScale': 'suricata-rule-priority', 'timestampBasis': 'event-offset'},
        source_record_reference=reference, original_detector_fields=raw)


def bundle_for(canonical) -> SuricataEvidenceBundle | None:
    value = canonical.structured_evidence.get('suricataBundle')
    return SuricataEvidenceBundle.model_validate(value) if value is not None else None
