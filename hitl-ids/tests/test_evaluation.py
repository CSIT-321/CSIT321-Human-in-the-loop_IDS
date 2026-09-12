"""S15 - the three-arm evaluation harness.

What these tests pin, in the plan's own words: re-running a scenario reproduces identical metrics
(NFR-05), the pre-registered sequence is byte-identical across runs, and run C's suppression count
is recorded **as measured**.

That last one shapes the whole file. No test here asserts that feedback improved anything, that the
guardrails bound, or that arm C suppressed a critical alert - asserting any of those would rebuild
the corrupt v0.2 exit criterion in test form, where the suite passes only when the experiment
produces the wanted answer. The tests check that the machinery is honest: that the arms differ in
exactly two variables, that detection is untouched, that learning stays inside its families, and
that whatever the numbers are, they are recorded and reproducible.

The fixture is a synthetic capture, not the demo sample: the suite must pass on a fresh checkout,
where ``data/demo.db`` does not exist.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import open_database, run_detection
from packages.detection.pipeline.source import CsvReplaySource
from packages.detection.ranking.severity import load_severity_chart
from packages.evaluation import metrics as mx
from packages.evaluation.harness import ARMS, evaluate, export, guardrail_pass, run_arm
from packages.evaluation.scenario import (
    Preregistration,
    build_sequence,
    category_for,
    ensure_evaluator,
    pinned_run_config,
    sequence_digest,
)
from packages.evaluation.truth import GroundTruth

from conftest import FTP_RULE, ROWS  # the shared synthetic capture

#: The gate needs three verdicts in a family, so a test family needs more than three members
#: for any of them to remain untouched. These numbers are the tests' own, not the rule's defaults.
TEST_RULE = Preregistration(size=6, max_per_family=3, min_family_size=4)

T0 = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


@pytest.fixture
def truth_file(tmp_path) -> Path:
    path = tmp_path / "ground_truth.json"
    path.write_text(json.dumps({
        str(entry["alert_id"]): {
            "attackType": entry["attack_class"], "isAttempted": False,
            "groundTruth": "benign" if entry["attack_class"] == "Benign" else "malicious",
        } for entry in ROWS}), encoding="utf-8")
    return path


@pytest.fixture
def truth(truth_file) -> GroundTruth:
    return GroundTruth.load(truth_file)


@pytest.fixture
def baseline(tmp_path, sample, predictions) -> Path:
    """A populated detection database - the thing all three arms are copies of."""
    path = tmp_path / "demo.db"
    conn = open_database(str(path))
    try:
        dataset_id = store.register_dataset(
            conn, name="synthetic capture", version="test-1", source_file="sample.csv",
            total_records=len(ROWS),
            class_distribution={"Benign": 7, "Brute Force": 8, "Botnet": 6}, now=T0)
        store.register_model(conn, version="xgb-8class-20260911",
                             model_file="models/xgboost_ids_model.json", now=T0)
        conn.commit()
        run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions),
                      dataset_id=dataset_id, rules=[FTP_RULE], seed=20260911, now=T0)
    finally:
        conn.close()
    return path


@pytest.fixture
def evaluation(baseline, truth, tmp_path):
    return evaluate(baseline, truth=truth, rule=TEST_RULE, workdir=tmp_path / "arms",
                    run_id="TEST")


# --------------------------------------------------------------------------------------------
# Ground truth: the one join, and its refusals
# --------------------------------------------------------------------------------------------

def test_ground_truth_reads_the_capture(truth):
    assert len(truth) == len(ROWS)
    assert truth.of("AL-0001").attack_type == "Brute Force"
    assert truth.malicious("AL-0001") and not truth.malicious("AL-0016")


def test_ground_truth_refuses_a_flow_it_cannot_check(truth):
    """An unknown record must raise, never default to benign: a silent default would count every
    unmatched alert as a false positive and quietly deflate precision."""
    with pytest.raises(LookupError, match="no ground truth"):
        truth.of("AL-9999")


def test_ground_truth_refuses_to_disagree_with_itself(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"AL-0001": {"attackType": "Botnet", "isAttempted": False,
                                            "groundTruth": "benign"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees with itself"):
        GroundTruth.load(path)


# --------------------------------------------------------------------------------------------
# Pre-registration (task 1)
# --------------------------------------------------------------------------------------------

def test_the_sequence_is_byte_identical_across_builds(baseline, truth):
    conn = db.connect(baseline)
    try:
        first = build_sequence(conn, truth, rule=TEST_RULE)
        second = build_sequence(conn, truth, rule=TEST_RULE)
    finally:
        conn.close()
    assert first == second
    assert sequence_digest(first) == sequence_digest(second)


def test_the_sequence_honours_its_own_limits(baseline, truth):
    conn = db.connect(baseline)
    try:
        sequence = build_sequence(conn, truth, rule=TEST_RULE)
        sizes = {row["family_key"]: row["n"] for row in conn.execute(
            "SELECT family_key, COUNT(*) AS n FROM alerts WHERE family_key IS NOT NULL "
            "GROUP BY family_key")}
    finally:
        conn.close()
    assert len(sequence) <= TEST_RULE.size
    per_family: dict[str, int] = {}
    for entry in sequence:
        per_family[entry["family_key"]] = per_family.get(entry["family_key"], 0) + 1
    assert all(count <= TEST_RULE.max_per_family for count in per_family.values())
    assert all(sizes[family] >= TEST_RULE.min_family_size for family in per_family)
    assert all(entry["queue_class"] != "none" for entry in sequence)


def test_every_judged_family_keeps_untouched_members(baseline, truth):
    """The subset rule is what makes an effect on *similar* alerts measurable at all."""
    conn = db.connect(baseline)
    try:
        sequence = build_sequence(conn, truth, rule=TEST_RULE)
        for family in {entry["family_key"] for entry in sequence}:
            members = conn.execute("SELECT COUNT(*) AS n FROM alerts WHERE family_key = ?",
                                   (family,)).fetchone()["n"]
            judged = sum(1 for entry in sequence if entry["family_key"] == family)
            assert members > judged, f"{family} was judged in full; nothing is left to measure"
    finally:
        conn.close()


def test_the_category_comes_from_ground_truth_not_from_the_detector():
    chart = load_severity_chart()
    assert category_for("Benign", chart, 7.0) == "mark_false_positive"
    assert category_for("Botnet", chart, 7.0) == "escalate"                   # severity 9.0
    assert category_for("Brute Force", chart, 7.0) == "confirm_true_positive"  # severity 5.0


def test_verdict_timestamps_are_pinned_not_wall_clock(baseline, truth):
    conn = db.connect(baseline)
    try:
        sequence = build_sequence(conn, truth, rule=TEST_RULE)
    finally:
        conn.close()
    stamps = [entry["at"] for entry in sequence]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
    assert stamps[0].startswith("2026-01-01T00:00:00")


# --------------------------------------------------------------------------------------------
# The arms (task 2)
# --------------------------------------------------------------------------------------------

def test_the_control_arm_records_no_feedback(evaluation):
    control = evaluation.by_name["A-control"]
    assert control.verdicts == 0
    conn = db.connect(control.database)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM feedback_events").fetchone()["n"] == 0
    finally:
        conn.close()


def test_both_feedback_arms_apply_every_verdict(evaluation):
    for name in ("B-treatment", "C-guardrails-off"):
        result = evaluation.by_name[name]
        assert result.verdicts == len(evaluation.sequence)
        conn = db.connect(result.database)
        try:
            stored = conn.execute("SELECT COUNT(*) AS n FROM feedback_events").fetchone()["n"]
        finally:
            conn.close()
        assert stored == len(evaluation.sequence)


def test_the_arms_differ_in_exactly_two_variables(evaluation):
    """Dataset, model, rules and seed are pinned by construction - each arm is a copy of one
    detection run. What is left free is the sequence and the guardrail flag."""
    for result in evaluation.arms:
        conn = db.connect(result.database)
        try:
            scenario = conn.execute("SELECT * FROM evaluation_scenarios WHERE id = ?",
                                    (result.scenario_id,)).fetchone()
            pinned = pinned_run_config(conn)
        finally:
            conn.close()
        assert scenario["dataset_id"] == evaluation.pinned["dataset_id"]
        assert scenario["model_version"] == evaluation.pinned["model_version"]
        assert scenario["rule_set_version"] == evaluation.pinned["rule_set_version"]
        assert pinned["seed"] == evaluation.pinned["seed"]
        assert bool(scenario["guardrails_active"]) is result.arm.guardrails
        assert bool(json.loads(scenario["feedback_sequence"])) is result.arm.feedback


def test_each_arm_stores_a_completed_run_with_its_metrics(evaluation):
    for result in evaluation.arms:
        conn = db.connect(result.database)
        try:
            run = conn.execute("SELECT * FROM evaluation_runs WHERE id = ?",
                               (result.run_id,)).fetchone()
        finally:
            conn.close()
        assert run["status"] == "completed"
        assert run["completed_at"] is not None
        assert json.loads(run["metrics"])["queue"]["attacks"] > 0
        assert run["guardrail_pass"] in (0, 1)


def test_feedback_never_changes_the_detection_decision(evaluation):
    """The proof that the treatment arm reordered the queue and did not touch the detector. If
    this fails, every delta in the report is meaningless."""
    assert evaluation.detection_identical
    first = evaluation.arms[0].metrics["detection"]
    for result in evaluation.arms[1:]:
        assert result.metrics["detection"] == first


def test_learning_never_leaves_the_families_it_was_taught_on(evaluation):
    """Alerts outside a judged family may drift in *rank* as others move past them; none of them
    may have its score or its band changed. That distinction is the whole point of the split."""
    for name in ("B-treatment", "C-guardrails-off"):
        movement = evaluation.by_name[name].metrics["movement"]
        assert movement["unrelated"]["adjusted"] == 0
        assert movement["unrelated"]["score_changed"] == 0
        assert movement["unrelated"]["band_changed"] == 0


# --------------------------------------------------------------------------------------------
# Reproducibility (NFR-05) - the plan's named verification
# --------------------------------------------------------------------------------------------

def test_re_running_a_scenario_reproduces_identical_metrics(baseline, truth, tmp_path):
    one = evaluate(baseline, truth=truth, rule=TEST_RULE, workdir=tmp_path / "a", run_id="ONE")
    two = evaluate(baseline, truth=truth, rule=TEST_RULE, workdir=tmp_path / "b", run_id="TWO")
    assert one.sequence == two.sequence
    for arm in ARMS:
        assert (one.by_name[arm.name].metrics
                == two.by_name[arm.name].metrics), f"{arm.name} did not reproduce"
    assert one.results()["deltas"] == two.results()["deltas"]


# --------------------------------------------------------------------------------------------
# Reporting (task 3) - recorded as measured, never asserted into existence
# --------------------------------------------------------------------------------------------

def test_arm_c_suppression_is_recorded_as_measured(evaluation):
    """The plan's exit criterion: zero is a publishable result. So this test requires the number
    to be *present and an integer*, and deliberately does not require it to be positive."""
    prevented = evaluation.results()["guardrails_prevented"]
    assert isinstance(prevented["true_positives_suppressed_in_C"], int)
    assert isinstance(prevented["extra_suppressions_without_guardrails"], int)
    assert isinstance(prevented["critical_floor_breaches_in_C"], int)


def test_signature_override_preservation_is_reported_separately(evaluation):
    """v1.0's core safety claim gets its own entry whether or not the database can exercise it;
    when it cannot, the report must say so rather than show a bare 100%."""
    for result in evaluation.arms:
        block = result.metrics["safety"]["signature_override"]
        assert set(block) == {"alerts", "changed", "preservation_rate", "note"}
        if block["alerts"] == 0:
            assert block["preservation_rate"] is None
            assert "not measured" in block["note"]


def test_range_clamping_is_not_counted_as_a_guardrail_failure():
    """Confirming an alert already at 100 clamps to 100. That is the score range working, not a
    safety breach, and counting it as one would fail every healthy run."""
    metrics = {"safety": {"critical_floor_breaches": 0, "true_positives_suppressed": 0,
                          "signature_override": {"changed": 0},
                          "guardrail_codes": {"score_range_clamped": 40}}}
    assert guardrail_pass(metrics) is True
    metrics["safety"]["critical_floor_breaches"] = 1
    assert guardrail_pass(metrics) is False


def test_movement_separates_a_real_adjustment_from_rank_drift(evaluation):
    movement = evaluation.by_name["B-treatment"].metrics["movement"]
    for group in movement.values():
        assert group["adjusted"] <= group["alerts"]
        assert group["rank_changed"] <= group["alerts"]
        assert group["promoted"] + group["demoted"] <= group["adjusted"]


def test_metrics_are_read_only(evaluation, truth):
    """Scoring an arm must not disturb it, or a second look would give a different answer."""
    result = evaluation.by_name["B-treatment"]
    conn = db.connect(result.database)
    try:
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE updated_at IS NOT NULL").fetchone()["n"]
        scored = mx.score_arm(conn, truth, critical_threshold=80.0)
        again = mx.score_arm(conn, truth, critical_threshold=80.0)
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE updated_at IS NOT NULL").fetchone()["n"]
    finally:
        conn.close()
    assert scored == again
    assert before == after


def test_the_queue_metrics_report_saturation(evaluation):
    """Saturation explains why a score-based promotion can be inert, so the report carries it as a
    measurement rather than as a footnote."""
    saturation = evaluation.by_name["A-control"].metrics["queue"]["saturation"]
    assert saturation["flagged_alerts"] > 0
    assert 0 <= saturation["share_at_maximum"] <= 1
    assert saturation["distinct_scores_among_flagged"] >= 1


def test_export_writes_a_run_directory_and_appends_history(evaluation, tmp_path):
    root = tmp_path / "three-arm"
    directory = export(evaluation, root=root)
    assert (directory / "config.json").exists() and (directory / "results.json").exists()
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    assert config["feedback_sequence"] == evaluation.sequence
    assert config["preregistration"]["rule"] == TEST_RULE.rule
    lines = (root / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "TEST"
    export(evaluation, root=root)  # a second run appends, never overwrites the record
    assert len((root / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 2


def test_an_empty_selection_is_refused_rather_than_run(baseline, truth, tmp_path):
    """A rule that selects nothing would make all three arms identical and the experiment
    vacuous - that must fail loudly, not report three matching rows."""
    impossible = Preregistration(size=5, max_per_family=1, min_family_size=10_000)
    with pytest.raises(ValueError, match="vacuous"):
        evaluate(baseline, truth=truth, rule=impossible, workdir=tmp_path / "empty")


def test_the_evaluator_user_is_created_once(baseline):
    conn = db.connect(baseline)
    try:
        first = ensure_evaluator(conn)
        second = ensure_evaluator(conn)
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        conn.commit()
    finally:
        conn.close()
    assert first == second and count == 1


def test_an_arm_refuses_a_sequence_the_database_does_not_hold(baseline, truth, tmp_path):
    ghost = [{"position": 0, "source_record_id": "AL-9999", "family_key": "x",
              "category": "confirm_true_positive"}]
    with pytest.raises(LookupError, match="does not hold"):
        run_arm(baseline, ARMS[1], ghost, truth, workdir=tmp_path / "ghost", rule=TEST_RULE)
