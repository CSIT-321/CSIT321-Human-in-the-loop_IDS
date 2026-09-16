"""S7 - feedback and guardrails: the project's safety claim, proven by test rather than asserted.

Pure guardrail cases first (the plan's verify list, plus the collaborator's JS tests ported), then
the feedback service against a real SQLite file: storage, re-scoring, audit and rollback.
"""

from __future__ import annotations

import itertools
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.feedback.service import (
    FEEDBACK_EFFECTS,
    current_feedback,
    load_policy,
    submit_feedback,
)
from packages.detection.feedback.learning import family_key_of
from packages.detection.fusion.cef import (
    EVIDENCE_PRIORITY,
    FusionConfig,
    ceilings_from_chart,
    severity_for,
)
from packages.detection.guardrail.policy import GuardrailPolicy, apply_guardrails
from packages.detection.pipeline.runner import _place
from packages.detection.ranking.severity import load_severity_chart

T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

#: The ceilings the committed severity chart yields - the same ones detection and feedback use.
CEILINGS = ceilings_from_chart(load_severity_chart())
CATEGORIES = list(get_args(m.FeedbackCategory))


def match(severity: str = "Medium", attack: str = "Brute Force") -> m.SignatureMatch:
    return m.SignatureMatch(
        rule_id="SIG-SSH-BRUTE-FORCE", version="s4b-1", name="SSH rule", attack_category=attack,
        severity=severity,
        matched_conditions=[m.MatchedCondition(feature="destinationPort", expected=22,
                                               observed=22)])


def alert(score: float, *, evidence: str = "ml_only", attack: str = "DoS",
          critical: bool | None = None, rule_severity: str = "Medium",
          dataset_id: int = 1, run_id: int = 1) -> m.Alert:
    critical = score >= 80 if critical is None else critical
    rules = [match(rule_severity, attack)] if evidence in ("corroborated",
                                                          "signature_override") else None
    predicted = {"corroborated": attack, "ml_only": attack}.get(evidence, "Benign")
    return m.Alert(
        dataset_id=dataset_id, run_id=run_id, detection_score=score, combined_score=score,
        severity="Critical" if critical else "Medium", confidence=0.9, signature_rules=rules,
        ml_predicted_class=predicted, attack_category=None if evidence == "none" else attack,
        explanation="test alert", is_critical=critical, evidence_class=evidence,
        evidence_priority=EVIDENCE_PRIORITY[evidence], created_at=T0, updated_at=T0)


def codes(outcome: m.GuardrailOutcome) -> list[str]:
    return [item.code for item in outcome.interventions]


# --------------------------------------------------------------------------------------------
# The guardrails, pure
# --------------------------------------------------------------------------------------------


def test_tdm_worked_example():
    # TDM: score 92, requested -40 -> capped at -30 -> 62 -> Critical floor -> final 70, actual -22
    outcome = apply_guardrails(alert(92), -40)
    assert (outcome.action, outcome.actual_delta, outcome.score_after) == ("capped", -22, 70)
    assert codes(outcome) == ["maximum_negative_adjustment_capped", "critical_alert_floor"]
    assert outcome.requires_review


def test_ported_js_case_critical_rule_triggers_the_floor():
    # stage-5 test: score 95, a Critical-severity rule, non-Critical alert, -90 -> -30 -> held at 70
    protected = alert(95, evidence="corroborated", critical=False, rule_severity="Critical")
    outcome = apply_guardrails(protected, -90)
    assert (outcome.actual_delta, outcome.score_after) == (-25, 70)
    assert codes(outcome) == ["maximum_negative_adjustment_capped", "critical_alert_floor"]


