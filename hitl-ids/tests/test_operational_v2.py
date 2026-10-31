"""V2 is an isolated evidence/triage foundation, not an activated operational workflow."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest
from pydantic import ValidationError

from packages.contracts import db, models as m
from packages.contracts.operational_v2 import OperationalAlertV2, OperationalTriageStateV2
from packages.detection.adapters.operational_v2 import (
    materialize_source, preview_source, project_external, project_legacy, read_projection, read_triage,
)
from packages.detection.adapters.staging import import_file, stage_file
from packages.detection.feedback.service import submit_feedback
from packages.detection.pipeline import store
from packages.evaluation import metrics
from test_api import client, database, rows
from test_evaluation import truth, truth_file

FIXTURE = Path(__file__).parent / "fixtures/suricata-alerts.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inspect_alert_v2.py"


def snapshot(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                      "AND name NOT IN ('sqlite_sequence', 'operational_alerts_v2', "
                                      "'operational_triage_state_v2', 'operational_triage_policy_audit', 'operational_routing_audit', "
                                      "'external_eligibility_review', 'external_operational_admission',"
                                      "'tier2_cases','tier2_case_state','tier2_case_events','response_recommendations','response_decisions',"
                                      "'triage_memory_lessons','triage_memory_support_events','triage_memory_decisions','triage_memory_audit')")]
    return {name: [tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY 1')]
            for name in names}


def test_legacy_projection_preserves_full_evidence_and_distinct_confidence(database):
    with closing(db.connect(database)) as conn:
        alert = db.get(conn, m.Alert, 1)
        canonical = store.detector_for_alert(conn, alert, store.flow_for_alert(conn, 1))
        before = snapshot(conn)
        projected = project_legacy(alert, canonical)
        assert projected.operational_alert_ref == alert.alert_ref
        assert projected.canonical_alert_id == canonical.canonical_alert_id
        assert projected.legacy_alert_id == 1 and projected.external_inbox_id is None
        assert projected.detector_confidence == canonical.confidence
        assert projected.source_provenance.legacy_fusion_confidence == alert.confidence
        assert projected.source_provenance.detection_score == alert.detection_score
        assert projected.detector_evidence.model_dump() == canonical.model_dump()
        for key in ("signatureRules", "mlProbability", "treeShap", "detectionScore"):
            assert projected.detector_evidence.structured_evidence[key] == canonical.structured_evidence[key]
        assert snapshot(conn) == before
        assert OperationalAlertV2.model_validate_json(projected.model_dump_json(by_alias=True)) == projected
        with pytest.raises((TypeError, ValidationError)):
            projected.detector_evidence.structured_evidence["detectionScore"] = 0


def test_suricata_projection_retains_null_confidence_timestamps_and_proposal(database):
    import_file(FIXTURE, "sensor-a", database)
    with closing(db.connect(database)) as conn:
        for row in conn.execute("SELECT * FROM external_alert_inbox"):
            projected = project_external(row)
            canonical = json.loads(row["canonical_snapshot"])
            assert projected.detector_confidence is None
            assert projected.native_severity == row["native_severity"]
            assert projected.external_inbox_id == row["id"] and projected.legacy_alert_id is None
            assert str(projected.canonical_alert_id) == row["canonical_alert_id"]
            assert projected.occurred_at == row["occurred_at"]
            assert projected.occurred_at_timezone_offset == row["occurred_at_timezone_offset"]
            assert projected.detector_evidence.model_dump(mode="json", by_alias=True) == canonical
            assert projected.source_provenance.proposed_operational_priority == row["proposed_operational_priority"]
            assert projected.source_provenance.proposed_evidence_class == "external_rule"
            assert "operational_priority" not in type(projected).model_fields
            assert OperationalAlertV2.model_validate_json(projected.model_dump_json(by_alias=True)) == projected


@pytest.mark.parametrize("changes", [
    {"legacy_alert_id": None}, {"external_inbox_id": 1},
    {"source_kind": "external_nids_alert"}, {"detector_confidence": 0.123},
    {"native_severity": "wrong"}, {"occurred_at": "bad"},
    {"source_port": -1}, {"destination_ip": "mismatched"},
    {"occurred_at_timezone_offset": "+12:00"},
])
def test_contract_rejects_invalid_or_inconsistent_projection(database, changes):
    with closing(db.connect(database)) as conn:
        value = preview_source(conn, "legacy_flow_alert", 1).model_dump()
    value.update(changes)
    with pytest.raises(ValidationError):
        OperationalAlertV2.model_validate(value)


def test_suricata_cannot_acquire_confidence_or_inconsistent_source_fields(database):
    import_file(FIXTURE, "sensor-a", database)
    with closing(db.connect(database)) as conn:
        row = dict(conn.execute("SELECT * FROM external_alert_inbox LIMIT 1").fetchone())
        altered = {**row, "confidence": 0.85}
        with pytest.raises(ValueError, match="disagree"):
            project_external(altered)
        value = project_external(row).model_dump()
        value["detector_confidence"] = 0.85
        value["detector_evidence"]["confidence"] = 0.85
        with pytest.raises(ValidationError, match="Suricata confidence"):
            OperationalAlertV2.model_validate(value)


@pytest.mark.parametrize("source_kind,source_id", [("legacy_flow_alert", 1), ("external_nids_alert", 1)])
def test_persistence_has_dormant_defaults_and_independent_mutable_triage(database, source_kind, source_id):
    import_file(FIXTURE, "sensor-a", database)
    with closing(db.connect(database)) as conn:
        before = snapshot(conn)
        projected = materialize_source(conn, source_kind, source_id)
        assert projected.id is not None
        triage = read_triage(conn, projected.id)
        assert triage.operational_priority is None and triage.priority_band is None
        assert triage.handling_route == "unassigned" and triage.workflow_stage == "staged"
        assert triage.review_required and not triage.tier2_recommended
        assert not triage.tier2_recommendation_reasons and triage.triage_policy_version is None
        before_evidence = conn.execute("SELECT * FROM operational_alerts_v2").fetchall()
        # An explicit test write proves separation. No routing/update API is activated.
        conn.execute("UPDATE operational_triage_state_v2 SET review_reason=?, decision_source='analyst', "
                     "operational_priority=75, priority_band='high' WHERE operational_alert_id=?",
                     ("Test-only independent triage state", projected.id))
        conn.commit()
        assert read_triage(conn, projected.id).operational_priority == 75
        assert read_triage(conn, projected.id).handling_route == "unassigned"
        assert conn.execute("SELECT * FROM operational_alerts_v2").fetchall() == before_evidence
        assert materialize_source(conn, source_kind, source_id) == projected
        assert read_triage(conn, projected.id).operational_priority == 75
        assert snapshot(conn) == before
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.mark.parametrize("changes", [
    {"operational_priority": 20}, {"priority_band": "high"},
    {"operational_priority": float("nan"), "priority_band": "high"},
    {"tier2_recommended": True}, {"tier2_recommendation_reasons": ["reason"]},
    {"tier2_recommended": True, "tier2_recommendation_reasons": [""]},
])
def test_triage_contract_rejects_incoherent_state(changes):
    with pytest.raises(ValidationError):
        OperationalTriageStateV2(operational_alert_id=1, **changes)


def test_snapshot_sql_immutability_including_replace(database):
    with closing(db.connect(database)) as conn:
        materialize_source(conn, "legacy_flow_alert", 1)
    with closing(sqlite3.connect(database)) as conn:
        before = conn.execute("SELECT * FROM operational_alerts_v2").fetchall()
        for sql in (
            "UPDATE operational_alerts_v2 SET detector_evidence='{}'",
            "UPDATE operational_alerts_v2 SET source_provenance='{}'",
            "DELETE FROM operational_alerts_v2",
            "INSERT OR REPLACE INTO operational_alerts_v2 SELECT * FROM operational_alerts_v2",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(sql)
            conn.rollback()
        assert conn.execute("SELECT * FROM operational_alerts_v2").fetchall() == before


def test_sql_source_constraints_and_atomic_failure(database):
    with closing(db.connect(database)) as conn:
        projected = preview_source(conn, "legacy_flow_alert", 1)
        row = projected.model_dump(mode="json", exclude={"id"})
        for key in ("native_severity", "detector_evidence", "source_provenance"):
            row[key] = json.dumps(row[key])
        sql = f"INSERT INTO operational_alerts_v2 ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})"
        for refs in ({"legacy_alert_id": None}, {"external_inbox_id": 1}, {"legacy_alert_id": 999999}):
            changed = {**row, **refs}
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql, list(changed.values()))
            conn.rollback()
        conn.execute("CREATE TRIGGER fail_triage BEFORE INSERT ON operational_triage_state_v2 "
                     "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="test failure"):
            materialize_source(conn, "legacy_flow_alert", 1)
        assert conn.execute("SELECT COUNT(*) FROM operational_alerts_v2").fetchone()[0] == 0


def test_concurrent_source_projection_is_idempotent(database):
    ready = Barrier(2)
    def project():
        with closing(db.connect(database)) as conn:
            ready.wait(timeout=5)
            return materialize_source(conn, "legacy_flow_alert", 1).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: project(), range(2))) == [1, 1]


def test_migration_four_preserves_populated_v3_rows_schema_and_foreign_keys(tmp_path, sample, predictions, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:3])
        path = database.__wrapped__(tmp_path, sample, predictions)
        import_file(FIXTURE, "sensor-a", path)
    with closing(db.connect(path)) as conn:
        user = db.insert(conn, m.User(username="reviewer", password_hash="fixture", display_name="Reviewer",
                                      email="reviewer@example.test", role="security_analyst"))
        conn.commit()
        submit_feedback(conn, alert_id=1, user_id=user, category="mark_false_positive")
        before = snapshot(conn)
        schema = list(map(tuple, conn.execute("SELECT name, rootpage, sql FROM sqlite_master "
                                             "WHERE name NOT LIKE 'sqlite_%' ORDER BY name")))
        trace = []
        conn.set_trace_callback(trace.append)
        assert db.migrate(conn) == [4, 5, 6, 7, 8, 9, 10]
        assert db.migrate(conn) == []
        assert snapshot(conn) == before
        for name, rootpage, sql in schema:
            assert tuple(conn.execute("SELECT name, rootpage, sql FROM sqlite_master WHERE name=?",
                                      (name,)).fetchone()) == (name, rootpage, sql)
        assert not any("DROP " in sql.upper() or ("ALTER " in sql.upper() and not sql.strip().startswith(
            "ALTER TABLE operational_triage_state_v2 ADD COLUMN priority_band_scheme TEXT NOT NULL")) or
                       "FOREIGN_KEYS=OFF" in sql.upper().replace(" ", "") for sql in trace)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT COUNT(*) FROM operational_alerts_v2").fetchone()[0] == 0


def test_v2_never_changes_queue_feedback_evaluation_or_staging(client, database, truth):
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.post(f"/api/alerts/{ref}/feedback", json={"category": "mark_false_positive"}).status_code == 200
    import_file(FIXTURE, "sensor-a", database)
    queue_before = client.get("/api/alerts").json()
    detail_before = client.get(f"/api/alerts/{ref}").json()
    with closing(db.connect(database)) as conn:
        before = snapshot(conn)
        evaluation_before = metrics.read_queue(conn, truth)
        overview = store.source_ip_security_overview(conn)
        for row in conn.execute("SELECT id FROM alerts").fetchall():
            materialize_source(conn, "legacy_flow_alert", row["id"])
        external = materialize_source(conn, "external_nids_alert", 1)
        assert snapshot(conn) == before
        after = metrics.read_queue(conn, truth)
        assert after == evaluation_before
        assert metrics.detection_metrics(after) == metrics.detection_metrics(evaluation_before)
        assert metrics.queue_metrics(after) == metrics.queue_metrics(evaluation_before)
        assert store.source_ip_security_overview(conn) == overview
        assert stage_file(conn, FIXTURE, "sensor-a").duplicate == 2
        assert snapshot(conn) == before
    assert client.get("/api/alerts").json() == queue_before
    assert client.get(f"/api/alerts/{ref}").json() == detail_before
    assert client.get(f"/api/alerts/{external.operational_alert_ref}").status_code == 404
    assert client.post(f"/api/alerts/{external.operational_alert_ref}/feedback",
                       json={"category": "needs_investigation"}).status_code == 404


def test_cli_preview_and_persisted_inspection_write_nothing(database):
    import_file(FIXTURE, "sensor-a", database)
    with closing(db.connect(database)) as conn:
        operational = materialize_source(conn, "legacy_flow_alert", 1)
    before = database.read_bytes()
    for option, identifier in (("--legacy-alert-id", 1), ("--external-inbox-id", 1),
                               ("--operational-alert-id", operational.id)):
        result = subprocess.run([sys.executable, str(SCRIPT), "--database", str(database),
                                 option, str(identifier)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["operationalAdmission"] == "pending" and data["routingPolicy"] == "inactive"
        assert database.read_bytes() == before
