"""S7b - similar-alert learning: a verdict on one alert moves the alerts like it, inside the
guardrails.

The design was chosen by experiment (notebooks 05-06). These tests pin that production *is* that
design - the experiment's own C1 + M1 functions behind the collaborator's gate, counted by
category - and that the safety claims hold on the family path as they do on S7a's direct path.
"""

from __future__ import annotations

import itertools
import json
import random
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter
from packages.detection.feedback.learning import (
    LearningPolicy,
    detection_placement,
    family_key,
    family_key_of,
    gate,
    learn,
    member_placement,
    verdict_queue_class,
)
from packages.detection.feedback.service import (
    load_learning_policy,
    load_policy,
    refresh_family,
    submit_feedback,
)
from packages.detection.fusion.cef import EVIDENCE_PRIORITY
from packages.detection.guardrail.policy import GuardrailPolicy
from packages.detection.ranking import experiment as E
from packages.detection.ranking.formulas import (
    QUEUE_CLASSES,
    FamilyState,
    RankingParams,
    apply_verdict,
    effective,
)
from packages.detection.ranking.severity import load_severity_chart

T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
CHART = load_severity_chart()
ON, OFF = GuardrailPolicy(), GuardrailPolicy(active=False)
GATE = LearningPolicy()
CATEGORIES = list(get_args(m.FeedbackCategory))
WEB = family_key("Web Attack", 80, "TCP", None, "172.31.69.28", "ml_only")
SSH = family_key("Brute Force", 22, "TCP", "SIG-SSH-BRUTE-FORCE", "172.31.69.25", "corroborated")


def rule(attack: str) -> m.SignatureMatch:
    return m.SignatureMatch(
        rule_id="SIG-SSH-BRUTE-FORCE", version="s4b-1", name="SSH rule", attack_category=attack,
        severity="Medium", matched_conditions=[m.MatchedCondition(
            feature="destinationPort", expected=22, observed=22)])


def alert(score: float, *, evidence: str = "ml_only", attack: str = "Web Attack",
          critical: bool | None = None, family: str | None = WEB) -> m.Alert:
    """An alert as fusion (S6) produces it; ``critical`` defaults to S6's rule, score >= 80."""
    critical = score >= 80 if critical is None else critical
    predicted = {"corroborated": attack, "ml_only": attack}.get(evidence, "Benign")
    return m.Alert(
        dataset_id=1, run_id=1, detection_score=score, combined_score=score,
        severity="Critical" if critical else "Medium", confidence=0.9,
        signature_rules=[rule(attack)] if evidence in m.SIGNATURE_EVIDENCE else None,
        ml_predicted_class=predicted, attack_category=None if evidence == "none" else attack,
        explanation="test alert", is_critical=critical, evidence_class=evidence,
        evidence_priority=EVIDENCE_PRIORITY[evidence], family_key=family,
        created_at=T0, updated_at=T0)


# --------------------------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------------------------


def test_queue_bands_are_the_experiments():
    assert tuple(m.QUEUE_PRIORITY) == QUEUE_CLASSES


def test_family_key_is_canonical_and_groups_as_the_experiment_did():
    assert WEB == '["Web Attack",80,"tcp","-"]'
    # protocol 6 is TCP, and a port may arrive as text - canonicalised as similarity-engine.js does
    assert family_key("Web Attack", "80", 6, "-", "10.0.0.9", "ml_only") == WEB
    # an unflagged flow keeps its destination, so one verdict cannot spread across a port
    assert family_key("Benign", 53, 17, None, "172.31.0.2", "none") == (
        '["Benign",53,"udp","-","172.31.0.2"]')
    for args in [("Web Attack", 80, "TCP", "-", "10.0.0.5", "ml_only"),
                 ("Benign", 53, "UDP", "-", "10.0.0.2", "none"),
                 ("Brute Force", 22, "TCP", "SIG-SSH-BRUTE-FORCE", "10.0.0.7", "corroborated")]:
        coarse = list(E.family_key(*args))
        coarse[2] = coarse[2].lower()
        assert json.loads(family_key(*args)) == coarse


