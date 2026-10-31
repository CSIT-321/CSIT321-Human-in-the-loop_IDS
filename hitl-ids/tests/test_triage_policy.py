"""V1 urgency, explicit context, explained recommendations, and audited V2-only mutation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest
from pydantic import ValidationError

from packages.contracts import db, models as m
from packages.contracts.operational_v2 import OperationalAlertV2
from packages.detection.adapters.operational_v2 import materialize_source, preview_source, read_triage
from packages.detection.adapters.staging import stage_file, import_file
from packages.detection.triage_policy import TriageContext, TriagePolicy, evaluate_triage, load_triage_policy
from packages.detection.triage_policy_service import StaleTriageState, apply_triage_policy
from packages.detection.pipeline import store
from packages.evaluation import metrics
from test_api import client, database, rows
from test_evaluation import truth, truth_file
from test_operational_v2 import snapshot

FIXTURE = Path(__file__).parent / "fixtures/suricata-alerts.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preview_triage_policy.py"


@pytest.fixture
def external():
    with closing(db.connect(":memory:")) as conn:
        db.create_schema(conn)
        stage_file(conn, FIXTURE, "test-sensor")
        return preview_source(conn, "external_nids_alert", 1)


def with_severity(external, severity):
    data = external.model_dump()
    data["native_severity"] = severity
    data["detector_evidence"]["detector_severity"] = severity
    return OperationalAlertV2.model_validate(data)


@pytest.mark.parametrize("severity,score,band", [(1, 85, "P1"), (2, 65, "P2"), (3, 40, "P3"), (4, 20, "P4")])
def test_default_urgency_is_not_tier_or_confidence(external, severity, score, band):
    alert = with_severity(external, severity)
    before = alert.model_dump_json()
    result = evaluate_triage(alert)
    assert result.base_priority == result.final_operational_priority == score
    assert result.priority_band == band
    assert result.handling_route == "tier1_review" and result.workflow_stage == "triage"
    assert result.review_required and result.decision_source == "system_policy"
    assert result.review_reasons and result.base_priority_reason and not result.context_adjustments
    assert not result.tier2_recommended and not result.tier2_recommendation_reasons
    assert alert.detector_confidence is None and alert.model_dump_json() == before


@pytest.mark.parametrize("context", [
    {"analystEscalated": True}, {"assetCriticality": "critical"},
    {"repeatedCampaign": True, "correlatedAlertCount": 3}, {"unresolvedByTier1": True},
    {"confirmedMalicious": True, "responseRequired": True},
])
def test_explicit_conditions_recommend_but_never_transition(external, context):
    result = evaluate_triage(with_severity(external, 1), TriageContext.model_validate(context))
    assert result.tier2_recommended and all(result.tier2_recommendation_reasons)
    assert result.handling_route == "tier1_review" and result.workflow_stage == "triage"


@pytest.mark.parametrize("context", [
    {"assetCriticality": "critical"}, {"repeatedCampaign": True}, {"correlatedAlertCount": 99},
    {"repeatedCampaign": True, "correlatedAlertCount": 2},
    {"knownMaliciousIndicator": True, "responseRequired": True},
    {"confirmedMalicious": True}, {"responseRequired": True}, {"evidenceConflict": True},
])
def test_incomplete_or_low_priority_context_is_not_escalation(external, context):
    result = evaluate_triage(with_severity(external, 4), TriageContext.model_validate(context))
    assert not result.tier2_recommended


def test_unknown_is_not_false_and_every_adjustment_is_explained(external):
    unknown = TriageContext()
    assert all(value is None for value in unknown.model_dump().values())
    assert any("unknown / not available" in reason for reason in evaluate_triage(external, unknown).review_reasons)
    explicit = TriageContext(analyst_escalated=False, evidence_conflict=False)
    assert "analystEscalated" not in " ".join(evaluate_triage(external, explicit).review_reasons)
    adjusted = evaluate_triage(with_severity(external, 1), TriageContext(
        asset_criticality="critical", known_malicious_indicator=True, evidence_conflict=True))
    assert adjusted.final_operational_priority == 100
    assert sum(item.applied_delta for item in adjusted.context_adjustments) == 15
    assert all(item.reason for item in adjusted.context_adjustments)
    assert adjusted.context_adjustments[-1].applied_delta == 0


@pytest.mark.parametrize("score,band", [(0, "P4"), (29.9, "P4"), (30, "P3"), (59.9, "P3"),
                                       (60, "P2"), (79.9, "P2"), (80, "P1"), (100, "P1")])
def test_configured_bands_cover_boundaries(external, score, band):
    data = load_triage_policy().model_dump()
    data["version"] = "test-band-v2"
    data["suricata_severity_priority"]["2"] = score
    result = evaluate_triage(external, policy=TriagePolicy.model_validate(data))
    assert result.priority_band == band and not result.tier2_recommended


@pytest.mark.parametrize("context", [{"analystEscalated": "true"}, {"unresolvedByTier1": 1},
                                    {"correlatedAlertCount": -1}, {"correlatedAlertCount": 2.5},
                                    {"assetCriticality": "unknown"}])
def test_invalid_context_is_rejected(context):
    with pytest.raises(ValidationError):
        TriageContext.model_validate(context)


def test_policy_config_validation_and_unsupported_severity(external):
    data = load_triage_policy().model_dump()
    data["priority_bands"][0]["minimum"] = 0
    with pytest.raises(ValidationError):
        TriagePolicy.model_validate(data)
    with pytest.raises(ValueError, match="no configured"):
        evaluate_triage(with_severity(external, 99))


def test_confidence_does_not_determine_priority(database):
    with closing(db.connect(database)) as conn:
        original = preview_source(conn, "legacy_flow_alert", 1)
    expected = evaluate_triage(original)
    for confidence in (None, 0.0, 1.0):
        data = original.model_dump()
        data["detector_confidence"] = confidence
        data["detector_evidence"]["confidence"] = confidence
        assert evaluate_triage(OperationalAlertV2.model_validate(data)) == expected


@pytest.fixture
def applied_database(database):
    import_file(FIXTURE, "sensor", database)
    with closing(db.connect(database)) as conn:
        actor = db.insert(conn, m.User(username="policy-user", password_hash="fixture", display_name="Policy user",
                                      email="policy@example.test", role="security_analyst"))
        conn.commit()
        alert = materialize_source(conn, "external_nids_alert", 1)
        state = read_triage(conn, alert.id)
    return database, actor, alert, state


def test_transactional_application_audit_and_identical_retry(applied_database):
    path, actor, alert, before = applied_database
    with closing(db.connect(path)) as conn:
        evidence = conn.execute("SELECT * FROM operational_alerts_v2").fetchall()
        legacy = snapshot(conn)
        context = TriageContext(analyst_escalated=True)
        result = apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before, context=context,
            now=datetime.now(timezone(timedelta(hours=8))))
        assert result.applied and result.state.priority_band == "P2"
        assert result.state.operational_priority == 65 and result.state.priority_band_scheme == "p1_p4"
        assert result.state.handling_route == "tier1_review" and result.state.tier2_recommended
        assert result.state.triage_policy_version == "operational-triage-v1"
        audit = conn.execute("SELECT * FROM operational_triage_policy_audit").fetchone()
        assert json.loads(audit["before_state"])["operationalPriority"] is None
        assert json.loads(audit["after_state"])["priorityBand"] == "P2"
        assert json.loads(audit["context_snapshot"])["assetCriticality"] is None
        assert json.loads(audit["result_snapshot"])["tier2RecommendationReasons"]
        assert json.loads(audit["policy_snapshot"])["version"] == "operational-triage-v1"
        repeat = apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before, context=context)
        assert not repeat.applied and repeat.audit_id == result.audit_id and repeat.state == result.state
        assert conn.execute("SELECT COUNT(*) FROM operational_triage_policy_audit").fetchone()[0] == 1
        assert conn.execute("SELECT * FROM operational_alerts_v2").fetchall() == evidence
        assert snapshot(conn) == legacy
        inspection = subprocess.run([sys.executable, str(SCRIPT.with_name("inspect_alert_v2.py")),
                                     "--database", str(path), "--operational-alert-id", str(alert.id)],
                                    capture_output=True, text=True)
        assert inspection.returncode == 0, inspection.stderr
        assert json.loads(inspection.stdout)["routingPolicy"] == "applied"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE operational_alerts_v2 SET detector_evidence='{}'")
        conn.rollback()


def test_stale_state_advanced_routes_and_analyst_decisions_are_not_overwritten(applied_database):
    path, actor, alert, before = applied_database
    with closing(db.connect(path)) as conn:
        apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before)
        with pytest.raises(StaleTriageState):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before,
                                context=TriageContext(unresolved_by_tier1=True))
        conn.execute("UPDATE operational_triage_state_v2 SET handling_route='tier2_candidate' WHERE operational_alert_id=?", (alert.id,))
        conn.commit()
        with pytest.raises(ValueError, match="advanced workflow"):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=read_triage(conn, alert.id))
        conn.execute("UPDATE operational_triage_state_v2 SET handling_route='tier1_review', decision_source='analyst'")
        conn.commit()
        with pytest.raises(ValueError, match="analyst decisions"):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=read_triage(conn, alert.id))


def test_unauthorised_actor_rejected_and_config_version_cannot_be_reused(applied_database):
    path, actor, alert, before = applied_database
    with closing(db.connect(path)) as conn:
        with pytest.raises(PermissionError):
            apply_triage_policy(conn, alert.id, actor_id=999999, expected_state=before)
        current = apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before).state
        data = load_triage_policy().model_dump()
        data["suricata_severity_priority"]["2"] = 67
        with pytest.raises(ValueError, match="new policy version"):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=current,
                                policy=TriagePolicy.model_validate(data))
        conn.execute("UPDATE users SET role='evaluator' WHERE id=?", (actor,))
        conn.commit()
        with pytest.raises(PermissionError):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=current)


def test_audit_failure_rolls_back_state_and_audit_cannot_be_rewritten(applied_database):
    path, actor, alert, before = applied_database
    with closing(db.connect(path)) as conn:
        conn.execute("CREATE TRIGGER fail_policy_audit BEFORE INSERT ON operational_triage_policy_audit "
                     "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="test failure"):
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before)
        assert read_triage(conn, alert.id) == before
        conn.execute("DROP TRIGGER fail_policy_audit")
        conn.commit()
        apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before)
    with closing(sqlite3.connect(path)) as conn:
        for sql in ("UPDATE operational_triage_policy_audit SET before_state='{}'",
                    "DELETE FROM operational_triage_policy_audit",
                    "INSERT OR REPLACE INTO operational_triage_policy_audit SELECT * FROM operational_triage_policy_audit"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(sql)
            conn.rollback()


def test_concurrent_distinct_applications_reject_stale_writer(applied_database):
    path, actor, alert, before = applied_database
    ready = Barrier(2)
    def apply(escalated):
        with closing(db.connect(path)) as conn:
            ready.wait(timeout=5)
            try:
                apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=before,
                                    context=TriageContext(analyst_escalated=escalated))
                return "applied"
            except StaleTriageState:
                return "stale"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(apply, (True, False))) == ["applied", "stale"]


def test_legacy_queue_feedback_guardrails_staging_and_evaluation_unchanged(client, database, truth):
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.post(f"/api/alerts/{ref}/feedback", json={"category": "mark_false_positive"}).status_code == 200
    import_file(FIXTURE, "sensor", database)
    queue_before = client.get("/api/alerts").json()
    detail_before = client.get(f"/api/alerts/{ref}").json()
    with closing(db.connect(database)) as conn:
        actor = conn.execute("SELECT id FROM users WHERE role='security_analyst' LIMIT 1").fetchone()[0]
        legacy = snapshot(conn)
        evaluation = metrics.read_queue(conn, truth)
        ip_overview = store.source_ip_security_overview(conn)
        for source in ("legacy_flow_alert", "external_nids_alert"):
            alert = materialize_source(conn, source, 1)
            result = evaluate_triage(alert)
            if source == "legacy_flow_alert":
                assert result.base_priority == alert.source_provenance.detection_score
            apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=read_triage(conn, alert.id),
                                context=TriageContext(analyst_escalated=True))
        assert snapshot(conn) == legacy
        after = metrics.read_queue(conn, truth)
        assert after == evaluation
        assert metrics.detection_metrics(after) == metrics.detection_metrics(evaluation)
        assert metrics.queue_metrics(after) == metrics.queue_metrics(evaluation)
        assert store.source_ip_security_overview(conn) == ip_overview
        assert stage_file(conn, FIXTURE, "sensor").duplicate == 2
    assert client.get("/api/alerts").json() == queue_before
    assert client.get(f"/api/alerts/{ref}").json() == detail_before
    assert client.post(f"/api/alerts/{ref}/feedback", json={"category": "needs_investigation"}).status_code == 200


def test_preview_cli_is_read_only(applied_database):
    path, actor, alert, before = applied_database
    original = path.read_bytes()
    result = subprocess.run([sys.executable, str(SCRIPT), "--database", str(path),
                             "--operational-alert-id", str(alert.id)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["mode"] == "preview_only" and data["result"]["priorityBand"] == "P2"
    assert path.read_bytes() == original


def test_migration_five_is_additive_and_preserves_existing_band_encoding(tmp_path, sample, predictions, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:4])
        path = database.__wrapped__(tmp_path, sample, predictions)
    with closing(db.connect(path)) as conn:
        alert = preview_source(conn, "legacy_flow_alert", 1)
        values = alert.model_dump(mode="json", exclude={"id"})
        for key in ("native_severity", "detector_evidence", "source_provenance"):
            values[key] = json.dumps(values[key])
        conn.execute(f"INSERT INTO operational_alerts_v2 ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})", list(values.values()))
        conn.execute("INSERT INTO operational_triage_state_v2 (operational_alert_id, operational_priority, priority_band, "
                     "review_reason, decision_source, updated_at) VALUES (1, 75, 'high', 'existing state', 'analyst', ?)",
                     (db.format_timestamp(m.utc_now()),))
        conn.commit()
        old_state = dict(conn.execute("SELECT * FROM operational_triage_state_v2").fetchone())
        legacy = snapshot(conn)
        root = conn.execute("SELECT rootpage FROM sqlite_master WHERE name='operational_triage_state_v2'").fetchone()[0]
        assert db.migrate(conn) == [5, 6, 7, 8, 9] and db.migrate(conn) == []
        state = dict(conn.execute("SELECT * FROM operational_triage_state_v2").fetchone())
        assert state.pop("priority_band_scheme") == "legacy_labels"
        assert state == old_state and read_triage(conn, 1).priority_band == "high"
        assert snapshot(conn) == legacy
        assert conn.execute("SELECT rootpage FROM sqlite_master WHERE name='operational_triage_state_v2'").fetchone()[0] == root
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
