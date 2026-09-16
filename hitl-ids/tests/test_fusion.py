"""S6 - Complementary Evidence Fusion, re-specified (changelog v1.8).

Invariants I1, I2, I4 and I5 are checked over a grid of signature severities, model classes and
probabilities; I3 belongs to S7. The demo test runs the real rule engine and the real model output
over all 5,000 flows and checks the queue the database would serve.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pandas as pd
import pytest

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.feedback.service import FEEDBACK_EFFECTS
from packages.detection.fusion.cef import (
    CVSS_TO_SEVERITY,
    EVIDENCE_PRIORITY,
    SEVERITY_RANK,
    FusionConfig,
    ceilings_from_chart,
    fuse,
    queue_key,
    severity_for,
)
from packages.detection.guardrail.policy import apply_guardrails
from packages.detection.ranking.severity import band, load_severity_chart
from packages.detection.signature.engine import match_all
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_frame
from packages.detection.signature.rule_set import load_rule_set

HITL = Path(__file__).resolve().parents[1]
DEMO_SAMPLE = HITL / "data" / "processed" / "demo_sample.csv"
SHAP_PREDICTIONS = HITL / "data" / "processed" / "demo_ml_predictions_shap.json"
T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
SEVERITIES = list(get_args(m.RuleSeverity))


def prediction(predicted: str, confidence: float, *, benign: float | None = None,
               available: bool = True) -> m.MlPrediction:
    """A model output. Unless `benign` is given, all mass not on the predicted class is Benign."""
    if not available:
        return m.MlPrediction(
            record_id="AL-TEST", prediction_status="unavailable",
            failure_reason="invalid_numeric_feature_values",
            explanation=m.MlExplanation(status="unavailable", reason="prediction_unavailable",
                                        method="xgboost_native_treeshap_pred_contribs"))
    probabilities = {attack: 0.0 for attack in get_args(m.AttackClass)}
    probabilities[predicted] = confidence
    if predicted != "Benign":
        probabilities["Benign"] = 1 - confidence if benign is None else benign
    return m.MlPrediction(
        record_id="AL-TEST", prediction_status="available", predicted_class=predicted,
        model_confidence=confidence, class_probabilities=probabilities,
        explanation=m.MlExplanation(
            status="available", method="xgboost_native_treeshap_pred_contribs",
            explained_class=predicted,
            top_supporting_features=[m.ShapAttribution(
                feature_name="Dst Port", feature_value=22.0, shap_contribution=1.2,
                direction="supports_prediction")],
            additivity_check=m.AdditivityCheck(passed=True, difference=1e-6, tolerance=1e-4)))


def match(attack: str = "Brute Force", severity: str = "Medium",
          rule_id: str = "SIG-SSH-BRUTE-FORCE") -> m.SignatureMatch:
    return m.SignatureMatch(
        rule_id=rule_id, version="s4b-1", name=f"{rule_id} rule", attack_category=attack,
        severity=severity,
        matched_conditions=[
            m.MatchedCondition(feature="destinationPort", expected=22, observed=22),
            m.MatchedCondition(feature="flowPacketsPerSecond",
                               expected=m.RangeCondition(min=10.66689), observed=54.2),
        ])


UNAVAILABLE = prediction("Benign", 0.0, available=False)

# (case, matches, prediction, evidence class, score, requires_review, severity)
SPEC = [
    ("rule and model agree, confident", [match()], prediction("Brute Force", 0.99),
     "corroborated", 100.0, True, "Medium"),
    ("rule and model agree, unsure", [match()], prediction("Brute Force", 0.5),
     "corroborated", 65.0, False, "Medium"),
    ("model contradicts the rule's class", [match()], prediction("Port Scan", 0.99),
     "signature_override", 60.0, True, "Medium"),
    ("model calls the flow benign", [match()], prediction("Benign", 0.9),
     "signature_override", 60.0, True, "Medium"),
    ("model only, confident", [], prediction("DoS", 0.95), "ml_only", 95.0, True, "Medium"),
    ("model only, unsure", [], prediction("DoS", 0.7), "ml_only", 70.0, False, "Medium"),
    ("model only, a class that can reach Critical", [], prediction("Infiltration", 0.99),
     "ml_only", 99.0, True, "Critical"),
    ("nothing fired, a real low signal", [], prediction("Benign", 0.97), "none", 3.0, False,
     "Low"),
    ("nothing fired, at the noise floor", [], prediction("Benign", 0.9999), "none", 0.01, False,
     "Informational"),
    ("model unavailable", [], UNAVAILABLE, "none", 0.0, True, "Informational"),
    ("model unavailable, rule fired", [match()], UNAVAILABLE,
     "signature_override", 60.0, True, "Medium"),
]


def grid():
    """Every severity, model class and probability combination, with and without rules."""
    match_sets = [[]] + [[match(severity=severity)] for severity in SEVERITIES] + [
        [match("Brute Force", "Low"), match("Port Scan", "High", "SIG-SECOND")]]
    for matches, predicted, confidence in itertools.product(
            match_sets, ["Benign", "Brute Force", "Port Scan", "DoS"],
            [0.0, 0.3, 0.5, 0.79, 0.8, 0.99, 1.0]):
        yield matches, prediction(predicted, confidence)
    for matches in match_sets:
        yield matches, UNAVAILABLE


# --------------------------------------------------------------------------------------------
# The specification, case by case
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("case", "matches", "pred", "evidence", "score", "review", "severity"),
                         SPEC, ids=[row[0] for row in SPEC])
def test_specification(case, matches, pred, evidence, score, review, severity):
    decision = fuse(matches, pred)
    assert decision.evidence_class == evidence
    assert decision.combined_score == pytest.approx(score)
    assert decision.requires_review is review
    assert decision.severity == severity
    assert decision.evidence_priority == EVIDENCE_PRIORITY[evidence]
    alert = decision.to_alert(dataset_id=1, run_id=1, created_at=T0)  # contract-valid
    assert alert.detection_score == alert.combined_score == decision.combined_score


def test_malicious_probability_is_one_minus_benign():
    # Half the mass on DoS, 45% on other attack classes, 5% Benign: 95% malicious, not 50%.
    decision = fuse([], prediction("DoS", 0.5, benign=0.05))
    assert decision.ml_probability == pytest.approx(0.95)
    assert decision.combined_score == pytest.approx(95.0)


def test_override_takes_the_most_severe_rule_class():
    decision = fuse([match("Brute Force", "Low"), match("Port Scan", "High", "SIG-SECOND")],
                    prediction("DoS", 0.99))
    assert (decision.evidence_class, decision.attack_category) == ("signature_override",
                                                                   "Port Scan")
    assert decision.combined_score == pytest.approx(80.0)


def test_any_agreeing_rule_corroborates():
    decision = fuse([match("Brute Force", "Low"), match("Port Scan", "High", "SIG-SECOND")],
                    prediction("Port Scan", 0.99))
    assert (decision.evidence_class, decision.attack_category) == ("corroborated", "Port Scan")


# --------------------------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------------------------


def test_i1_a_signature_match_never_lowers_the_score_below_its_severity():
    scores = FusionConfig().severity_scores
    for matches, pred in grid():
        if matches:
            floor = max(scores[match.severity] for match in matches) * 100
            assert fuse(matches, pred).combined_score >= floor - 1e-9


def test_i2_signature_override_is_always_reviewed():
    decisions = [fuse(matches, pred) for matches, pred in grid()]
    overrides = [d for d in decisions if d.evidence_class == "signature_override"]
    assert overrides and all(d.requires_review for d in overrides)


def test_i3_feedback_cannot_decay_signature_override():
    """I3 is enforced by S7's guardrails; checked here on real fusion output so the list is whole."""
    overrides = [fuse(matches, pred) for matches, pred in grid()]
    overrides = [d for d in overrides if d.evidence_class == "signature_override"]
    assert overrides
    for decision in overrides:
        alert = decision.to_alert(dataset_id=1, run_id=1, created_at=T0)
        for category, effect in FEEDBACK_EFFECTS.items():
            outcome = apply_guardrails(alert, effect.requested_delta)
            assert outcome.score_after == alert.detection_score, category