def test_family_key_of_a_stored_alert_and_its_flow():
    def flow(port: int, protocol: str, dst_ip: str) -> m.FlowRecord:
        return m.FlowRecord(src_ip="172.31.69.25", dst_ip=dst_ip, src_port=51514, dst_port=port,
                            protocol=protocol, duration=0.4, packets=22, bytes=3190,
                            flow_features={}, source_record_id="AL-00001")

    corroborated = alert(95, evidence="corroborated", attack="Brute Force")
    assert family_key_of(corroborated, flow(22, "6", "172.31.69.25")) == SSH
    unflagged = alert(0.02, evidence="none", critical=False)
    assert family_key_of(unflagged, flow(53, "UDP", "172.31.0.2")) == (
        '["Benign",53,"udp","-","172.31.0.2"]')


# --------------------------------------------------------------------------------------------
# The gate (Q30)
# --------------------------------------------------------------------------------------------


def test_gate_needs_three_learning_verdicts():
    assert "cold start" in gate({}, GATE).reason
    assert not gate({"mark_false_positive": 2}, GATE).open
    assert gate({"mark_false_positive": 3}, GATE).open


def test_gate_refuses_ties_and_uses_the_collaborators_rounded_ratio():
    tie = gate({"mark_false_positive": 2, "confirm_true_positive": 2}, GATE)
    assert (tie.open, tie.dominant, tie.agreement) == (False, None, 0.5)
    two_of_three = gate({"confirm_true_positive": 2, "mark_false_positive": 1}, GATE)
    assert (two_of_three.open, two_of_three.agreement) == (False, 0.6667)  # < 0.67, as in the JS
    assert gate({"confirm_true_positive": 3, "mark_false_positive": 1}, GATE).open


def test_gate_counts_by_category_not_by_direction():
    # A false positive and expected activity point the same way but are different verdicts; the
    # collaborator's engine counts them apart, and so does S7b. The experiment counted directions,
    # under which these three dismissals agree.
    assert not gate({"mark_false_positive": 2, "mark_expected_activity": 1}, GATE).open
    by_direction = FamilyState(adjustment=-12.0, class_offset=1, dismissals=3)
    assert effective(by_direction, gated=True) == (-12.0, 1)


def test_expected_activity_does_not_propagate_unless_enabled():
    assert not gate({"mark_expected_activity": 9}, GATE).open
    enabled = LearningPolicy(expected_activity_propagates=True)
    assert not gate({"mark_expected_activity": 4}, enabled).open  # needs 5
    assert not gate({"mark_expected_activity": 9, "mark_false_positive": 2}, enabled).open  # 0.82
    assert gate({"mark_expected_activity": 5}, enabled).open


# --------------------------------------------------------------------------------------------
# Learning (Q29: formula C1, movement M1)
# --------------------------------------------------------------------------------------------


def test_escalate_counts_as_a_confirmation_and_needs_investigation_teaches_nothing():
    result = learn(["escalate", "confirm_true_positive", "needs_investigation", "escalate"],
                   0.8, ON, GATE)
    assert result.counts == {"confirm_true_positive": 3} and result.gate.open
    assert (result.applied_adjustment, result.applied_offset) == (20, -3)  # 3 x 24, capped at +20
    assert learn(["needs_investigation"] * 5, 0.8, ON, GATE).counts == {}


def test_three_correct_dismissals_reproduce_notebook_06s_constructed_case():
    result = learn(["mark_false_positive"] * 3, CHART.weight("Web Attack"), ON, GATE)
    assert (result.learned_adjustment, result.learned_offset) == (-18, 1)  # 3 x -30(1 - 0.8)
    assert (result.applied_adjustment, result.applied_offset) == (-18, 1)
    before = detection_placement(alert(100.0), CHART)
    after = member_placement(alert(100.0), result.applied_adjustment, result.applied_offset,
                             CHART, ON)
    # notebook 06, F4: (class 0, score 100) -> (class 3, score 82)
    assert (before.queue_priority, before.score) == (0, 100.0)
    assert (after.queue_priority, after.score) == (3, 82.0)


def test_learning_is_the_experiments_gated_c1_m1_where_categories_are_directions():
    # With only confirmations and false positives a category is a direction, so S7b must give
    # exactly what the experiment's gated C1 + M1 arm computed from the same verdicts.
    rng = random.Random(20260912)
    params = RankingParams(formula="C1", movement="M1")
    for _ in range(500):
        verdicts = [rng.choice(["confirm_true_positive", "mark_false_positive"])
                    for _ in range(rng.randint(0, 12))]
        weight = rng.choice([0.0, 0.3, 0.5, 0.65, 0.75, 0.8, 0.9, 0.95])
        state = FamilyState()
        for verdict in verdicts:
            apply_verdict(state, params, verdict, 50.0, weight)
        adjustment, offset = effective(state, gated=True)
        result = learn(verdicts, weight, ON, GATE)
        assert result.applied_adjustment == pytest.approx(adjustment, abs=1e-4)
        assert result.applied_offset == offset


