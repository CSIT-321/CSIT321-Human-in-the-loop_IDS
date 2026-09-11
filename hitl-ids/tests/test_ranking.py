"""Ranking (Q24-Q27): the editable severity chart, the four formulas, class movement, and the
experiment's scorer matching the real guardrails."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from typing import get_args

import pytest

from packages.contracts import models as m
from packages.detection.guardrail.policy import apply_guardrails
from packages.detection.ranking.experiment import (
    Arm,
    Flow,
    calibrate,
    family_key,
    final_score,
    parse_timestamps,
    select,
    simulate,
)
from packages.detection.ranking.formulas import (
    FamilyState,
    RankingParams,
    agreement,
    apply_verdict,
    effective,
    queue_class,
    verdict_delta,
)
from packages.detection.ranking.severity import DEFAULT_CHART, band, load_severity_chart

T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


# -- severity chart -------------------------------------------------------------------------


def test_chart_holds_the_approved_values():
    chart = load_severity_chart()
    assert chart.version == "sev-1"
    assert {c: chart.severity(c) for c in get_args(m.AttackClass)} == {
        "Benign": 0.0, "Port Scan": 3.0, "Brute Force": 5.0, "DoS": 6.5, "DDoS": 7.5,
        "Web Attack": 8.0, "Botnet": 9.0, "Infiltration": 9.5}
    assert len(chart.entries) == 15
    assert chart.weight("Web Attack") == pytest.approx(0.8) and chart.weight(None) == 0


def test_bands_follow_cvss():
    assert [band(s) for s in (0, 0.1, 3.9, 4.0, 6.9, 7.0, 8.9, 9.0, 10)] == [
        "None", "Low", "Low", "Medium", "Medium", "High", "High", "Critical", "Critical"]


def test_chart_values_can_be_changed_in_the_file(tmp_path):
    document = json.loads(DEFAULT_CHART.read_text("utf-8"))
    for entry in document["entries"]:
        if entry["model_class"] == "Port Scan":
            entry["severity"] = 4.0
    edited = tmp_path / "chart.json"
    edited.write_text(json.dumps(document), "utf-8")
    chart = load_severity_chart(edited)
    assert chart.weight("Port Scan") == pytest.approx(0.4)
    assert chart.entry("Port Scan").band == "Medium"


def test_a_chart_missing_a_model_class_is_refused(tmp_path):
    document = json.loads(DEFAULT_CHART.read_text("utf-8"))
    document["entries"] = [e for e in document["entries"] if e["model_class"] != "DoS"]
    bad = tmp_path / "chart.json"
    bad.write_text(json.dumps(document), "utf-8")
    with pytest.raises(ValueError, match="DoS"):
        load_severity_chart(bad)


# -- the four formulas: the design document's worked numbers ---------------------------------


def test_c2_reproduces_the_worked_numbers():
    c2 = RankingParams(formula="C2")
    assert verdict_delta(c2, "confirm_true_positive", 36.94, 0.8) == pytest.approx(17.03, abs=0.01)
    assert verdict_delta(c2, "mark_false_positive", 99.89, 0.8) == pytest.approx(-17.98, abs=0.01)
    assert verdict_delta(c2, "mark_false_positive", 95, 0.3) == pytest.approx(-24.23, abs=0.01)
    assert verdict_delta(c2, "confirm_true_positive", 100, 0.5) == 0  # self-limiting


def test_c0_c1_c3():
    assert verdict_delta(RankingParams(formula="C0"), "mark_false_positive", 99, 0.8) == -30
    c1 = RankingParams(formula="C1")
    assert verdict_delta(c1, "confirm_true_positive", 50, 0.8) == pytest.approx(24)
    assert verdict_delta(c1, "mark_false_positive", 50, 0.8) == pytest.approx(-6)
    c2, c3 = RankingParams(formula="C2"), RankingParams(formula="C3")
    fresh = verdict_delta(c3, "mark_false_positive", 90, 0.5, verdicts=0)
    assert fresh == pytest.approx(verdict_delta(c2, "mark_false_positive", 90, 0.5))
    assert verdict_delta(c3, "mark_false_positive", 90, 0.5, verdicts=3) == pytest.approx(
        fresh / 2 ** 0.5)
    assert verdict_delta(c3, "mark_false_positive", 90, 0.5, verdicts=1000) == pytest.approx(
        fresh * 0.4)


def test_needs_investigation_moves_nothing():
    for formula in ("C0", "C1", "C2", "C3"):
        assert verdict_delta(RankingParams(formula=formula), "needs_investigation", 50, 0.5) == 0


def test_family_adjustment_stays_inside_the_guardrail_caps():
    state, params = FamilyState(), RankingParams(formula="C0")
    for _ in range(5):
        apply_verdict(state, params, "mark_false_positive", 90, 0.5)
    assert state.adjustment == -30
    for _ in range(10):
        apply_verdict(state, params, "escalate", 90, 0.5)
    assert state.adjustment == 20


# -- class movement ------------------------------------------------------------------------


def test_m1_promotes_one_class_and_demotes_only_after_the_shield():
    state, params = FamilyState(), RankingParams(movement="M1")
    apply_verdict(state, params, "confirm_true_positive", 40, 0.8)
    assert state.class_offset == -1
    apply_verdict(state, params, "mark_false_positive", 60, 0.8)
    assert state.class_offset == -1  # the shield holds after one dismissal
    apply_verdict(state, params, "mark_false_positive", 60, 0.8)
    assert state.class_offset == 0


def test_m2_sends_a_confirmed_family_to_the_top():
    state = apply_verdict(FamilyState(), RankingParams(movement="M2"), "confirm_true_positive",
                          40, 0.8)
    assert queue_class("none", state.class_offset, tier2=False) == 0


def test_tier_loss_protection_keeps_flagged_alerts_out_of_the_bottom_band():
    assert queue_class("ml_only", 4, tier2=False) == 3
    assert queue_class("ml_only", 4, tier2=False, protect=False) == 4
    assert queue_class("none", -1, tier2=False) == 3  # a promoted unflagged alert joins ml_only


# -- the experiment's scorer is the guardrail code -----------------------------------------


def flow(score: float, evidence: str, critical: bool, infiltration: bool = False) -> Flow:
    return Flow(alert_id="AL-X", order=0, family=("x",), evidence_class=evidence,
                detection_score=score, is_critical=critical, critical_protected=critical,
                infiltration=infiltration, attack_class="DoS", severity=6.5, weight=0.65,
                malicious=True)


def alert(f: Flow) -> m.Alert:
    rules = None
    if f.evidence_class in ("corroborated", "signature_override"):
        rules = [m.SignatureMatch(rule_id="SIG-X", version="t", name="x", attack_category="DoS",
                                  severity="Medium", matched_conditions=[m.MatchedCondition(
                                      feature="destinationPort", expected=22, observed=22)])]
    predicted = "Benign" if f.evidence_class in ("signature_override", "none") else "DoS"
    return m.Alert(dataset_id=1, run_id=1, detection_score=f.detection_score,
                   combined_score=f.detection_score, severity="Critical", confidence=0.9,
                   signature_rules=rules, ml_predicted_class=predicted,
                   attack_category="Infiltration" if f.infiltration else "DoS",
                   explanation="x", is_critical=f.is_critical, evidence_class=f.evidence_class,
                   evidence_priority=0, created_at=T0, updated_at=T0)


def test_experiment_scorer_matches_apply_guardrails():
    for score, evidence, critical, infiltration, adjustment in itertools.product(
            [10, 60, 72, 80, 99.89, 100], ["ml_only", "corroborated", "signature_override"],
            [True, False], [False, True], [-30, -17.98, -5, 0, 7.5, 20]):
        f = flow(score, evidence, critical, infiltration)
        expected = apply_guardrails(alert(f), adjustment).score_after
        assert final_score(f, adjustment, guardrails=True) == pytest.approx(expected, abs=0.011)


def test_selection_requires_severity_scaling_then_robustness():
    def row(formula, movement, key, error_rate, demoted, tier2_precision=1.0, changes=10):
        return {"formula": formula, "movement": movement, "guardrails": True, "gated": True,
                "family_key": key, "error_rate": error_rate, "floor_violations": 0,
                "attacks_demoted": demoted, "tier2_precision": tier2_precision, "tier2_load": 243,
                "mean_attack_position": 0.08, "precision_at_100": 1.0, "class_changes": changes}
    aggregates = [row(f, mv, key, e, demoted=59 if f == "C2" and e else 0,
                      tier2_precision=0.74 if mv == "M2" and e else 1.0,
                      changes=5 if mv == "M2" else 25)
                  for f in ("C0", "C1", "C2", "C3") for mv in ("M1", "M2")
                  for key in ("coarse", "fine") for e in (0.0, 0.05, 0.15)]
    ranked = select(aggregates)
    best = ranked[0]
    assert (best["formula"], best["movement"], best["family_key"]) == ("C1", "M1", "coarse")
    assert not any(r["meets_q27"] for r in ranked if r["formula"] == "C0")
    assert ranked[-1]["formula"] == "C0"  # fixed steps never win, however good their numbers


# -- the agreement gate (the collaborator's aggregation rule) ---------------------------------


def test_gate_needs_three_agreeing_verdicts():
    state, params = FamilyState(), RankingParams(formula="C1", movement="M1")
    for _ in range(2):
        apply_verdict(state, params, "mark_false_positive", 99.89, 0.8)
    assert effective(state, gated=False) == (state.adjustment, state.class_offset)
    assert effective(state, gated=True) == (0.0, 0)  # two verdicts: closed
    apply_verdict(state, params, "mark_false_positive", 99.89, 0.8)
    assert effective(state, gated=True) == (state.adjustment, state.class_offset)  # three agree


def test_gate_uses_the_collaborators_ratio_and_refuses_ties():
    two_of_three = FamilyState(adjustment=10.0, class_offset=-2, confirmations=2, dismissals=1)
    assert agreement(two_of_three) == (1, 0.6667)
    assert effective(two_of_three, gated=True) == (0.0, 0)  # 0.6667 < 0.67, as in feedback-engine.js
    three_of_four = FamilyState(adjustment=10.0, class_offset=-2, confirmations=3, dismissals=1)
    assert effective(three_of_four, gated=True) == (10.0, -2)
    tie = FamilyState(adjustment=5.0, class_offset=-1, confirmations=2, dismissals=2)
    assert effective(tie, gated=True) == (0.0, 0)


def test_gate_applies_only_learning_that_points_the_dominant_way():
    # run 2's M2 failure: thirteen correct dismissals, then one wrong confirmation of a benign family
    state, params = FamilyState(), RankingParams(formula="C1", movement="M2")
    for _ in range(13):
        apply_verdict(state, params, "mark_false_positive", 5.0, 0.0)
    apply_verdict(state, params, "confirm_true_positive", 5.0, 0.0)
    assert state.class_offset < 0  # ungated, M2 sends the family to the top
    adjustment, offset = effective(state, gated=True)
    assert offset == 0 and adjustment <= 0  # gated, the promotion against the majority is ignored


def test_fine_family_key_always_adds_the_destination_ip():
    assert family_key("Web Attack", 80, "TCP", "-", "10.0.0.5", "ml_only") == (
        "Web Attack", 80, "TCP", "-")
    assert family_key("Benign", 53, "UDP", "-", "10.0.0.2", "none") == (
        "Benign", 53, "UDP", "-", "10.0.0.2")
    assert family_key("Web Attack", 80, "TCP", "-", "10.0.0.5", "ml_only", "fine") == (
        "Web Attack", 80, "TCP", "-", "10.0.0.5")
    with pytest.raises(ValueError):
        family_key("DoS", 80, "TCP", "-", "10.0.0.5", "ml_only", "exact")


def test_timestamps_parse_as_iso_never_day_first():
    import pandas as pd

    parsed = parse_timestamps(pd.Series(["2018-03-01 12:15:42.329367",
                                         "2018-02-14 16:21:49.364081"]))
    assert [(t.month, t.day) for t in parsed] == [(3, 1), (2, 14)]  # 1 March, not 3 January
    with pytest.raises(ValueError):
        parse_timestamps(pd.Series(["01/03/2018 12:15"]))


def test_simulation_is_reproducible_for_a_seed():
    flows = [Flow(alert_id=f"AL-{i:03}", order=i, family=(i % 4,), evidence_class=e,
                  detection_score=s, is_critical=s >= 80, critical_protected=s >= 80,
                  infiltration=False, attack_class="DoS", severity=6.5, weight=0.65,
                  malicious=mal)
             for i, (e, s, mal) in enumerate(
                 [("ml_only", 95, True), ("ml_only", 90, False), ("none", 20, False),
                  ("none", 35, True)] * 30)]
    arm = Arm("C2", "M1", True, 0.15, 7)
    first = simulate(flows[:60], flows[60:], arm, rounds=4, batch=5, qa_sample=2)
    assert simulate(flows[:60], flows[60:], arm, rounds=4, batch=5, qa_sample=2) == first
    assert first["floor_violations"] == 0

    families, log = calibrate(flows[:60], arm, rounds=4, batch=5, qa_sample=2)
    assert len(log) == 4 * (5 + 2)  # every reviewed alert is logged once
    assert sum(e["learned"] for e in log) == first["verdicts"]
    assert sum(e["wrong"] for e in log) == first["wrong_verdicts"]
    for family, state in families.items():
        learned = [e for e in log if e["learned"] and e["family"] == family]
        assert state.verdicts == len(learned)
        assert state.adjustment == learned[-1]["adjustment_after"]

    gated = Arm("C2", "M1", True, 0.15, 7, gated=True)
    once = simulate(flows[:60], flows[60:], gated, rounds=4, batch=5, qa_sample=2)
    assert simulate(flows[:60], flows[60:], gated, rounds=4, batch=5, qa_sample=2) == once
    assert once["floor_violations"] == 0 and once["gated"] is True