def test_i4_fusion_is_a_pure_function_of_its_inputs():
    for matches, pred in grid():
        rebuilt = ([m.SignatureMatch.model_validate(x.model_dump()) for x in matches],
                   m.MlPrediction.model_validate(pred.model_dump()))
        assert fuse(matches, pred) == fuse(matches, pred) == fuse(*rebuilt)


def test_the_queue_band_no_longer_affects_position():
    """v1.31 retired I5, and with it the band key. ``queue_class`` still marks a Tier 2 candidate for
    escalation and orders the band tabs; it no longer decides where an alert sits.

    Measured before the change: the whole top 50 of the demo queue was Medium - Tier 2 candidates
    that are not severe, the opposite of what a Tier 1 analyst should open first.
    """
    critical = fuse([], prediction("Botnet", 0.9))              # ml_only, Critical
    medium = fuse([match()], prediction("Brute Force", 0.99))   # corroborated, 100, Medium
    assert queue_key(critical) == (-SEVERITY_RANK["Critical"], -90.0)
    assert queue_key(medium) == (-SEVERITY_RANK["Medium"], -100.0)
    assert queue_key(critical) < queue_key(medium), (
        "a Critical alert outranks a Medium one however high the Medium one scores")


def test_retiring_i5_cannot_hide_a_disputed_rule():
    """I5 said a signature_override outranks every ml_only alert. Dropping it is only safe because
    I2 keeps the override review-flagged, and the console keeps a "Rule only" band tab."""
    decisions = [fuse(matches, pred) for matches, pred in grid()]
    overrides = [d for d in decisions if d.evidence_class == "signature_override"]
    assert overrides, "the grid must produce signature_override cases"
    assert all(decision.requires_review for decision in overrides)


