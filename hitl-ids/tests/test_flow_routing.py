"""Phase B: automatic routing of flow alerts (decisions D3, D3a, B3, B4 in analysis/codebase-review).

Every projected flow alert gets exactly one system routing decision, with one of three outcomes:

    auto-escalate      E1: the model agrees with a rule (our flow rule engine, or a Suricata alert of severity 1-2)
                       and the score is at least 80 -> a Tier 2 case, no Tier 1 step
    Tier 2 candidate   E3 (score >= 90 and an attack type of severity >= 7), detectors in conflict, or an E1 alert
                       whose rule is switched off -> Tier 1 review, with the reasons shown
    routine Tier 1     everything else -> Tier 1 review

Fail-safe: anything the routing cannot evaluate goes to routine Tier 1 with the reason. Nothing is ever closed.
The synthetic capture (tests/conftest.py): AL-0001..0009 are rule + model Brute Force on TCP/21 (corroborated);
AL-0010..0015 are model-only Botnet on TCP/8080; AL-0016..0021 are unflagged benign.
"""
from contextlib import closing
import json
import sys
from pathlib import Path

import pytest

from packages.contracts import db, models as m
from packages.detection import flow_routing
from packages.detection.analyst_work import is_tier1_work
from packages.detection.ranking.severity import load_severity_chart
from test_api import database  # noqa: F401  (pytest fixture)
from test_operational_v2 import snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import materialize_flagged, route_flagged  # noqa: E402

CHART = load_severity_chart()


def routed(conn):
    """source_record_id -> (route, tier2_recommended, reasons, case_ref, rule)."""
    out = {}
    for r in conn.execute("""
            SELECT f.source_record_id, t.handling_route, t.tier2_recommended, t.tier2_recommendation_reasons,
                   s.case_ref, s.routing_decision
            FROM operational_alerts_v2 o
            JOIN flow_data f ON f.alert_id = o.legacy_alert_id
            JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id
            LEFT JOIN operational_system_routing s ON s.operational_alert_id = o.id"""):
        decision = json.loads(r[5]) if r[5] else None
        out[r[0]] = (r[1], bool(r[2]), tuple(json.loads(r[3])), r[4], decision)
    return out


def prepare(conn, policy=None):
    materialize_flagged(conn)
    return route_flagged(conn, policy=policy)


# ---------------------------------------------------------------------------------------------- end to end


def test_every_projected_flow_alert_gets_one_routing_decision(database):
    with closing(db.connect(str(database))) as conn:
        counts = prepare(conn)
        rows = routed(conn)
    assert len(rows) == 15 and all(v[4] is not None for v in rows.values())
    assert sum(counts.values()) == 15


def test_e1_flow_rule_alerts_are_escalated_to_a_tier2_case(database):
    with closing(db.connect(str(database))) as conn:
        prepare(conn)
        rows = routed(conn)
    for ref in [f"AL-{i:04d}" for i in range(1, 10)]:
        route, _, _, case_ref, decision = rows[ref]
        assert route == "tier2_case" and case_ref is not None, ref
        assert decision["routeClass"] == "CRITICAL_ESCALATION"
        assert any("E1-flow-rule" in reason for reason in decision["reasons"]), decision["reasons"]


def test_model_only_high_severity_alerts_are_tier2_candidates_with_reasons(database):
    with closing(db.connect(str(database))) as conn:
        prepare(conn)
        rows = routed(conn)
    for ref in [f"AL-{i:04d}" for i in range(10, 16)]:
        route, recommended, reasons, case_ref, _ = rows[ref]
        assert (route, recommended, case_ref) == ("tier1_review", True, None), ref
        assert any(reason.startswith("E3") for reason in reasons), reasons


def test_routed_tier1_flow_alerts_can_be_claimed(database):
    with closing(db.connect(str(database))) as conn:
        prepare(conn)
        ids = [r[0] for r in conn.execute(
            "SELECT o.id FROM operational_alerts_v2 o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
            "WHERE t.handling_route='tier1_review'")]
        assert ids and all(is_tier1_work(conn, i) for i in ids)


