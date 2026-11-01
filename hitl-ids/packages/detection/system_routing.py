"""One initial, system-attributed decision per admitted correlated detection.

Only trusted persisted facts enter this pipeline. The admission orchestrator owns the
transaction: evidence, priority, classification, routing, case and admission commit together.
"""
from datetime import timedelta
from pathlib import Path
import json
from typing import Literal
from uuid import NAMESPACE_URL, uuid5
from pydantic import Field, model_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract, OperationalTriageStateV2, POLICY_BAND_STORAGE
from packages.contracts.suricata_bundle import SystemRoutingDecision
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.adapters.suricata_bundle import bundle_for, canonical_json
from packages.detection.attack_classification import classify, load_classification_policy
from packages.detection.context_store import resolved_for
from packages.detection.routing import RoutingAudit, state_version
from packages.detection.tier2_cases import CaseSnapshot
from packages.detection.triage_policy import evaluate_triage, load_triage_policy

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / 'config/system-routing-v1.json'
Rule = Literal['unknown_classification_requires_expert', 'confirmed_malicious_and_response_required',
    'high_priority_and_critical_asset', 'repeated_campaign_and_independent_alert_threshold', 'unresolved_requires_expert']


class SystemRoutingPolicy(V2Contract):
    version: str = Field(min_length=1)
    rules: tuple[Rule, ...]
    high_priority_threshold: float = Field(ge=0, le=100)
    campaign_alert_threshold: int = Field(strict=True, ge=2)

    @model_validator(mode='after')
    def rules_valid(self):
        if len(set(self.rules)) != len(self.rules) or 'unknown_classification_requires_expert' not in self.rules:
            raise ValueError('unique rules and unknown-class expert review are required')
        return self


def load_system_routing_policy(path=DEFAULT_POLICY):
    return SystemRoutingPolicy.model_validate_json(path.read_text(encoding='utf-8'))


def evaluate_system_route(classification, priority, context, policy=None):
    policy = SystemRoutingPolicy.model_validate((policy or load_system_routing_policy()).model_dump())
    rules, critical, expert = set(policy.rules), [], []
    if classification.attack_category == 'unknown_needs_expert':
        expert.append('Attack classification cannot be resolved safely from current evidence (Unknown / Needs Expert). This is not a maliciousness verdict.')
    if 'unresolved_requires_expert' in rules and context.unresolved_by_tier1 is True:
        expert.append('Trusted context explicitly reports unresolved Tier 1 investigation; expert handling is required.')
    if 'confirmed_malicious_and_response_required' in rules and context.confirmed_malicious is True and context.response_required is True:
        critical.append('Trusted confirmed malicious context AND response required.')
    if 'high_priority_and_critical_asset' in rules and priority >= policy.high_priority_threshold and context.asset_criticality == 'critical':
        critical.append(f'Operational priority {priority:g} meets {policy.high_priority_threshold:g} AND trusted asset criticality is critical.')
    if ('repeated_campaign_and_independent_alert_threshold' in rules and context.repeated_campaign is True
            and context.correlated_alert_count is not None and context.correlated_alert_count >= policy.campaign_alert_threshold):
        critical.append(f'Trusted repeated campaign AND {context.correlated_alert_count} independent alerts meet threshold {policy.campaign_alert_threshold}; same-flow signatures are not counted.')
    # Classification uncertainty stays visible even if strong risk is also present.
    route_class = 'EXPERT_REVIEW_REQUIRED' if expert else 'CRITICAL_ESCALATION' if critical else 'ROUTINE_REVIEW'
    reasons = expert + critical or [('Explicit informational/policy signal; ' if classification.status == 'informational_policy_signal' else 'Known attack classification; ') + 'no configured trusted critical or expert condition is satisfied. Routine Tier 1 review.']
    return SystemRoutingDecision(route_class=route_class, route='tier2_case' if expert or critical else 'tier1_review',
        policy_version=policy.version, reasons=tuple(reasons))


def _snapshot(model):
    return model.model_dump_json(by_alias=True)


def _version_guard(conn, column, policy):
    # Configuration cannot silently change under an already-recorded version.
    for row in conn.execute(f'SELECT {column} FROM operational_system_routing'):
        old = type(policy).model_validate_json(row[0])
        if old.version == policy.version and old != policy:
            raise ValueError('changed configuration requires a new policy version')