# --------------------------------------------------------------------------------------------
# Parameters and explanation
# --------------------------------------------------------------------------------------------


def test_parameters_change_behaviour_on_cases_that_occur():
    unsure = ([match()], prediction("Brute Force", 0.5))
    assert fuse(*unsure).combined_score == pytest.approx(65.0)
    assert fuse(*unsure, FusionConfig(agreement_bonus=0)).combined_score == pytest.approx(60.0)
    lowered = fuse(*unsure, FusionConfig(critical_threshold=60))
    assert (lowered.requires_review, lowered.is_critical, lowered.severity) == (True, True,
                                                                                "Medium")


def test_critical_threshold_is_the_guardrail_setting():
    assert FusionConfig().critical_threshold == m.GUARDRAIL_DEFAULTS["critical_alert_threshold"][0]


CEILINGS = ceilings_from_chart(load_severity_chart())


def test_the_attack_class_caps_the_severity():
    """Confidence says how sure the model is. The class says how much the finding is worth.

    Before the cap existed, 994 of the demo's 996 flagged alerts read "Critical" - a Port Scan and an
    Infiltration alike - because severity was a function of confidence alone, and the model is
    confident about everything it flags. The ceilings come from the attack-type severity chart, so
    this pins the chart rather than a second table. Each figure in the comment is ``severity`` in
    ``config/severity-chart.json``.
    """
    assert severity_for(100.0, "Port Scan", CEILINGS) == "Low"           # 3.0
    assert severity_for(100.0, "Brute Force", CEILINGS) == "Medium"      # 5.0
    assert severity_for(100.0, "DoS", CEILINGS) == "Medium"              # 6.5
    assert severity_for(100.0, "DDoS", CEILINGS) == "High"               # 7.5
    assert severity_for(100.0, "Web Attack", CEILINGS) == "High"         # 8.0
    assert severity_for(100.0, "Botnet", CEILINGS) == "Critical"         # 9.0
    assert severity_for(100.0, "Infiltration", CEILINGS) == "Critical"   # 9.5


def test_the_ceilings_are_the_severity_chart_and_nothing_else():
    """One source of truth. A chart edited for Tier 2 candidacy moves the ceilings with it.

    Regression: a hand-written ceiling table was added first, and it disagreed with the chart on two
    classes - Port Scan (table: Medium, chart: Low) and DoS (table: High, chart: Medium). Both are
    asserted below, so a second table cannot creep back in unnoticed.
    """
    chart = load_severity_chart()
    ceilings = ceilings_from_chart(chart)
    assert set(ceilings) == set(get_args(m.AttackClass))
    for model_class, ceiling in ceilings.items():
        assert ceiling == CVSS_TO_SEVERITY[band(chart.severity(model_class))]
    assert ceilings["Port Scan"] == "Low"
    assert ceilings["DoS"] == "Medium"


def test_the_cap_only_lowers_and_never_raises():
    """A ceiling that could raise a severity would let a quiet class outrank a loud one."""
    for predicted in (*get_args(m.AttackClass), None, "Not A Class"):
        for score in (0.0, 0.5, 1.0, 39.99, 40.0, 69.99, 70.0, 79.99, 80.0, 100.0):
            capped = severity_for(score, predicted, CEILINGS)
            uncapped = severity_for(score, None, CEILINGS)
            assert SEVERITY_RANK[capped] <= SEVERITY_RANK[uncapped], (
                f"{predicted} at score {score} gave {capped}, above the uncapped {uncapped}")


