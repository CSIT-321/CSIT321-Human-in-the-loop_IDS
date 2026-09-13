"""S2 contract tests — the plan's verify step for the keystone schema.

    python -m pytest tests/test_contracts.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.contracts import db
from packages.contracts import models as m

HITL = Path(__file__).resolve().parents[1]
SHAP_PREDICTIONS = HITL / "data" / "processed" / "demo_ml_predictions_shap.json"
LEGACY_RULES = HITL / "tests" / "fixtures" / "legacy" / "flow-signatures.json"
ADAPTATION_CONFIG = HITL.parent / "stage-5" / "config" / "adaptation-config.json"

# TDM §7.2 column names, transcribed. The TDM lives outside this repo, so they are pinned here.
TDM_COLUMNS = {
    "users": {"id", "username", "password_hash", "display_name", "email", "role", "status",
              "created_at", "last_login", "require_pw_change", "one_time_pw"},
    "datasets": {"id", "name", "version", "source_file", "preparation_meta", "total_records",
                 "class_distribution", "is_held_out", "created_at", "created_by"},
    "signature_rules": {"id", "rule_id", "name", "severity", "conditions", "enabled", "version",
                        "created_at"},
    "ml_models": {"id", "version", "model_type", "f1_score", "precision", "recall", "model_file",
                  "status", "created_at"},
    "detection_runs": {"id", "dataset_id", "model_version", "rule_set_version", "fusion_weights",
                       "guardrail_config", "status", "alert_count", "started_at", "completed_at"},
    "alerts": {"id", "alert_ref", "dataset_id", "run_id", "combined_score", "severity",
               "confidence", "signature_severity", "ml_probability", "signature_rules",
               "ml_predicted_class", "attack_category", "shap_attributions", "explanation",
               "status", "owner_id", "is_duplicate_of", "is_critical", "created_at", "updated_at"},
    "flow_data": {"id", "alert_id", "src_ip", "dst_ip", "src_port", "dst_port", "protocol",
                  "duration", "packets", "bytes", "flow_features"},
    "feedback_events": {"id", "alert_id", "user_id", "category", "note", "original_score",
                        "requested_delta", "actual_delta", "guardrail_action", "guardrail_reason",
                        "created_at", "amended_from_id"},
    "audit_log": {"id", "event_type", "actor_id", "alert_id", "feedback_id", "details",
                  "created_at"},
    "guardrail_config": {"id", "config_key", "config_value", "description", "updated_at"},
    "evaluation_scenarios": {"id", "name", "dataset_id", "model_version", "rule_set_version",
                             "feedback_sequence", "metrics_config", "guardrails_active",
                             "created_at"},
    "evaluation_runs": {"id", "scenario_id", "status", "metrics", "fpr_reduction",
                        "rank_improvement", "guardrail_pass", "usability_data", "started_at",
                        "completed_at"},
}
# Every column added to a TDM table, and every table the TDM lacks. Each is logged in
# docs/plan-changelog.md (v1.5; S7b's in v1.14); an unlogged addition fails
# test_columns_are_tdm_names_plus_logged_deviations.
DEVIATION_COLUMNS = {
    "signature_rules": {"attack_category", "rationale"},
    "detection_runs": {"seed"},
    "alerts": {"detection_score", "evidence_class", "evidence_priority", "requires_review",
               "queue_class", "queue_priority", "family_key"},
    "flow_data": {"source_record_id"},
}
DEVIATION_TABLES = {
    "alert_families": {"id", "family_key", "attack_category", "scheme", "severity_version",
                       "weight", "feedback_counts", "dominant_category", "agreement_ratio",
                       "gate_open", "gate_reason", "learned_adjustment", "learned_offset",
                       "applied_adjustment", "applied_offset", "updated_at"},
    # Console rebuild B2; added by migration 1 (db.MIGRATIONS), not schema.sql.
    "alert_notes": {"id", "alert_id", "user_id", "body", "created_at"},
}
ENGINE_FEEDBACK_CATEGORIES = {"confirm_true_positive", "mark_false_positive",
                              "mark_expected_activity", "needs_investigation", "escalate"}
APPEND_ONLY = [("audit_log", "audit"), ("feedback_events", "feedback"), ("alert_notes", "note")]

T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
MODEL_VERSION = "xgb-8class-20260911"
RULE_SET_VERSION = "s4b-1"
FAMILY_KEY = '["Brute Force",22,"tcp","SIG-SSH-BRUTE-FORCE"]'


# --------------------------------------------------------------------------------------------
# Builders and fixtures
# --------------------------------------------------------------------------------------------


def ssh_match() -> m.SignatureMatch:
    return m.SignatureMatch(
        rule_id="SIG-SSH-BRUTE-FORCE", version=RULE_SET_VERSION,
        name="SSH Brute Force Flow Pattern", attack_category="Brute Force", severity="Medium",
        matched_conditions=[
            m.MatchedCondition(feature="Dst Port", expected=22, observed=22),
            m.MatchedCondition(feature="Flow Packets/s", expected=m.RangeCondition(min=10.67),
                               observed=54.2),
        ],
    )


def explanation() -> m.MlExplanation:
    return m.MlExplanation(
        status="available", method="xgboost_native_treeshap_pred_contribs",
        output_space="raw_margin", explained_class="Brute Force", explained_class_index=2,
        base_value=0.29, raw_model_margin=6.1,
        top_supporting_features=[m.ShapAttribution(
            feature_name="Dst Port", feature_value=22.0, shap_contribution=1.2,
            direction="supports_prediction")],
        additivity_check=m.AdditivityCheck(passed=True, difference=1e-6, tolerance=1e-4),
    )


def outcome() -> m.GuardrailOutcome:
    return m.GuardrailOutcome(
        score_before=92, requested_delta=-25, actual_delta=-22, score_after=70, action="capped",
        interventions=[m.GuardrailIntervention(
            code="critical_alert_floor", configured_value=70, original_value=67,
            applied_value=70)],
        requires_review=True,
    )


def make_alert(dataset_id: int = 1, run_id: int = 1, **overrides) -> m.Alert:
    fields = dict(
        dataset_id=dataset_id, run_id=run_id, detection_score=92, combined_score=92,
        severity="Critical", confidence=0.97, signature_severity=0.6, ml_probability=0.97,
        signature_rules=[ssh_match()], ml_predicted_class="Brute Force",
        attack_category="Brute Force", shap_attributions=explanation(),
        explanation="SSH rule matched; the model agrees (Brute Force, 0.97).",
        evidence_class="corroborated", evidence_priority=1, created_at=T0, updated_at=T0,
    )
    fields.update(overrides)
    return m.Alert(**fields)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "contracts.db"


@pytest.fixture
def conn(db_path: Path):
    connection = db.connect(db_path)
    db.create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def graph(conn: sqlite3.Connection) -> dict[str, m.Contract]:
    """One persisted instance of every table model, inserted in foreign-key order."""
    rows: dict[str, m.Contract] = {}

    def put(key: str, model: m.Contract) -> int:
        new_id = db.insert(conn, model)
        rows[key] = model.model_copy(update={"id": new_id})
        return new_id

    user = put("user", m.User(
        username="analyst1", password_hash="$2b$12$synthetic", display_name="Analyst One",
        email="analyst1@example.test", role="security_analyst", created_at=T0))
    dataset = put("dataset", m.Dataset(
        name="CSE-CIC-IDS2018 corrected - demo sample", version="demo-20260911",
        source_file="data/processed/demo_sample.csv", preparation_meta={"seed": 20260911},
        total_records=5000, class_distribution={"Benign": 4000, "DoS": 200},
        created_by=user, created_at=T0))
    put("rule", m.SignatureRule(
        rule_id="SIG-SSH-BRUTE-FORCE", name="SSH Brute Force Flow Pattern", severity="Medium",
        conditions={"Protocol": "TCP", "Dst Port": 22, "Flow Packets/s": {"min": 10.67}},
        version=RULE_SET_VERSION, attack_category="Brute Force",
        rationale="Repeated short TCP flows against port 22.", created_at=T0))
    put("model", m.MlModel(
        version=MODEL_VERSION, model_type="XGBoost", f1_score=0.9882, precision=0.99,
        recall=0.98, model_file="models/xgboost_ids_model.json", status="active", created_at=T0))
    run = put("run", m.DetectionRun(
        dataset_id=dataset, model_version=MODEL_VERSION, rule_set_version=RULE_SET_VERSION,
        fusion_weights={"scheme": "evidence_class"},
        guardrail_config={key: value for key, (value, _) in m.GUARDRAIL_DEFAULTS.items()},
        status="completed", alert_count=1, started_at=T0, completed_at=T0, seed=20260911))
    alert = put("alert", make_alert(dataset, run, family_key=FAMILY_KEY))
    put("flow", m.FlowRecord(
        alert_id=alert, source_record_id="AL-00001", src_ip="172.31.69.25",
        dst_ip="18.221.219.4", src_port=51514, dst_port=22, protocol="TCP", duration=0.42,
        packets=22, bytes=3190, flow_features={"Flow Packets/s": 54.2, "Dst Port": 22}))
    feedback = put("feedback", m.FeedbackEvent(
        alert_id=alert, user_id=user, category="mark_false_positive", original_score=92,
        requested_delta=-25, actual_delta=-22, guardrail_action="capped",
        guardrail_reason="critical_alert_floor: score held at 70", created_at=T0))
    put("audit", m.AuditEntry(
        event_type="FEEDBACK", actor_id=user, alert_id=alert, feedback_id=feedback,
        details={"guardrail": outcome().model_dump(mode="json")}, created_at=T0))
    put("guardrail", m.GuardrailConfigEntry(
        config_key="round_trip_probe", config_value=1.5, description="test only", updated_at=T0))
    scenario = put("scenario", m.EvaluationScenario(
        name="treatment", dataset_id=dataset, model_version=MODEL_VERSION,
        rule_set_version=RULE_SET_VERSION,
        feedback_sequence=[{"record": "AL-00001", "category": "mark_false_positive"}],
        metrics_config={"metrics": ["fpr", "rank"]}, created_at=T0))
    put("evaluation", m.EvaluationRun(
        scenario_id=scenario, status="completed", metrics={"fpr": 0.01}, fpr_reduction=12.5,
        rank_improvement=3.0, guardrail_pass=True, started_at=T0, completed_at=T0))
    put("family", m.AlertFamily(
        family_key=FAMILY_KEY, attack_category="Brute Force", scheme="s7b-c1-m1-category-gate",
        severity_version="sev-1", weight=0.5, feedback_counts={"mark_false_positive": 1},
        dominant_category="mark_false_positive", agreement_ratio=1.0, gate_open=False,
        gate_reason="not enough learning verdicts: 1 of 3 required", learned_adjustment=-15.0,
        learned_offset=0, applied_adjustment=0.0, applied_offset=0, updated_at=T0))
    put("note", m.AlertNote(alert_id=alert, user_id=user, body="Destination is the SSH bastion.",
                            created_at=T0))
    conn.commit()
    return rows


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}


def columns(conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def is_unique(conn: sqlite3.Connection, table: str, column: str) -> bool:
    for index in conn.execute(f"PRAGMA index_list({table})"):
        if index["unique"]:
            indexed = [row["name"] for row in conn.execute(f"PRAGMA index_info({index['name']})")]
            if indexed == [column]:
                return True
    return False


# --------------------------------------------------------------------------------------------
# Schema shape
# --------------------------------------------------------------------------------------------


def test_schema_is_the_twelve_table_demo_subset_plus_logged_tables(conn):
    assert table_names(conn) == set(TDM_COLUMNS) | set(DEVIATION_TABLES)


def test_columns_are_tdm_names_plus_logged_deviations(conn):
    for table, tdm in TDM_COLUMNS.items():
        assert set(columns(conn, table)) == tdm | DEVIATION_COLUMNS.get(table, set()), table
    for table, logged in DEVIATION_TABLES.items():
        assert set(columns(conn, table)) == logged, table


def test_every_table_model_matches_its_columns(conn):
    assert set(db.TABLE_MODELS) == table_names(conn)
    for table, model in db.TABLE_MODELS.items():
        assert set(model.model_fields) == set(columns(conn, table)), table


EXPECTED_FOREIGN_KEYS = {
    ("datasets", "created_by", "users", "id"),
    ("detection_runs", "dataset_id", "datasets", "id"),
    ("detection_runs", "model_version", "ml_models", "version"),
    ("alerts", "dataset_id", "datasets", "id"),
    ("alerts", "run_id", "detection_runs", "id"),
    ("alerts", "owner_id", "users", "id"),
    ("alerts", "is_duplicate_of", "alerts", "id"),
    ("flow_data", "alert_id", "alerts", "id"),
    ("feedback_events", "alert_id", "alerts", "id"),
    ("feedback_events", "user_id", "users", "id"),
    ("feedback_events", "amended_from_id", "feedback_events", "id"),
    ("audit_log", "actor_id", "users", "id"),
    ("alert_notes", "alert_id", "alerts", "id"),
    ("alert_notes", "user_id", "users", "id"),
    ("audit_log", "alert_id", "alerts", "id"),
    ("audit_log", "feedback_id", "feedback_events", "id"),
    ("evaluation_scenarios", "dataset_id", "datasets", "id"),
    ("evaluation_scenarios", "model_version", "ml_models", "version"),
    ("evaluation_runs", "scenario_id", "evaluation_scenarios", "id"),
}


def test_every_foreign_key_resolves(conn):
    tables = table_names(conn)
    found = set()
    for table in tables:
        for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
            parent, parent_column = fk["table"], fk["to"]
            assert parent in tables, f"{table}.{fk['from']} -> missing table {parent}"
            parent_columns = columns(conn, parent)
            assert parent_column in parent_columns, f"{table}.{fk['from']} -> {parent}.{parent_column}"
            assert parent_columns[parent_column]["pk"] or is_unique(conn, parent, parent_column), (
                f"{parent}.{parent_column} is neither PRIMARY KEY nor UNIQUE")
            found.add((table, fk["from"], parent, parent_column))
    assert found == EXPECTED_FOREIGN_KEYS
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_connection_enforces_foreign_keys(conn, graph):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    orphan = graph["alert"].model_copy(update={"id": None, "alert_ref": uuid4(), "run_id": 999})
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        db.insert(conn, orphan)


def test_guardrail_defaults_are_seeded(conn):
    seeded = {row["config_key"]: row["config_value"]
              for row in conn.execute("SELECT config_key, config_value FROM guardrail_config")}
    assert seeded == {key: value for key, (value, _) in m.GUARDRAIL_DEFAULTS.items()}
    # the five TDM defaults, the plan's infiltration floor, and the positive cap the docs omit
    assert {k: seeded[k] for k in ("max_feedback_reduction", "critical_alert_floor",
                                   "critical_alert_threshold", "learned_exception_min_occurrences",
                                   "learned_exception_min_confidence", "infiltration_alert_floor",
                                   "max_feedback_increase")} == {
        "max_feedback_reduction": 30, "critical_alert_floor": 70, "critical_alert_threshold": 80,
        "learned_exception_min_occurrences": 3, "learned_exception_min_confidence": 60,
        "infiltration_alert_floor": 75, "max_feedback_increase": 20}


@pytest.mark.skipif(not ADAPTATION_CONFIG.exists(), reason="collaborator config not present")
def test_guardrail_defaults_agree_with_adaptation_config():
    config = json.loads(ADAPTATION_CONFIG.read_text(encoding="utf-8"))
    guardrails, aggregation = config["guardrails"], config["aggregation"]
    defaults = {key: value for key, (value, _) in m.GUARDRAIL_DEFAULTS.items()}
    assert defaults["max_feedback_reduction"] == -guardrails["maximumNegativeAdjustment"]
    assert defaults["max_feedback_increase"] == guardrails["maximumPositiveAdjustment"]
    assert defaults["critical_alert_floor"] == guardrails["criticalFloor"]
    assert defaults["infiltration_alert_floor"] == guardrails["infiltrationFloor"]
    assert defaults["review_threshold"] == guardrails["reviewThreshold"]
    assert defaults["high_risk_threshold"] == guardrails["highRiskThreshold"]
    assert defaults["aggregation_min_feedback_count"] == aggregation["minimumFeedbackCount"]
    assert defaults["aggregation_min_agreement_ratio"] == aggregation["minimumAgreementRatio"]
    assert defaults["aggregation_strong_agreement_ratio"] == aggregation["strongAgreementRatio"]


# --------------------------------------------------------------------------------------------
# Round trips
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["user", "dataset", "rule", "model", "run", "alert", "flow",
                                 "feedback", "audit", "guardrail", "scenario", "evaluation",
                                 "family"])
def test_table_model_round_trips_through_sqlite(conn, graph, key):
    model = graph[key]
    assert db.get(conn, type(model), model.id) == model


@pytest.mark.parametrize("model", [
    ssh_match(), explanation(), outcome(),
    m.RangeCondition(min=1, max=5),
    m.OneOfCondition.model_validate({"oneOf": [80, 443]}),
], ids=lambda model: type(model).__name__)
def test_value_model_round_trips_through_json(model):
    assert type(model).model_validate(json.loads(json.dumps(model.model_dump(mode="json")))) == model


def test_condition_format_holds_the_frozen_legacy_rules():
    for rule in json.loads(LEGACY_RULES.read_text(encoding="utf-8")):
        parsed = m.SignatureRule(
            rule_id=rule["id"], name=rule["name"], severity=rule["severity"],
            conditions=rule["condition"], version="legacy",
            attack_category=rule["predictedAttackType"])
        assert parsed.model_dump(mode="json")["conditions"] == rule["condition"], rule["id"]


@pytest.mark.skipif(not SHAP_PREDICTIONS.exists(),
                    reason="gitignored; regenerate with scripts/run_ml_inference.py")
def test_real_ml_predictions_fit_the_contract_and_persist(conn, graph):
    records = json.loads(SHAP_PREDICTIONS.read_text(encoding="utf-8"))
    predictions = [m.MlPrediction.model_validate(record) for record in records.values()]
    assert len(predictions) == 5000
    assert all(p.prediction_status == "available" for p in predictions)
    assert all(p.explanation.status == "available" for p in predictions)

    attack = next(p for p in predictions if p.predicted_class != "Benign")
    alert = make_alert(
        graph["dataset"].id, graph["run"].id, signature_rules=None, evidence_class="ml_only",
        ml_predicted_class=attack.predicted_class, attack_category=attack.predicted_class,
        confidence=attack.model_confidence, ml_probability=attack.model_confidence,
        shap_attributions=attack.explanation)
    stored = db.get(conn, m.Alert, db.insert(conn, alert))
    assert stored.shap_attributions == attack.explanation


# --------------------------------------------------------------------------------------------
# Append-only
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("table", "key"), APPEND_ONLY)
def test_append_only_rejects_update(conn, graph, table, key):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"UPDATE {table} SET created_at = 'tampered' WHERE id = ?", (graph[key].id,))


@pytest.mark.parametrize(("table", "key"), APPEND_ONLY)
def test_append_only_rejects_delete(conn, graph, table, key):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (graph[key].id,))


@pytest.mark.parametrize(("table", "key"), APPEND_ONLY)
def test_append_only_holds_on_a_raw_connection(db_path, graph, table, key):
    """No recursive_triggers, no foreign_keys: REPLACE and UPSERT must still be refused."""
    raw = sqlite3.connect(db_path)
    try:
        row_id = graph[key].id
        before = raw.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            raw.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table} WHERE id = ?",
                        (row_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            raw.execute(f"INSERT INTO {table} SELECT * FROM {table} WHERE id = ? "
                        "ON CONFLICT (id) DO UPDATE SET created_at = 'tampered'", (row_id,))
        assert raw.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone() == before
    finally:
        raw.close()


def test_amendment_is_a_new_feedback_row(conn, graph):
    original = graph["feedback"]
    amendment = original.model_copy(update={
        "id": None, "category": "needs_investigation", "requested_delta": 0, "actual_delta": 0,
        "guardrail_action": "applied", "guardrail_reason": None, "amended_from_id": original.id})
    stored = db.get(conn, m.FeedbackEvent, db.insert(conn, amendment))
    assert stored.amended_from_id == original.id
    assert db.get(conn, m.FeedbackEvent, original.id) == original


# --------------------------------------------------------------------------------------------
# Invariants the contract carries
# --------------------------------------------------------------------------------------------


def test_queue_orders_by_queue_band_then_score(conn, graph):
    dataset, run = graph["dataset"].id, graph["run"].id
    for band, score in [("signature_override", 99), ("tier2_candidate", 40), ("ml_only", 100),
                        ("tier2_candidate", 95)]:
        db.insert(conn, make_alert(dataset, run, queue_class=band, combined_score=score,
                                   detection_score=score))
    order = [(row["queue_priority"], row["combined_score"]) for row in conn.execute(
        f"SELECT queue_priority, combined_score FROM alerts ORDER BY {db.QUEUE_ORDER_BY}")]
    # The score-100 alert is last: score only orders within a queue band (invariant I5).
    assert order == [(0, 95), (0, 40), (1, 92), (2, 99), (3, 100)]


def test_queue_band_defaults_to_the_evidence_band():
    assert (make_alert().queue_class, make_alert().queue_priority) == ("corroborated", 1)
    model_only = make_alert(signature_rules=None, evidence_class="ml_only", evidence_priority=2)
    assert (model_only.queue_class, model_only.queue_priority) == ("ml_only", 3)
    assert list(m.QUEUE_PRIORITY) == list(get_args(m.QueueClass))


def test_queue_priority_must_be_its_bands():
    with pytest.raises(ValidationError, match="queue_priority"):
        make_alert(queue_class="tier2_candidate", queue_priority=1)


def test_signature_override_never_leaves_its_band():
    with pytest.raises(ValidationError, match="I3"):
        make_alert(evidence_class="signature_override", ml_predicted_class="DoS",
                   queue_class="tier2_candidate")


def test_database_enforces_the_queue_band(conn, graph):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # the priority no longer matches
        conn.execute("UPDATE alerts SET queue_class = 'tier2_candidate' WHERE id = ?",
                     (graph["alert"].id,))
    override = db.insert(conn, make_alert(graph["dataset"].id, graph["run"].id,
                                          evidence_class="signature_override",
                                          ml_predicted_class="DoS"))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # I3
        conn.execute("UPDATE alerts SET queue_class = 'tier2_candidate', queue_priority = 0 "
                     "WHERE id = ?", (override,))


def test_a_family_whose_gate_is_shut_applies_nothing():
    with pytest.raises(ValidationError, match="shut"):
        m.AlertFamily(family_key=FAMILY_KEY, scheme="s7b", severity_version="sev-1", weight=0.5,
                      feedback_counts={"mark_false_positive": 1}, agreement_ratio=1.0,
                      gate_open=False, gate_reason="1 of 3", learned_adjustment=-15.0,
                      learned_offset=0, applied_adjustment=-15.0, applied_offset=0)


def test_alert_evidence_class_must_agree_with_detectors():
    with pytest.raises(ValidationError, match="signature"):
        make_alert(evidence_class="ml_only")  # a signature fired
    with pytest.raises(ValidationError, match="signature"):
        make_alert(signature_rules=None)  # corroborated without a signature
    with pytest.raises(ValidationError, match="ML attack"):
        make_alert(signature_rules=None, evidence_class="ml_only", ml_predicted_class="Benign")
    # Retired as a live case (v1.3) but still a valid branch of the contract.
    assert make_alert(evidence_class="signature_override", ml_predicted_class="Benign")
    assert make_alert(signature_rules=None, evidence_class="none", ml_predicted_class="Benign")


def test_database_rejects_evidence_class_that_contradicts_detectors(conn, graph):
    forged = graph["alert"].model_copy(
        update={"id": None, "alert_ref": uuid4(), "evidence_class": "ml_only"})
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.insert(conn, forged)


def test_feedback_categories_are_the_engine_five(conn, graph):
    assert set(get_args(m.FeedbackCategory)) == ENGINE_FEEDBACK_CATEGORIES
    duplicate = graph["feedback"].model_copy(update={"id": None, "category": "duplicate"})
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.insert(conn, duplicate)


@pytest.mark.parametrize(("action", "requested", "actual", "reason"), [
    ("applied", -25, -20, None),
    ("capped", -25, -25, "cap"),
    ("rejected", -25, -5, "rejected"),
    ("capped", -25, -20, None),
])
def test_feedback_delta_must_agree_with_guardrail_action(action, requested, actual, reason):
    with pytest.raises(ValidationError):
        m.FeedbackEvent(alert_id=1, user_id=1, category="mark_false_positive", original_score=92,
                        requested_delta=requested, actual_delta=actual,
                        guardrail_action=action, guardrail_reason=reason)


def test_guardrail_outcome_must_explain_a_cap():
    with pytest.raises(ValidationError, match="interventions"):
        m.GuardrailOutcome.model_validate({**outcome().model_dump(), "interventions": []})


@pytest.mark.parametrize("field", ["Label", "Attempted Category", "is_attempted", "attack_class",
                                   "label"])
def test_flow_record_refuses_label_fields(field):
    with pytest.raises(ValidationError, match="label fields"):
        m.FlowRecord(source_record_id="AL-00001", src_ip="10.0.0.1", dst_ip="10.0.0.2",
                     src_port=1, dst_port=22, protocol="TCP", duration=0.1, packets=1, bytes=60,
                     flow_features={"Dst Port": 22, field: "Brute Force"})


def test_leakage_fields_cover_the_inference_guard():
    pytest.importorskip("xgboost")
    from packages.detection.ml.inference import FORBIDDEN_PREDICTION_FIELDS

    assert set(FORBIDDEN_PREDICTION_FIELDS) <= m.LEAKAGE_FIELDS


def test_available_explanation_requires_passed_additivity():
    with pytest.raises(ValidationError, match="additivity"):
        m.MlExplanation(status="available", method="xgboost_native_treeshap_pred_contribs",
                        additivity_check=m.AdditivityCheck(passed=False, difference=1.0,
                                                           tolerance=1e-4))


def test_feedback_audit_entry_must_link_actor_alert_and_feedback():
    with pytest.raises(ValidationError, match="feedback_id"):
        m.AuditEntry(event_type="FEEDBACK", actor_id=1, alert_id=1, details={})


def test_non_finite_values_are_refused():
    with pytest.raises(ValidationError):
        m.FlowRecord(source_record_id="AL-00001", src_ip="10.0.0.1", dst_ip="10.0.0.2",
                     src_port=1, dst_port=22, protocol="TCP", duration=0.1, packets=1, bytes=60,
                     flow_features={"Flow Bytes/s": float("inf")})


TIMESTAMP_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def test_stored_timestamps_are_fixed_width_so_text_order_is_time_order(conn, graph):
    # Variable-width ISO text sorts wrongly ("12:00:00.5Z" < "12:00:00Z"); audit range queries
    # and the TDM's created_at indexes depend on text order being time order.
    user = graph["user"].id
    for moment in (T0 + timedelta(seconds=1), T0 + timedelta(microseconds=500_000), T0):
        db.insert(conn, m.AuditEntry(event_type="LOGIN", actor_id=user, created_at=moment))
    conn.execute("INSERT INTO audit_log (event_type, actor_id, details) VALUES ('LOGIN', ?, '{}')",
                 (user,))  # takes the database default timestamp
    stored = [row["created_at"] for row in
              conn.execute("SELECT created_at FROM audit_log ORDER BY created_at, id")]
    assert all(TIMESTAMP_TEXT.match(text) for text in stored), stored
    moments = [datetime.fromisoformat(text) for text in stored]
    assert moments == sorted(moments)


def test_timestamps_without_a_timezone_are_refused():
    with pytest.raises(ValidationError):
        m.AuditEntry(event_type="DETECTION_RUN", created_at=datetime(2026, 9, 11, 12, 0))
    with pytest.raises(ValueError, match="timezone"):
        db.format_timestamp(datetime(2026, 9, 11, 12, 0))