def test_ported_js_case_configured_values_are_used():
    policy = GuardrailPolicy(max_feedback_reduction=20, max_feedback_increase=12,
                             critical_alert_floor=85, infiltration_alert_floor=90)
    outcome = apply_guardrails(alert(92), -50, policy)
    assert outcome.score_after == 85
    assert [(i.code, i.configured_value) for i in outcome.interventions] == [
        ("maximum_negative_adjustment_capped", -20), ("critical_alert_floor", 85)]
    assert apply_guardrails(alert(50, critical=False), 30, policy).actual_delta == 12


def test_non_finite_change_is_rejected():
    for bad in (float("inf"), float("-inf"), float("nan")):
        outcome = apply_guardrails(alert(92), bad)
        assert (outcome.action, outcome.actual_delta, outcome.score_after) == ("rejected", 0, 92)
        assert codes(outcome) == ["non_finite_adjustment_rejected"]


def test_positive_change_is_capped_at_plus_twenty_without_forcing_review():
    outcome = apply_guardrails(alert(40, critical=False), 25)
    assert (outcome.action, outcome.actual_delta, outcome.score_after) == ("capped", 20, 60)
    assert codes(outcome) == ["maximum_increase_capped"] and not outcome.requires_review


def test_score_never_leaves_the_range():
    top = apply_guardrails(alert(95), 20)
    assert (top.score_after, top.actual_delta, codes(top)) == (100, 5, ["score_range_clamped"])
    bottom = apply_guardrails(alert(10, critical=False), -30)
    assert (bottom.score_after, bottom.actual_delta) == (0, -10)


def test_floors_never_raise_a_score():
    # The JS engine lifted a sub-75 Infiltration alert to 75 on a "false positive"; the port does not.
    low = apply_guardrails(alert(60, attack="Infiltration", critical=False), -30)
    assert (low.score_after, codes(low)) == (30, [])
    high = apply_guardrails(alert(90, attack="Infiltration"), -30)
    assert high.score_after == 75
    assert codes(high) == ["critical_alert_floor", "infiltration_alert_floor"]


def test_i3_signature_override_is_frozen_by_every_category():
    override = alert(60, evidence="signature_override", critical=False)
    for category, effect in FEEDBACK_EFFECTS.items():
        outcome = apply_guardrails(override, effect.requested_delta)
        assert outcome.score_after == 60, category
        assert outcome.requires_review, category
        if effect.requested_delta:
            assert (outcome.action, codes(outcome)) == ("rejected",
                                                        ["signature_override_feedback_immune"])
        else:
            assert codes(outcome) == ["signature_ml_disagreement_review_preserved"]


def test_a_critical_alert_can_never_fall_below_its_floor():
    policy = GuardrailPolicy()
    for base, requested, attack in itertools.product(
            [80, 85.5, 92, 99.89, 100], [-1000, -100, -40, -30, -15, -1, 0, 10, 20, 50],
            ["DoS", "Infiltration"]):
        after = apply_guardrails(alert(base, attack=attack), requested, policy).score_after
        assert after >= policy.critical_alert_floor, (base, requested)
        if attack == "Infiltration":
            assert after >= policy.infiltration_alert_floor, (base, requested)


def test_capped_and_rejected_are_counted_apart():
    actions = Counter(apply_guardrails(a, r).action for a, r in [
        (alert(92), -40), (alert(60, evidence="signature_override", critical=False), -30),
        (alert(50, critical=False), 10)])
    assert actions == Counter({"capped": 1, "rejected": 1, "applied": 1})


def test_same_alert_and_feedback_give_the_same_change():
    assert apply_guardrails(alert(88.48), -30) == apply_guardrails(alert(88.48), -30)


def test_guardrails_off_arm_applies_changes_raw():
    off = GuardrailPolicy(active=False)
    assert apply_guardrails(alert(99.89), -30, off).score_after == pytest.approx(69.89)
    assert apply_guardrails(alert(60, evidence="signature_override", critical=False), -30,
                            off).score_after == 30
    clamped = apply_guardrails(alert(10, critical=False), -30, off)
    assert (clamped.score_after, clamped.action, codes(clamped)) == (0, "capped",
                                                                     ["score_range_clamped"])