def test_a_switched_off_rule_turns_its_escalations_into_candidates(database):
    policy = flow_routing.load_flow_routing_policy().model_copy(update={"version": "flow-routing-test-off",
                                                                        "e1_flow_rule_enabled": False})
    with closing(db.connect(str(database))) as conn:
        prepare(conn, policy=policy)
        rows = routed(conn)
    route, recommended, reasons, case_ref, _ = rows["AL-0001"]
    assert (route, recommended, case_ref) == ("tier1_review", True, None)
    assert any("switched off" in reason for reason in reasons), reasons


def test_a_second_run_routes_nothing_new(database):
    with closing(db.connect(str(database))) as conn:
        first = prepare(conn)
        audits = conn.execute("SELECT count(*) FROM operational_routing_audit").fetchone()[0]
        second = route_flagged(conn)
        assert sum(first.values()) == 15 and sum(second.values()) == 0
        assert conn.execute("SELECT count(*) FROM operational_routing_audit").fetchone()[0] == audits


def test_routing_leaves_the_legacy_workflow_rows_unchanged(database):
    with closing(db.connect(str(database))) as conn:
        before = snapshot(conn)
        prepare(conn)
        assert snapshot(conn) == before


def test_every_decision_is_audited_as_system_policy_with_the_policy_version(database):
    with closing(db.connect(str(database))) as conn:
        prepare(conn)
        audits = conn.execute("SELECT decision_source, actor_id, action FROM operational_routing_audit").fetchall()
        versions = {json.loads(r[0])["policyVersion"] for r in conn.execute(
            "SELECT routing_decision FROM operational_system_routing")}
    assert len(audits) == 15 and all(tuple(a) == ("system_policy", None, "system_route") for a in audits)
    assert versions == {flow_routing.load_flow_routing_policy().version}


# ---------------------------------------------------------------------------------------------- the rules


def alert(evidence, score, ml, category=None):
    return m.Alert.model_construct(evidence_class=evidence, combined_score=score, ml_predicted_class=ml,
                                   attack_category=category)


def decide(a, *, suricata_severity=None, policy=None):
    policy = policy or flow_routing.load_flow_routing_policy()
    return flow_routing.evaluate_flow_route(a, flow_routing.classify_flow(a, policy), policy, CHART,
                                            suricata_severity=suricata_severity)


def test_e1_suricata_branch_escalates_model_only_alerts_with_a_severe_suricata_alert():
    result = decide(alert("ml_only", 85.0, "Brute Force"), suricata_severity=2)
    assert result.decision.route == "tier2_case"
    assert any("E1-suricata" in reason for reason in result.decision.reasons)


def test_e1_suricata_ignores_informational_suricata_alerts():
    result = decide(alert("ml_only", 85.0, "Brute Force"), suricata_severity=3)
    assert result.decision.route == "tier1_review" and not result.tier2_reasons  # Brute Force is severity 5.0


def test_e1_needs_a_score_of_at_least_80():
    result = decide(alert("corroborated", 79.99, "Brute Force", "Brute Force"))
    assert result.decision.route == "tier1_review"


def test_detector_conflict_is_a_candidate_never_an_automatic_case():
    result = decide(alert("signature_override", 95.0, "Benign", "Brute Force"))
    assert result.decision.route == "tier1_review"
    assert result.classification.attack_category == "unknown_needs_expert"
    assert any("disagree" in reason for reason in result.tier2_reasons)


def test_low_severity_model_only_alerts_are_routine():
    result = decide(alert("ml_only", 99.0, "Port Scan"))  # Port Scan is severity 3.0
    assert result.decision.route == "tier1_review" and not result.tier2_reasons
    assert result.decision.route_class == "ROUTINE_REVIEW"


def test_anything_the_routing_cannot_evaluate_goes_to_routine_tier1(monkeypatch):
    def broken(*_args, **_kwargs):
        raise KeyError("no such class")
    monkeypatch.setattr(flow_routing, "_e1", broken)
    result = decide(alert("corroborated", 100.0, "Brute Force", "Brute Force"))
    assert result.decision.route == "tier1_review" and result.decision.route_class == "ROUTINE_REVIEW"
    assert any("could not be evaluated" in reason for reason in result.decision.reasons)
