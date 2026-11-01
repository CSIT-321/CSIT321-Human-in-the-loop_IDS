"""Immutable, sensor-scoped EVE evidence; identifiers are strings at the JSON boundary."""
from typing import Any, Literal
from pydantic import Field
from packages.contracts.operational_v2 import V2Contract

EveType = Literal['alert', 'flow', 'http', 'dns', 'tls', 'ssh', 'fileinfo', 'anomaly']
AttackCategory = Literal['brute_force', 'botnet_c2', 'dos', 'ddos', 'web_attack',
    'infiltration', 'reconnaissance_port_scan', 'malware_exploit', 'other_known_attack',
    'unknown_needs_expert']


class SuricataRecord(V2Contract):
    source_record_ref: str
    sensor_id: str
    event_type: EveType
    timestamp: str
    flow_id: str | None
    tx_id: str | None
    raw: dict[str, Any]


class RelatedSignature(V2Contract):
    source_record_ref: str
    timestamp: str
    signature_id: int
    signature: str
    native_category: str
    native_severity: int
    action: str | None
    metadata: dict[str, Any]


class SuricataEvidenceBundle(V2Contract):
    schema_version: Literal['suricata-bundle-v1'] = 'suricata-bundle-v1'
    sensor_id: str
    flow_id: str | None
    correlation_basis: Literal['sensor_flow_id', 'independent_record']
    primary_record_ref: str
    native_severity: int
    related_signatures: tuple[RelatedSignature, ...] = Field(min_length=1)
    records: tuple[SuricataRecord, ...] = Field(min_length=1)
    transaction_records: dict[str, tuple[str, ...]]
    evidence_types: tuple[EveType, ...]
    ml_enrichment: Literal['unavailable_no_validated_feature_bridge'] = 'unavailable_no_validated_feature_bridge'


class AttackClassification(V2Contract):
    attack_category: AttackCategory
    status: Literal['mapped', 'unmapped', 'conflict']
    source: Literal['deterministic_suricata_mapping'] = 'deterministic_suricata_mapping'
    reasons: tuple[str, ...] = Field(min_length=1)
    policy_version: str


class SystemRoutingDecision(V2Contract):
    route_class: Literal['ROUTINE_REVIEW', 'CRITICAL_ESCALATION', 'EXPERT_REVIEW_REQUIRED']
    route: Literal['tier1_review', 'tier2_case']
    decision_source: Literal['system_policy'] = 'system_policy'
    policy_version: str
    reasons: tuple[str, ...] = Field(min_length=1)
