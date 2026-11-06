"""Automatic routing of flow alerts into Tier 1 and Tier 2 (analysis/codebase-review/DECISION-BRIEF.md, D3).

One system decision per projected flow alert, written to the same tables and audit as the Suricata routing in
``system_routing``. Three outcomes:

* **auto-escalate (E1)** - the model agrees with a rule and the score is at least ``e1MinimumScore``. The rule is
  either our flow rule engine (``E1-flow-rule``: ``evidence_class == 'corroborated'``) or a linked Suricata alert of
  severity <= ``e1SuricataMaximumSeverity`` (``E1-suricata``). The alert becomes a Tier 2 case.
  Measured on real packets (spike B, 2018-02-14): E1-flow-rule precision 0.99986, recall 1.0.
* **Tier 2 candidate** - E3 (score >= 90 and an attack type of severity >= 7), detectors in conflict, or an E1 alert
  whose branch the Admin switched off. Tier 1 review, with the reasons on the alert. E3 is never automatic: it made
  342 wrong escalations on the stress data.
* **routine Tier 1** - everything else.

Fail-safe: an alert the routing cannot evaluate goes to routine Tier 1 with the reason. Routing never closes,
dismisses or lowers an alert.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from packages.contracts import db, models as m
from packages.contracts.operational_v2 import OperationalTriageStateV2, POLICY_BAND_STORAGE, V2Contract
from packages.contracts.suricata_bundle import AttackClassification, SystemRoutingDecision
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.context_store import resolved_for
from packages.detection.ranking.severity import SeverityChart, load_severity_chart
from packages.detection.routing import RoutingAudit, state_version
from packages.detection.system_routing import _snapshot
from packages.detection.tier2_cases import CaseSnapshot
from packages.detection.triage_policy import evaluate_triage, load_triage_policy
from packages.detection.adapters.suricata_bundle import canonical_json

from uuid import NAMESPACE_URL, uuid5
from datetime import timedelta

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "config/flow-routing-v1.json"
# The model's 8 classes -> the operational attack categories (packages/contracts/suricata_bundle.py).
CATEGORY = {"Brute Force": "brute_force", "Botnet": "botnet_c2", "DoS": "dos", "DDoS": "ddos",
            "Web Attack": "web_attack", "Infiltration": "infiltration", "Port Scan": "reconnaissance_port_scan"}
CLASSIFIER_VERSION = "flow-classification-v1"


class FlowRoutingPolicy(V2Contract):
    version: str = Field(min_length=1)
    e1_flow_rule_enabled: bool
    e1_suricata_enabled: bool
    e1_minimum_score: float = Field(ge=0, le=100)
    e1_suricata_maximum_severity: int = Field(ge=1, le=4)
    e3_minimum_score: float = Field(ge=0, le=100)
    e3_minimum_attack_severity: float = Field(ge=0, le=10)
    new_groups_per_minute: int = Field(ge=1)
    group_window_minutes: int = Field(ge=1)


def load_flow_routing_policy(path: Path = DEFAULT_POLICY) -> FlowRoutingPolicy:
    return FlowRoutingPolicy.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class GroupRoute:
    classification: AttackClassification
    decision: SystemRoutingDecision
    tier2_reasons: tuple[str, ...]
    qualifying_member: int | None = None
    limit_downgraded: bool = False


def classify_flow(alert: m.Alert, policy: FlowRoutingPolicy) -> AttackClassification:
    """The operational attack category of a flow alert, from what its detectors assert."""
    rule = alert.attack_category
    model = alert.ml_predicted_class if alert.ml_predicted_class != "Benign" else None
    if rule and model and rule != model or (rule and alert.ml_predicted_class == "Benign"):
        return AttackClassification(attack_category="unknown_needs_expert", status="conflict",
            reasons=(f"The rule asserts {rule} but the model predicts {alert.ml_predicted_class}.",),
            policy_version=CLASSIFIER_VERSION)
    asserted = rule or model
    if asserted is None:
        return AttackClassification(attack_category=None, status="informational_policy_signal",
            reasons=("No detector asserts an attack class.",), policy_version=CLASSIFIER_VERSION)
    return AttackClassification(attack_category=CATEGORY[asserted], status="mapped",
        reasons=(f"{'Rule and model' if rule and model else 'Rule' if rule else 'Model'} assert {asserted}.",),
        policy_version=CLASSIFIER_VERSION)


def _e1(alert: m.Alert, policy: FlowRoutingPolicy, suricata_severity: int | None) -> list[tuple[str, bool]]:
    """The E1 branches this alert meets, each with whether the Admin has it switched on."""
    if alert.combined_score < policy.e1_minimum_score:
        return []
    model_attack = alert.ml_predicted_class not in (None, "Benign")
    met = []
    if alert.evidence_class == "corroborated":
        met.append((f"E1-flow-rule: the rule and the model agree on {alert.attack_category} at score "
                    f"{alert.combined_score:g}.", policy.e1_flow_rule_enabled))
    if (model_attack and suricata_severity is not None and suricata_severity <= policy.e1_suricata_maximum_severity):
        met.append((f"E1-suricata: a Suricata alert of severity {suricata_severity} and the model "
                    f"({alert.ml_predicted_class}) agree at score {alert.combined_score:g}.", policy.e1_suricata_enabled))
    return met


def route_group(members: list[m.Alert], policy: FlowRoutingPolicy, chart: SeverityChart, *,
                suricata_severity_by_legacy_id: dict[int, int] | None = None,
                escalated_groups_this_minute: int = 0) -> GroupRoute:
    """One route for a whole group: the strongest member outcome wins, the strongest member is marked.

    Any member that meets an enabled E1 branch escalates the whole group. Otherwise the first member whose
    candidate rules apply makes the group a candidate. A group that escalates past the per-minute limit of new
    groups is downgraded to a candidate with the reason; the alert is never closed or lost.
    """
    severity_by_id = suricata_severity_by_legacy_id or {}
    try:
        for i, alert in enumerate(members):
            e1 = _e1(alert, policy, severity_by_id.get(alert.id))
            enabled = [reason for reason, on in e1 if on]
            if not enabled:
                continue
            escalation_reasons = list(enabled)
            if len(members) > 1:
                escalation_reasons.append(f"The whole group of {len(members)} alerts is escalated; "
                                          f"member {i + 1} of {len(members)} qualified.")
            classification = classify_flow(alert, policy)
            if escalated_groups_this_minute >= policy.new_groups_per_minute:
                reason = (f"New-group limit: {policy.new_groups_per_minute} new escalated groups per minute already "
                          f"reached; the group waits for a Tier 1 analyst.")
                return GroupRoute(classification, SystemRoutingDecision(
                    route_class="ROUTINE_REVIEW", route="tier1_review", policy_version=policy.version,
                    reasons=(reason,)), tuple(escalation_reasons) + (reason,), i, True)
            return GroupRoute(classification, SystemRoutingDecision(
                route_class="CRITICAL_ESCALATION", route="tier2_case", policy_version=policy.version,
                reasons=tuple(escalation_reasons)), (), i)
        candidates, candidate_member = [], None
        classification = None
        for i, alert in enumerate(members):
            classification = classification or classify_flow(alert, policy)
            switched = [f"{reason} This rule is switched off, so the alert waits for Tier 1."
                        for reason, on in _e1(alert, policy, severity_by_id.get(alert.id)) if not on]
            if classification.attack_category == "unknown_needs_expert":
                switched.append("The detectors disagree on the attack class: " + " ".join(classification.reasons))
            attack = alert.attack_category or alert.ml_predicted_class
            severity = chart.severity(attack) if attack not in (None, "Benign") else 0.0
            if alert.combined_score >= policy.e3_minimum_score and severity >= policy.e3_minimum_attack_severity:
                switched.append(f"E3: score {alert.combined_score:g} and {attack} has attack severity {severity:g}. "
                                "A Tier 1 analyst confirms before escalation.")
            if switched:
                candidates.extend(switched)
                candidate_member = candidate_member if candidate_member is not None else i
    except Exception as error:  # fail-safe: never escalate or close on a failure
        return GroupRoute(AttackClassification(attack_category=None, status="informational_policy_signal",
            reasons=("Routing could not be evaluated.",), policy_version=CLASSIFIER_VERSION),
            SystemRoutingDecision(route_class="ROUTINE_REVIEW", route="tier1_review", policy_version=policy.version,
                reasons=(f"Routing could not be evaluated ({type(error).__name__}); routine Tier 1 review.",)), ())
    classification = classification or AttackClassification(attack_category=None, status="informational_policy_signal",
        reasons=("No detector asserts an attack class.",), policy_version=CLASSIFIER_VERSION)
    if candidates:
        return GroupRoute(classification, SystemRoutingDecision(route_class="ROUTINE_REVIEW", route="tier1_review",
            policy_version=policy.version, reasons=("Tier 2 candidate; a Tier 1 analyst decides.",)),
            tuple(candidates), candidate_member)
    return GroupRoute(classification, SystemRoutingDecision(route_class="ROUTINE_REVIEW", route="tier1_review",
        policy_version=policy.version, reasons=("No automatic or candidate rule applies. Routine Tier 1 review.",)), ())


def route_flow_alert(conn, operational_id: int, *, policy: FlowRoutingPolicy, chart: SeverityChart,
                     group_members: list[m.Alert] | None = None,
                     suricata_severity_by_legacy_id: dict[int, int] | None = None,
                     escalated_groups_this_minute: int = 0,
                     qualifying_member_alert_id: int | None = None) -> tuple[str, int | None]:
    """Write one system routing decision for a projected flow group. Caller owns the transaction.

    ``group_members`` are the group's legacy alerts in arrival order; when absent the projected alert is the
    whole group. Returns the outcome and the qualifying member's legacy alert id.
    """
    if not conn.in_transaction or not conn.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("flow routing requires a transaction and foreign keys")
    alert_v2 = read_projection(conn, operational_id)
    before = read_triage(conn, operational_id)
    if alert_v2.source_kind != "legacy_flow_alert" or (before.handling_route, before.workflow_stage) != ("unassigned", "staged"):
        raise ValueError("flow routing requires a fresh projected flow alert")
    members = group_members if group_members is not None else [db.get(conn, m.Alert, alert_v2.legacy_alert_id)]
    route = route_group(members, policy, chart,
                        suricata_severity_by_legacy_id=suricata_severity_by_legacy_id,
                        escalated_groups_this_minute=escalated_groups_this_minute)
    decision = route.decision
    qualifying_id = qualifying_member_alert_id if qualifying_member_alert_id is not None \
        else members[route.qualifying_member].id if route.qualifying_member is not None else None
    priority_policy = load_triage_policy()
    moment = max(m.utc_now(), before.updated_at + timedelta(microseconds=1))
    provenance = resolved_for(conn, alert_v2.operational_alert_ref, moment)
    priority = evaluate_triage(alert_v2, provenance.context, priority_policy)
    reason = " ".join(decision.reasons + route.tier2_reasons)
    reason_audit = reason if len(reason) <= 2000 else reason[:1970] + " ... (reasons truncated)"
    after = OperationalTriageStateV2(operational_alert_id=operational_id,
        operational_priority=priority.final_operational_priority, priority_band=priority.priority_band,
        priority_band_scheme="p1_p4", handling_route=decision.route,
        workflow_stage="investigation" if decision.route == "tier2_case" else "triage",
        review_required=True, review_reason=reason, tier2_recommended=bool(route.tier2_reasons),
        tier2_recommendation_reasons=route.tier2_reasons, decision_source="system_policy",
        triage_policy_version=priority.policy_version, updated_at=moment)
    stamp = db.format_timestamp(moment)
    values = after.model_dump(mode="json", exclude={"operational_alert_id"})
    values.update(priority_band=POLICY_BAND_STORAGE[after.priority_band],
                  tier2_recommendation_reasons=json.dumps(list(route.tier2_reasons)), updated_at=stamp)
    conn.execute("UPDATE operational_triage_state_v2 SET " + ",".join(f"{k}=?" for k in values) +
                 " WHERE operational_alert_id=?", [*values.values(), operational_id])
    scoring = priority.model_dump(mode="json", by_alias=True, include={
        "base_priority", "base_priority_reason", "context_adjustments", "final_operational_priority",
        "priority_band", "policy_version"})
    scoring["routingPolicyVersion"] = policy.version
    policy_id = conn.execute("INSERT INTO operational_triage_policy_audit "
        "(operational_alert_id,actor_id,decision_source,policy_version,policy_snapshot,context_snapshot,result_snapshot,"
        "before_state,after_state,created_at) VALUES (?,NULL,'system_policy',?,?,?,?,?,?,?)",
        (operational_id, priority.policy_version,
         json.dumps(priority_policy.model_dump(mode="json", by_alias=True), sort_keys=True, allow_nan=False),
         _snapshot(provenance.context), canonical_json(scoring), _snapshot(before), _snapshot(after), stamp)).lastrowid
    conn.execute("INSERT INTO triage_context_provenance (policy_audit_id,snapshot) VALUES (?,?)",
                 (policy_id, _snapshot(provenance)))
    request_id = uuid5(NAMESPACE_URL, f"flow-routing:{policy.version}:{alert_v2.operational_alert_ref}")
    routing_id = conn.execute("INSERT INTO operational_routing_audit "
        "(operational_alert_id,actor_id,decision_source,request_id,action,event_type,expected_state_version,reason,"
        "before_state,after_state,created_at) VALUES (?,NULL,'system_policy',?,'system_route','V2_SYSTEM_ROUTED',?,?,?,?,?)",
        (operational_id, str(request_id), state_version(before), reason_audit, _snapshot(before), _snapshot(after),
         stamp)).lastrowid
    case_ref = None
    if decision.route == "tier2_case":
        audit = RoutingAudit(id=routing_id, operational_alert_id=operational_id, actor_id=None,
            decision_source="system_policy", request_id=request_id, action="system_route",
            event_type="V2_SYSTEM_ROUTED", expected_state_version=state_version(before), reason=reason,
            before_state=before, after_state=after, created_at=stamp)
        case_ref = str(uuid5(NAMESPACE_URL, "system-tier2-case:" + str(alert_v2.operational_alert_ref)))
        snapshot = CaseSnapshot(detector=alert_v2, triage=after, routing_decision=audit, escalation_reason=reason,
            tier1_handoff_summary="Automatically escalated by flow routing (E1); no manual Tier 1 escalation.",
            creation_reason=reason)
        case_id = conn.execute("INSERT INTO tier2_cases "
            "(case_ref,primary_operational_alert_id,title,owner_actor_id,created_by_actor_id,decision_source,snapshot,created_at) "
            "VALUES (?,?,?,NULL,NULL,'system_policy',?,?)",
            (case_ref, operational_id, alert_v2.detection_title[:200], _snapshot(snapshot), stamp)).lastrowid
        conn.execute("INSERT INTO tier2_case_state (case_id,status,revision,updated_at) VALUES (?,'open',1,?)",
                     (case_id, stamp))
        conn.execute("INSERT INTO tier2_case_events "
            "(case_id,actor_id,decision_source,request_id,action,event_type,request_payload,reason,before_state,after_state,created_at) "
            "VALUES (?,NULL,'system_policy',?,'create','V2_TIER2_CASE_CREATED',?,?,?,?,?)",
            (case_id, str(uuid5(NAMESPACE_URL, f"flow-case:{request_id}")), _snapshot(decision), reason_audit,
             _snapshot(before), _snapshot(after), stamp))
    conn.execute("INSERT INTO operational_system_routing "
        "(operational_alert_id,classification,classification_policy,routing_decision,routing_policy,context_provenance,"
        "routing_audit_id,policy_audit_id,case_ref,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (operational_id, _snapshot(route.classification),
         json.dumps({"version": CLASSIFIER_VERSION, "categories": CATEGORY}, sort_keys=True),
         _snapshot(decision), _snapshot(policy), _snapshot(provenance), routing_id, policy_id, case_ref, stamp))
    if read_triage(conn, operational_id) != after:
        raise ValueError("flow routing storage round-trip mismatch")
    return ("auto_escalated" if decision.route == "tier2_case" else "candidate" if route.tier2_reasons else "routine",
            qualifying_id)


__all__ = ["FlowRoutingPolicy", "GroupRoute", "classify_flow", "route_group", "load_flow_routing_policy",
           "load_severity_chart", "route_flow_alert"]