def test_learning_against_the_majority_is_withheld():
    # At severity 9.5, C1 weighs a confirmation (+28.5) nineteen times a dismissal (-1.5), so a
    # family the analysts mostly dismiss can still have learned a rise. None of it gets through.
    result = learn(["confirm_true_positive"] * 3 + ["mark_false_positive"] * 7,
                   CHART.weight("Infiltration"), ON, GATE)
    assert (result.gate.open, result.gate.dominant) == (True, "mark_false_positive")
    assert result.learned_adjustment == pytest.approx(9.5)
    assert result.applied_adjustment == 0


# --------------------------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------------------------


def test_no_family_learning_breaks_a_floor():
    for score, adjustment, offset in itertools.product(
            [80, 85, 90, 99.89, 100], [-30, -25, -18, -6], [0, 1, 2]):
        assert member_placement(alert(score), adjustment, offset, CHART, ON).score >= 70
    assert member_placement(alert(90, attack="Infiltration"), -30, 0, CHART, ON).score == 75
    assert member_placement(alert(90), -30, 0, CHART, OFF).score == 60  # guardrails off: raw


def test_signature_override_members_are_frozen():
    disputed = alert(60, evidence="signature_override", attack="Brute Force", critical=False)
    place = member_placement(disputed, -30, 2, CHART, ON)
    assert (place.score, place.queue_class, place.outcome) == (60, "signature_override", None)
    for category in CATEGORIES:
        assert verdict_queue_class(disputed, category, 60, CHART, ON) == "signature_override"


def test_tier_loss_protection_keeps_a_flagged_member_out_of_the_bottom_band():
    assert member_placement(alert(60, critical=False), 0, 3, CHART, ON).queue_class == "ml_only"
    assert member_placement(alert(60, critical=False), 0, 3, CHART, OFF).queue_class == "none"


def test_a_direct_verdict_places_its_own_alert():
    missed = alert(36.94, evidence="none", critical=False, family=None)  # AL-03086
    assert verdict_queue_class(missed, "confirm_true_positive", 46.94, CHART, ON) == "ml_only"
    assert verdict_queue_class(missed, "escalate", 51.94, CHART, ON) == "tier2_candidate"  # E2
    severe = alert(75, critical=False)  # Web Attack, severity 8.0
    assert verdict_queue_class(severe, "confirm_true_positive", 85, CHART, ON) == (
        "tier2_candidate")  # E2
    # Port Scan (3.0) is below E2's 7.0, so a confirmation promotes one band: from ml_only to the
    # band Q24 names signature_override. Bands are positions; the evidence class is unchanged.
    mild = alert(75, attack="Port Scan", critical=False)
    assert verdict_queue_class(mild, "confirm_true_positive", 85, CHART, ON) == (
        "signature_override")
    corroborated = alert(95, evidence="corroborated", attack="Brute Force")  # E1
    assert detection_placement(corroborated, CHART).queue_class == "tier2_candidate"
    # a dismissal withdraws Tier 2 candidacy - the Tier 1 decision - but moves it no lower
    assert verdict_queue_class(corroborated, "mark_false_positive", 70, CHART, ON) == (
        "corroborated")
    assert verdict_queue_class(corroborated, "needs_investigation", 95, CHART, ON) == (
        "tier2_candidate")


# --------------------------------------------------------------------------------------------
# The service, against a real database
# --------------------------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "learning.db")
    db.create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def base(conn):
    """An analyst, a dataset, a model and a completed run."""
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
    conn.commit()
    return {"user": user, "dataset": dataset, "run": run}


def store(conn, base, model: m.Alert) -> int:
    """Insert an alert as detection (S9) will: at its detection-time placement."""
    place = detection_placement(model, CHART)
    return db.insert(conn, m.Alert.model_validate({
        **model.model_dump(), "dataset_id": base["dataset"], "run_id": base["run"],
        "queue_class": place.queue_class, "queue_priority": place.queue_priority,
        "requires_review": place.requires_review}))