def test_policy_defaults_are_the_seeded_guardrail_settings():
    policy = GuardrailPolicy()
    for key in ("max_feedback_reduction", "max_feedback_increase", "critical_alert_floor",
                "infiltration_alert_floor", "critical_alert_threshold"):
        assert getattr(policy, key) == m.GUARDRAIL_DEFAULTS[key][0]


def test_feedback_effects_are_the_engine_values():
    assert {c: (e.requested_delta, e.forces_review) for c, e in FEEDBACK_EFFECTS.items()} == {
        "confirm_true_positive": (10, True), "mark_false_positive": (-30, False),
        "mark_expected_activity": (-15, False), "needs_investigation": (0, True),
        "escalate": (15, True)}
    assert set(FEEDBACK_EFFECTS) == set(CATEGORIES)


# --------------------------------------------------------------------------------------------
# The feedback service, against a real database
# --------------------------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "feedback.db")
    db.create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    """An analyst, a run, and one alert of each kind the demo meets."""
    user = db.insert(conn, m.User(username="analyst1", password_hash="$2b$12$synthetic",
                                  display_name="Analyst One", email="a1@example.test",
                                  role="security_analyst", created_at=T0))
    dataset = db.insert(conn, m.Dataset(name="demo", version="demo-20260911",
                                        source_file="data/processed/demo_sample.csv",
                                        total_records=5000, class_distribution={}))
    db.insert(conn, m.MlModel(version="xgb-8class-20260911", model_type="XGBoost",
                              model_file="models/xgboost_ids_model.json"))
    run = db.insert(conn, m.DetectionRun(
        dataset_id=dataset, model_version="xgb-8class-20260911", rule_set_version="s4b-1",
        fusion_weights={}, guardrail_config={}, status="completed", completed_at=T0))
    ids = {"user": user}
    for key, model in {
        "false_positive": alert(99.89, attack="Web Attack", dataset_id=dataset, run_id=run),
        "missed_attack": alert(36.94, evidence="none", critical=False, dataset_id=dataset,
                               run_id=run),
        "override": alert(60, evidence="signature_override", critical=False,
                          dataset_id=dataset, run_id=run),
        "moderate": alert(75, critical=False, dataset_id=dataset, run_id=run),
    }.items():
        ids[key] = db.insert(conn, model)
    conn.commit()
    return ids


def audit_types(conn) -> list[str]:
    return [row["event_type"] for row in conn.execute("SELECT event_type FROM audit_log ORDER BY id")]


def test_false_positive_on_a_critical_alert_is_held_at_the_floor(conn, seeded):
    result = submit_feedback(conn, alert_id=seeded["false_positive"], user_id=seeded["user"],
                             category="mark_false_positive", note="internal scanner", now=T0)
    assert (result.alert.detection_score, result.alert.combined_score) == (99.89, 70)
    event = result.feedback
    assert (event.original_score, event.requested_delta, event.actual_delta) == (99.89, -30, -29.89)
    assert event.guardrail_action == "capped" and "critical_alert_floor" in event.guardrail_reason
    assert result.alert.requires_review
    assert audit_types(conn) == ["FEEDBACK", "GUARDRAIL_INTERVENTION"]