def admit_system_route(conn, alert, request_id):
    if not conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('system routing requires the admission transaction and foreign keys')
    before = read_triage(conn, alert.id)
    if (before.handling_route, before.workflow_stage) != ('unassigned', 'staged') or before.triage_policy_version is not None:
        raise ValueError('initial system routing requires a fresh dormant detection')
    bundle = bundle_for(alert.detector_evidence)
    if bundle is None:
        raise ValueError('system routing requires validated correlated Suricata evidence')
    classification_policy, routing_policy, priority_policy = load_classification_policy(), load_system_routing_policy(), load_triage_policy()
    _version_guard(conn, 'classification_policy', classification_policy)
    _version_guard(conn, 'routing_policy', routing_policy)
    classification = classify(bundle, classification_policy)
    moment = max(m.utc_now(), before.updated_at + timedelta(microseconds=1))
    provenance = resolved_for(conn, alert.operational_alert_ref, moment)
    context = provenance.context
    priority = evaluate_triage(alert, context, priority_policy)
    decision = evaluate_system_route(classification, priority.final_operational_priority, context, routing_policy)
    reason = ' '.join(decision.reasons)
    after = OperationalTriageStateV2(operational_alert_id=alert.id,
        operational_priority=priority.final_operational_priority, priority_band=priority.priority_band,
        priority_band_scheme='p1_p4', handling_route=decision.route,
        workflow_stage='investigation' if decision.route == 'tier2_case' else 'triage',
        review_required=True, review_reason=reason, tier2_recommended=False, tier2_recommendation_reasons=(),
        decision_source='system_policy', triage_policy_version=priority.policy_version, updated_at=moment)
    stamp = db.format_timestamp(moment)
    values = after.model_dump(mode='json', exclude={'operational_alert_id'})
    values.update(priority_band=POLICY_BAND_STORAGE[after.priority_band], tier2_recommendation_reasons='[]', updated_at=stamp)
    conn.execute('UPDATE operational_triage_state_v2 SET ' + ','.join(f'{key}=?' for key in values) +
        ' WHERE operational_alert_id=?', [*values.values(), alert.id])
    priority_config = json.dumps(priority_policy.model_dump(mode='json', by_alias=True), sort_keys=True, allow_nan=False)
    prior_priority = conn.execute('SELECT policy_snapshot FROM operational_triage_policy_audit WHERE policy_version=? LIMIT 1', (priority_policy.version,)).fetchone()
    if prior_priority is not None and json.loads(prior_priority[0]) != json.loads(priority_config):
        raise ValueError('changed priority configuration requires a new policy version')
    # Priority uses the existing score formula; its audit explicitly defers final routing to this policy.
    scoring = priority.model_dump(mode='json', by_alias=True, include={
        'base_priority','base_priority_reason','context_adjustments','final_operational_priority','priority_band','policy_version'})
    scoring['routingPolicyVersion'] = routing_policy.version
    policy_id = conn.execute('INSERT INTO operational_triage_policy_audit '
        '(operational_alert_id,actor_id,decision_source,policy_version,policy_snapshot,context_snapshot,result_snapshot,before_state,after_state,created_at) '
        "VALUES (?,NULL,'system_policy',?,?,?,?,?,?,?)", (alert.id,priority.policy_version,priority_config,
        _snapshot(context),canonical_json(scoring),_snapshot(before),_snapshot(after),stamp)).lastrowid
    conn.execute('INSERT INTO triage_context_provenance (policy_audit_id,snapshot) VALUES (?,?)', (policy_id,_snapshot(provenance)))
    routing_id = conn.execute('INSERT INTO operational_routing_audit '
        '(operational_alert_id,actor_id,decision_source,request_id,action,event_type,expected_state_version,reason,before_state,after_state,created_at) '
        "VALUES (?,NULL,'system_policy',?,'system_route','V2_SYSTEM_ROUTED',?,?,?,?,?)", (alert.id,
        str(uuid5(NAMESPACE_URL, 'system-admission:' + str(request_id))),state_version(before),reason,
        _snapshot(before),_snapshot(after),stamp)).lastrowid
    audit = RoutingAudit(id=routing_id, operational_alert_id=alert.id, actor_id=None, decision_source='system_policy',
        request_id=uuid5(NAMESPACE_URL, 'system-admission:' + str(request_id)), action='system_route',
        event_type='V2_SYSTEM_ROUTED',expected_state_version=state_version(before),reason=reason,
        before_state=before,after_state=after,created_at=stamp)
    case_ref = None
    if decision.route == 'tier2_case':
        case_ref = str(uuid5(NAMESPACE_URL, 'system-tier2-case:' + str(alert.operational_alert_ref)))
        snapshot = CaseSnapshot(detector=alert, triage=after, routing_decision=audit, escalation_reason=reason,
            tier1_handoff_summary='Automatically created by system policy; no manual Tier 1 escalation.', creation_reason=reason)
        case_id = conn.execute('INSERT INTO tier2_cases '
            '(case_ref,primary_operational_alert_id,title,owner_actor_id,created_by_actor_id,decision_source,snapshot,created_at) '
            "VALUES (?,?,?,NULL,NULL,'system_policy',?,?)", (case_ref,alert.id,alert.detection_title[:200],_snapshot(snapshot),stamp)).lastrowid
        conn.execute("INSERT INTO tier2_case_state (case_id,status,revision,updated_at) VALUES (?,'open',1,?)", (case_id,stamp))
        conn.execute('INSERT INTO tier2_case_events '
            '(case_id,actor_id,decision_source,request_id,action,event_type,request_payload,reason,before_state,after_state,created_at) '
            "VALUES (?,NULL,'system_policy',?,'create','V2_TIER2_CASE_CREATED',?,?,?,?,?)", (case_id,
            str(uuid5(NAMESPACE_URL, 'system-case:' + str(request_id))),_snapshot(decision),reason,_snapshot(before),_snapshot(after),stamp))
    conn.execute('INSERT INTO operational_system_routing '
        '(operational_alert_id,classification,classification_policy,routing_decision,routing_policy,context_provenance,'
        'routing_audit_id,policy_audit_id,case_ref,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (alert.id,_snapshot(classification),_snapshot(classification_policy),_snapshot(decision),_snapshot(routing_policy),
         _snapshot(provenance),routing_id,policy_id,case_ref,stamp))
    if read_triage(conn, alert.id) != after:
        raise ValueError('system routing storage round-trip mismatch')
    return policy_id, audit