@pytest.fixture
def web(conn, base):
    """Six Web Attack alerts in one family, as the model scored them: five in the Tier 2 band (E3:
    score >= 90 on a severity-8.0 type) and one Critical alert at 85 in the ml_only band."""
    ids = [store(conn, base, alert(score)) for score in (100.0, 100.0, 99.89, 99.5, 100.0, 85.0)]
    conn.commit()
    return ids


def verdict(conn, base, alert_id: int, category: str, second: int, **kwargs):
    return submit_feedback(conn, alert_id=alert_id, user_id=base["user"], category=category,
                           chart=CHART, now=T0 + timedelta(seconds=second), **kwargs)


def get(conn, alert_id: int) -> m.Alert:
    return db.get(conn, m.Alert, alert_id)


def placed(conn, alert_id: int) -> tuple[float, str]:
    current = get(conn, alert_id)
    return current.combined_score, current.queue_class


def test_the_third_agreeing_verdict_opens_the_gate_and_moves_the_family(conn, base, web):
    a1, a2, a3, a4, a5, a6 = web
    for second, alert_id in enumerate((a1, a2), 1):
        result = verdict(conn, base, alert_id, "mark_false_positive", second)
        assert not result.learning.after.gate_open
        assert placed(conn, a4) == (99.5, "tier2_candidate")  # untouched while the gate is shut
    result = verdict(conn, base, a3, "mark_false_positive", 3)
    family = result.learning.after
    assert (family.gate_open, family.feedback_counts) == (True, {"mark_false_positive": 3})
    assert (family.applied_adjustment, family.applied_offset) == (-18, 1)
    # out of the Tier 2 band; the Critical 85 is held at the floor rather than dropped to 67
    assert [placed(conn, i) for i in (a4, a5, a6)] == [
        (81.5, "ml_only"), (82.0, "ml_only"), (70.0, "ml_only")]
    assert get(conn, a6).detection_score == 85 and get(conn, a6).requires_review
    assert result.learning.members_moved == 3
    assert result.learning.guardrail_interventions == {"critical_alert_floor": 1}