def test_a_verdict_that_moves_the_score_moves_the_label_with_it(conn, seeded):
    """Severity is a function of the operational score, so feedback has to recompute it.

    Regression: severity was written once at detection and never revisited, so feedback moved the
    score out from under the label. The demo database shipped two alerts whose score the maximum
    reduction had pushed from 100 down to the floor of 70, still labelled "Critical" - a High-band
    score wearing a Critical label.
    """
    run, dataset = conn.execute("SELECT run_id, dataset_id FROM alerts WHERE id = ?",
                                (seeded["false_positive"],)).fetchone()
    # An Infiltration reaches Critical, so a drop to 70 crosses a real band edge.
    alert_id = db.insert(conn, alert(99.9, attack="Infiltration", dataset_id=dataset, run_id=run))
    conn.commit()
    assert severity_for(99.9, "Infiltration", CEILINGS) == "Critical"

    result = submit_feedback(conn, alert_id=alert_id, user_id=seeded["user"],
                             category="mark_false_positive", now=T0)

    assert (result.alert.detection_score, result.alert.combined_score) == (99.9, 75.0)
    # The Infiltration floor binds at 75 - above the critical floor of 70 - and 75 is the High band.
    assert result.alert.severity == "High", "the label has to come down with the score"
    assert result.alert.severity == severity_for(result.alert.combined_score,
                                                 result.alert.attack_category, CEILINGS)


def test_the_severity_label_matches_the_score_for_every_alert_after_verdicts(conn, seeded):
    """The invariant on the feedback path: whatever the score and class, the stored label is what
    they imply. A label written once at detection and never revisited cannot satisfy this."""
    judged = ("false_positive", "override", "moderate")
    for key in judged:
        submit_feedback(conn, alert_id=seeded[key], user_id=seeded["user"],
                        category="mark_false_positive", now=T0)

    for key in judged:
        row = conn.execute(
            "SELECT combined_score, severity, attack_category FROM alerts WHERE id = ?",
            (seeded[key],)).fetchone()
        assert row[1] == severity_for(row[0], row[2], CEILINGS), (
            f"{key}: score {row[0]} carries {row[1]}")


def test_a_new_alert_takes_what_its_family_already_learned(conn, seeded):
    """Ingest must apply a family's stored learning, or the learning never reaches new findings.

    Regression: ``_place`` ran on a zero adjustment, so a detection run over new flows started every
    alert at its raw detection score while the family's ``applied_adjustment`` sat unread in
    ``alert_families``. ``refresh_family``'s docstring claimed detection called it. It did not.
    """
    run, dataset = conn.execute("SELECT run_id, dataset_id FROM alerts WHERE id = ?",
                                (seeded["false_positive"],)).fetchone()
    flow = m.FlowRecord(src_ip="10.0.0.9", dst_ip="18.221.219.4", src_port=4444, dst_port=21,
                        protocol="tcp", duration=0.5, packets=6, bytes=3190, flow_features={},
                        source_record_id="AL-99999")
    fresh = alert(100.0, attack="Brute Force", dataset_id=dataset, run_id=run).model_copy(
        update={"requires_review": True})  # what fuse() sets for a confident model-only alert
    chart, policy, config = load_severity_chart(), GuardrailPolicy(), FusionConfig()

    # Nothing learned yet, so the alert keeps its own detection score - the old behaviour.
    before = _place(conn, fresh, flow, chart, policy, config)
    assert before.combined_score == fresh.detection_score == 100.0
    assert before.severity == "Medium"  # Brute Force tops out at Medium on the chart

    # The family learns a dismissal. A new alert of the same kind must arrive adjusted.
    key = family_key_of(fresh, flow)
    db.insert(conn, m.AlertFamily(
        family_key=key, attack_category="Brute Force", scheme="c1-m1", severity_version="v1",
        weight=0.5, feedback_counts={"mark_false_positive": 3},
        dominant_category="mark_false_positive", agreement_ratio=1.0, gate_open=True,
        gate_reason="3 verdicts, none dissenting", learned_adjustment=-30.0, learned_offset=0,
        applied_adjustment=-30.0, applied_offset=0))
    conn.commit()

    after = _place(conn, fresh, flow, chart, policy, config)
    assert after.detection_score == 100.0, "the immutable record must not move"
    assert after.combined_score == 70.0, "the family's learned adjustment must reach a new alert"
    assert after.severity == severity_for(70.0, "Brute Force", CEILINGS) == "Medium"


