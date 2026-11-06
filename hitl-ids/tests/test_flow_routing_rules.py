"""The pure flow-routing rules (E1 branches, E3, conflict, fail-safe) and their Admin switches.

The group-level routing is in test_flow_routing.py; these pin the member-level decision rules.
"""
import pytest

from packages.contracts import models as m
from packages.detection import flow_routing
from packages.detection.ranking.severity import load_severity_chart

CHART = load_severity_chart()


def alert(evidence, score, ml, category=None):
    return m.Alert.model_construct(evidence_class=evidence, combined_score=score, ml_predicted_class=ml,
                                   attack_category=category)


def decide(a, *, suricata_severity=None, policy=None):
    policy = policy or flow_routing.load_flow_routing_policy()
    return flow_routing.route_group([a], policy, CHART,
                                    suricata_severity_by_legacy_id={a.id: suricata_severity}
                                    if suricata_severity is not None else None)


def test_e1_suricata_branch_escalates_model_only_alerts_with_a_severe_suricata_alert():
    a = alert("ml_only", 85.0, "Brute Force")
    result = decide(a, suricata_severity=2)
    assert result.decision.route == "tier2_case"
    assert any("E1-suricata" in reason for reason in result.decision.reasons)


def test_e1_suricata_ignores_informational_suricata_alerts():
    a = alert("ml_only", 85.0, "Brute Force")
    result = decide(a, suricata_severity=3)
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


def group(*members):
    for i, member in enumerate(members, start=1):
        member.__dict__.update(id=i)
    return list(members)


def test_a_conflicting_member_after_the_first_still_makes_the_group_a_candidate():
    # review 2026-11-06: classification was computed once, from the first member only
    members = group(alert("ml_only", 50.0, "Port Scan"), alert("signature_override", 95.0, "Benign", "Brute Force"))
    result = flow_routing.route_group(members, flow_routing.load_flow_routing_policy(), CHART)
    assert result.decision.route == "tier1_review"
    assert any("disagree" in reason for reason in result.tier2_reasons), result.tier2_reasons
    assert result.qualifying_member == 1


def test_a_conflicting_first_member_does_not_mark_the_whole_group_as_conflicting():
    members = group(alert("signature_override", 95.0, "Benign", "Brute Force"), alert("ml_only", 50.0, "Port Scan"),
                    alert("ml_only", 40.0, "Port Scan"))
    result = flow_routing.route_group(members, flow_routing.load_flow_routing_policy(), CHART)
    assert sum("disagree" in reason for reason in result.tier2_reasons) == 1, result.tier2_reasons


def test_group_reasons_are_summarised_not_repeated_per_member():
    # review 2026-11-06: one E3 sentence per member (57 members -> 17 copies of 3 sentences)
    members = group(*[alert("ml_only", 99.0, "Infiltration") for _ in range(40)])
    result = flow_routing.route_group(members, flow_routing.load_flow_routing_policy(), CHART)
    assert result.tier2_reasons, "an Infiltration group at score 99 is a candidate"
    assert len(result.tier2_reasons) == len(set(result.tier2_reasons)), "no repeated reason"
    assert len(result.tier2_reasons) <= 5, result.tier2_reasons
    assert any("40 of 40 members" in reason for reason in result.tier2_reasons), result.tier2_reasons
