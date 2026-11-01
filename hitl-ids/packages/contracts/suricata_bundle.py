"""Immutable, sensor-scoped EVE evidence; identifiers are strings at the JSON boundary."""
from typing import Any, Literal
from pydantic import Field, model_validator
from packages.contracts.operational_v2 import V2Contract

EveType = Literal['alert', 'flow', 'http', 'dns', 'tls', 'ssh', 'fileinfo', 'anomaly']
AttackCategory = Literal['brute_force', 'botnet_c2', 'dos', 'ddos', 'web_attack',
    'infiltration', 'reconnaissance_port_scan', 'malware_exploit', 'other_known_attack',
    'unknown_needs_expert']


class SuricataRecord(V2Contract):
    source_record_ref: str
    sensor_id: str
    capture_scope: str | None = Field(default=None, min_length=1, max_length=200)
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
    schema_version: Literal['suricata-bundle-v1', 'suricata-bundle-v2'] = 'suricata-bundle-v1'
    sensor_id: str
    capture_scope: str | None = Field(default=None, min_length=1, max_length=200)
    flow_id: str | None
    correlation_basis: Literal['sensor_flow_id', 'sensor_capture_flow_id', 'independent_record']
    primary_record_ref: str
    native_severity: int
    related_signatures: tuple[RelatedSignature, ...] = Field(min_length=1)
    records: tuple[SuricataRecord, ...] = Field(min_length=1)
    transaction_records: dict[str, tuple[str, ...]]
    evidence_types: tuple[EveType, ...]
    ml_enrichment: Literal['unavailable_no_validated_feature_bridge'] = 'unavailable_no_validated_feature_bridge'


class ClassificationMatch(V2Contract):
    rule_id: str
    source_record_ref: str
    signature_id: int
    field: str
    value: str
    category: AttackCategory | None


class AttackClassification(V2Contract):
    attack_category: AttackCategory | None
    status: Literal['mapped', 'unmapped', 'conflict', 'informational_policy_signal']
    source: Literal['deterministic_suricata_mapping'] = 'deterministic_suricata_mapping'
    reasons: tuple[str, ...] = Field(min_length=1)
    policy_version: str
    matches: tuple[ClassificationMatch, ...] = ()
    conflicting_categories: tuple[AttackCategory, ...] = ()

    @model_validator(mode='after')
    def coherent(self):
        if (self.attack_category is None) != (self.status == 'informational_policy_signal'):
            raise ValueError('only explicit informational/policy signals have no attack category')
        if (self.attack_category == 'unknown_needs_expert') != (self.status in ('unmapped', 'conflict')):
            raise ValueError('unresolved/conflicting attacks must remain Unknown / Needs Expert')
        return self


class SystemRoutingDecision(V2Contract):
    route_class: Literal['ROUTINE_REVIEW', 'CRITICAL_ESCALATION', 'EXPERT_REVIEW_REQUIRED']
    route: Literal['tier1_review', 'tier2_case']
    decision_source: Literal['system_policy'] = 'system_policy'
    policy_version: str
    reasons: tuple[str, ...] = Field(min_length=1)