def test_a_confirmed_missed_attack_rises_and_is_reviewed(conn, seeded):
    result = submit_feedback(conn, alert_id=seeded["missed_attack"], user_id=seeded["user"],
                             category="confirm_true_positive", now=T0)
    assert result.alert.combined_score == pytest.approx(46.94)
    assert (result.feedback.guardrail_action, result.alert.requires_review) == ("applied", True)
    assert result.alert.evidence_class == "none"  # feedback never changes the evidence class
    assert audit_types(conn) == ["FEEDBACK"]


def test_verdicts_supersede_instead_of_stacking(conn, seeded):
    alert_id, user = seeded["moderate"], seeded["user"]
    first = submit_feedback(conn, alert_id=alert_id, user_id=user,
                            category="mark_false_positive", now=T0)
    second = submit_feedback(conn, alert_id=alert_id, user_id=user,
                             category="mark_false_positive", now=T0 + timedelta(seconds=1))
    assert first.alert.combined_score == second.alert.combined_score == 45  # 75 - 30, not 75 - 60
    assert second.feedback.amended_from_id == first.feedback.id
    third = submit_feedback(conn, alert_id=alert_id, user_id=user, category="escalate",
                            now=T0 + timedelta(seconds=2))
    assert third.alert.combined_score == 90  # the latest verdict is applied to the detection score
    assert current_feedback(conn, alert_id).id == third.feedback.id


def test_feedback_on_signature_override_is_rejected_and_routed(conn, seeded):
    result = submit_feedback(conn, alert_id=seeded["override"], user_id=seeded["user"],
                             category="mark_false_positive", now=T0)
    assert result.alert.combined_score == 60
    assert (result.feedback.guardrail_action, result.feedback.actual_delta) == ("rejected", 0)
    assert audit_types(conn) == ["FEEDBACK", "GUARDRAIL_REJECTION"]


def test_a_failed_submission_writes_nothing(conn, seeded):
    before = db.get(conn, m.Alert, seeded["false_positive"])
    with pytest.raises(sqlite3.IntegrityError):
        submit_feedback(conn, alert_id=seeded["false_positive"], user_id=999,
                        category="mark_false_positive", now=T0)
    assert db.get(conn, m.Alert, seeded["false_positive"]) == before
    assert conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0] == 0
    assert audit_types(conn) == []


def test_unknown_category_and_alert_are_refused(conn, seeded):
    with pytest.raises(ValueError, match="duplicate"):
        submit_feedback(conn, alert_id=seeded["moderate"], user_id=seeded["user"],
                        category="duplicate")
    with pytest.raises(LookupError):
        submit_feedback(conn, alert_id=12345, user_id=seeded["user"],
                        category="mark_false_positive")


def test_guardrails_off_arm_through_the_service(conn, seeded):
    result = submit_feedback(conn, alert_id=seeded["false_positive"], user_id=seeded["user"],
                             category="mark_false_positive",
                             policy=load_policy(conn, active=False), now=T0)
    assert result.alert.combined_score == pytest.approx(69.89)
    assert result.feedback.guardrail_action == "applied"


def test_administrator_settings_take_effect(conn, seeded):
    with conn:
        conn.execute("UPDATE guardrail_config SET config_value = 20 "
                     "WHERE config_key = 'max_feedback_reduction'")
    result = submit_feedback(conn, alert_id=seeded["moderate"], user_id=seeded["user"],
                             category="mark_false_positive", now=T0)
    assert (result.feedback.actual_delta, result.alert.combined_score) == (-20, 55)


def test_every_category_passes_the_contract_and_the_database(conn, seeded):
    for offset, category in enumerate(CATEGORIES):
        for key in ("false_positive", "missed_attack", "override", "moderate"):
            submit_feedback(conn, alert_id=seeded[key], user_id=seeded["user"],
                            category=category, now=T0 + timedelta(seconds=offset))
    assert conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0] == 4 * len(CATEGORIES)
    assert db.get(conn, m.Alert, seeded["false_positive"]).combined_score >= 70