def test_severity_is_the_band_the_score_falls_in():
    """The bands at their boundaries, read through DDoS - a class the chart tops out at High."""
    assert severity_for(0.0, "DDoS", CEILINGS) == "Informational"
    assert severity_for(0.99, "DDoS", CEILINGS) == "Informational"
    assert severity_for(1.0, "DDoS", CEILINGS) == "Low"
    assert severity_for(39.99, "DDoS", CEILINGS) == "Low"
    assert severity_for(40.0, "DDoS", CEILINGS) == "Medium"
    assert severity_for(69.99, "DDoS", CEILINGS) == "Medium"
    assert severity_for(70.0, "DDoS", CEILINGS) == "High"
    assert severity_for(79.99, "DDoS", CEILINGS) == "High"
    assert severity_for(100.0, "DDoS", CEILINGS) == "High"   # the ceiling, not the band
    assert severity_for(80.0, "Botnet", CEILINGS) == "Critical"


def test_config_snapshot_replays():
    config = FusionConfig(agreement_bonus=7, critical_threshold=85)
    snapshot = json.loads(json.dumps(config.snapshot()))
    assert snapshot["evidence_priority"] == EVIDENCE_PRIORITY
    assert FusionConfig.from_snapshot(snapshot) == config
    with pytest.raises(ValueError, match="scheme"):
        FusionConfig.from_snapshot({**snapshot, "scheme": "weighted-sum"})


def test_config_must_score_every_severity():
    with pytest.raises(ValueError, match="severity_scores"):
        FusionConfig(severity_scores={"Low": 0.4})


def test_explanation_gives_the_checkable_reason_and_the_model_view():
    disputed = fuse([match()], prediction("Port Scan", 0.99)).explanation
    assert "does not confirm" in disputed
    assert "SIG-SSH-BRUTE-FORCE" in disputed and "(observed 54.2)" in disputed
    assert "Flow packets per second is at least 10.667" in disputed
    assert "Port Scan" in disputed and "Dst Port" in disputed
    assert "no rule gives a checkable reason" in fuse([], prediction("DoS", 0.95)).explanation.lower()
    assert "unavailable" in fuse([], UNAVAILABLE).explanation


# --------------------------------------------------------------------------------------------
# The demo sample, end to end
# --------------------------------------------------------------------------------------------


@pytest.mark.skipif(not (DEMO_SAMPLE.exists() and SHAP_PREDICTIONS.exists()),
                    reason="needs demo_sample.csv and scripts/run_ml_inference.py output")
def test_demo_flows_fuse_as_changelog_v1_3_reports(tmp_path):
    frame = pd.read_csv(DEMO_SAMPLE, usecols=["alert_id", "attack_class", *OBSERVABLE_FIELDS],
                        low_memory=False)
    view = project_frame(frame).drop(columns="id").to_dict("records")
    predictions = {record_id: m.MlPrediction.model_validate(record) for record_id, record in
                   json.loads(SHAP_PREDICTIONS.read_text("utf-8")).items()}
    rules = [rule for rule in load_rule_set() if rule.enabled]
    decisions = [fuse(match_all(record, rules), predictions[alert_id])
                 for record, alert_id in zip(view, frame["alert_id"], strict=True)]
    truth = frame["attack_class"].tolist()

    counts = Counter(decision.evidence_class for decision in decisions)
    flagged = sum(1 for p in predictions.values() if p.predicted_class != "Benign")
    assert sum(counts.values()) == 5000
    assert counts["corroborated"] == 200  # v1.3: 200 flows caught by both detectors
    assert counts["signature_override"] == 0  # no rule is contradicted on the demo sample
    assert counts["ml_only"] == flagged - counts["corroborated"]
    assert all(true_class != "Benign" for decision, true_class in zip(decisions, truth)
               if decision.evidence_class == "corroborated")

    # The queue the database serves is the queue queue_key describes.
    conn = db.connect(tmp_path / "queue.db")
    db.create_schema(conn)
    dataset = db.insert(conn, m.Dataset(
        name="demo", version="demo-20260911", source_file="data/processed/demo_sample.csv",
        total_records=5000, class_distribution={}))
    db.insert(conn, m.MlModel(version="xgb-8class-20260911", model_type="XGBoost",
                              model_file="models/xgboost_ids_model.json"))
    run = db.insert(conn, m.DetectionRun(
        dataset_id=dataset, model_version="xgb-8class-20260911", rule_set_version="s4b-1",
        fusion_weights=FusionConfig().snapshot(), guardrail_config={}, status="completed",
        completed_at=T0))
    ids = [db.insert(conn, decision.to_alert(dataset_id=dataset, run_id=run, created_at=T0))
           for decision in decisions]
    served = [row["id"] for row in
              conn.execute(f"SELECT id FROM alerts ORDER BY {db.QUEUE_ORDER_BY}")]
    expected = [ids[index] for index in
                sorted(range(len(decisions)), key=lambda index: queue_key(decisions[index]))]
    conn.close()
    assert served == expected