def test_an_amended_verdict_counts_once_and_a_shut_gate_restores_the_family(conn, base, web):
    a1, a2, a3, a4, *_ = web
    for second, alert_id in enumerate((a1, a2, a3), 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    assert placed(conn, a4) == (81.5, "ml_only")
    result = verdict(conn, base, a3, "confirm_true_positive", 4)  # the analyst changes their mind
    family = result.learning.after
    assert family.feedback_counts == {"mark_false_positive": 2, "confirm_true_positive": 1}
    assert (family.gate_open, family.agreement_ratio) == (False, 0.6667)
    assert (*placed(conn, a4), get(conn, a4).requires_review) == (99.5, "tier2_candidate", True)


def test_a_members_own_verdict_takes_priority_over_its_familys(conn, base, web):
    for second, alert_id in enumerate(web[:3], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    assert placed(conn, web[3]) == (81.5, "ml_only")
    result = verdict(conn, base, web[3], "needs_investigation", 4)
    assert (result.alert.combined_score, result.alert.queue_class) == (99.5, "tier2_candidate")
    assert result.learning.after.feedback_counts == {"mark_false_positive": 3}  # taught nothing
    assert (result.learning.changed, result.learning.members_moved) == (False, 0)


def test_a_failure_after_the_family_moved_rolls_everything_back(conn, base, web, monkeypatch):
    for second, alert_id in enumerate(web[:2], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    tables = ("alerts", "alert_families", "feedback_events", "audit_log")

    def snapshot():
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                for table in tables}

    before = snapshot()

    def unavailable(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(AuditWriter, "similar_alert_learning", unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        verdict(conn, base, web[2], "mark_false_positive", 3)  # would open the gate
    assert snapshot() == before


def test_refreshing_a_family_again_changes_nothing(conn, base, web):
    for second, alert_id in enumerate(web[:3], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    with conn:
        again = refresh_family(conn, WEB, policy=ON, learning=GATE, chart=CHART,
                               now=T0 + timedelta(hours=1))
    assert (again.changed, again.members_moved) == (False, 0)
    assert again.after.updated_at == T0 + timedelta(seconds=3)


def test_an_alert_arriving_later_takes_its_familys_learning(conn, base, web):
    for second, alert_id in enumerate(web[:3], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    newcomer = store(conn, base, alert(100.0))
    with conn:
        refresh = refresh_family(conn, WEB, policy=ON, learning=GATE, chart=CHART,
                                 now=T0 + timedelta(minutes=1))
    assert (refresh.changed, refresh.members_moved) == (False, 1)
    assert placed(conn, newcomer) == (82.0, "ml_only")


def test_administrator_gate_settings_take_effect(conn, base, web):
    with conn:
        conn.execute("UPDATE guardrail_config SET config_value = 2 "
                     "WHERE config_key = 'aggregation_min_feedback_count'")
    assert load_learning_policy(conn).min_feedback_count == 2
    verdict(conn, base, web[0], "mark_false_positive", 1)
    assert verdict(conn, base, web[1], "mark_false_positive", 2).learning.after.gate_open
    assert placed(conn, web[3]) == (87.5, "ml_only")  # 99.5 - 12, one band down


def test_signature_override_neither_teaches_nor_learns(conn, base):
    confirmed = [store(conn, base, alert(95.0, evidence="corroborated", attack="Brute Force",
                                         family=SSH)) for _ in range(4)]
    disputed = [store(conn, base, alert(60.0, evidence="signature_override", attack="Brute Force",
                                        critical=False, family=SSH)) for _ in range(2)]
    conn.commit()
    result = verdict(conn, base, disputed[0], "mark_false_positive", 1)
    assert result.learning is None and result.alert.combined_score == 60  # routed, not learned
    for second, alert_id in enumerate(confirmed[:3], 2):
        result = verdict(conn, base, alert_id, "mark_false_positive", second)
    family = result.learning.after
    assert family.feedback_counts == {"mark_false_positive": 3}  # the disputed verdict is absent
    assert (family.gate_open, family.applied_adjustment, family.applied_offset) == (True, -30, 1)
    assert placed(conn, disputed[1]) == (60, "signature_override")  # frozen (I3)
    # 95 - 30 is held at the Critical floor; E1's Tier 2 band drops one band to corroborated
    assert placed(conn, confirmed[3]) == (70.0, "corroborated")


def test_no_sequence_of_verdicts_breaks_a_floor_or_touches_a_detection_score(conn, base, web):
    rng = random.Random(20260912)
    detection = {alert_id: get(conn, alert_id).detection_score for alert_id in web}
    for step in range(60):
        verdict(conn, base, rng.choice(web), rng.choice(CATEGORIES), step)
        for alert_id in web:
            current = get(conn, alert_id)
            assert current.detection_score == detection[alert_id]
            assert current.combined_score >= 70  # every member was Critical at detection
    with conn:  # what is stored is exactly what the verdicts imply
        again = refresh_family(conn, WEB, policy=ON, learning=GATE, chart=CHART,
                               now=T0 + timedelta(hours=1))
    assert (again.changed, again.members_moved) == (False, 0)


def test_guardrails_off_applies_the_familys_learning_raw(conn, base, web):
    off = load_policy(conn, active=False)
    for second, alert_id in enumerate(web[:3], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second, policy=off)
    # 85 - 18 = 67: no Critical floor, and no tier-loss protection to keep it off the bottom band
    assert placed(conn, web[5]) == (67.0, "none")


def test_every_change_to_a_familys_learning_is_audited(conn, base, web):
    for second, alert_id in enumerate(web[:3], 1):
        verdict(conn, base, alert_id, "mark_false_positive", second)
    verdict(conn, base, web[3], "needs_investigation", 4)  # changes nothing the family learned
    entries = AuditWriter(conn).query(event_types=["SIMILAR_ALERT_LEARNING"])
    assert len(entries) == 3
    first, last = entries[0], entries[-1]
    assert first.details["before"] is None
    assert (last.actor_id, last.alert_id, last.details["family_key"]) == (
        base["user"], web[2], WEB)
    assert (last.details["before"]["gate_open"], last.details["after"]["gate_open"]) == (
        False, True)
    assert last.details["members_moved"] == 3
    assert last.details["guardrail_interventions"] == {"critical_alert_floor": 1}


def test_an_alert_outside_any_family_teaches_nothing(conn, base):
    alone = store(conn, base, alert(90.0, family=None))
    conn.commit()
    assert verdict(conn, base, alone, "mark_false_positive", 1).learning is None
    assert conn.execute("SELECT COUNT(*) FROM alert_families").fetchone()[0] == 0
