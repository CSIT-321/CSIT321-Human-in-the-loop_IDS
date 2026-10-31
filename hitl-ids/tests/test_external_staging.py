"""External staging is isolated from every current operational table and query."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from packages.contracts import db, models as m
from packages.detection.adapters.staging import import_file, inspect_inbox, stage_file
from packages.detection.feedback.service import submit_feedback
from packages.detection.pipeline import store
from packages.evaluation import metrics
from test_api import client, database, rows
from test_evaluation import truth, truth_file

FIXTURE = Path(__file__).parent / "fixtures/suricata-alerts.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/import_suricata_eve.py"


def table_rows(conn):
    return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY id')]
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                        "AND name NOT IN ('sqlite_sequence','external_alert_inbox', "
                                        "'operational_alerts_v2','operational_triage_state_v2', "
                                        "'operational_triage_policy_audit', 'operational_routing_audit')")}


def test_populated_migration_does_not_rebuild_or_change_core(tmp_path, sample, predictions, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:2])
        path = database.__wrapped__(tmp_path, sample, predictions)
    with closing(db.connect(path)) as conn:
        user_id = db.insert(conn, m.User(username="reviewer", password_hash="fixture",
                            display_name="Reviewer", email="reviewer@example.test", role="security_analyst"))
        conn.commit()
        submit_feedback(conn, alert_id=1, user_id=user_id, category="mark_false_positive")
        before = table_rows(conn)
        schema = list(map(tuple, conn.execute("SELECT name, rootpage, sql FROM sqlite_master "
                                             "WHERE name NOT LIKE 'sqlite_%' ORDER BY name")))
        original_bytes = path.read_bytes()
        assert import_file(FIXTURE, "dry-run-old-schema", path, dry_run=True).staged == 2
        assert inspect_inbox(path)["total"] == 0
        assert path.read_bytes() == original_bytes
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        statements = []
        conn.set_trace_callback(statements.append)
        assert db.migrate(conn) == [3, 4, 5, 6]
        assert table_rows(conn) == before
        for name, rootpage, sql in schema:
            assert tuple(conn.execute("SELECT name, rootpage, sql FROM sqlite_master WHERE name=?",
                                      (name,)).fetchone()) == (name, rootpage, sql)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not any("DROP " in s.upper() or ("ALTER " in s.upper() and not s.strip().startswith(
            "ALTER TABLE operational_triage_state_v2 ADD COLUMN priority_band_scheme TEXT NOT NULL"))
                       or "FOREIGN_KEYS=OFF" in s.upper().replace(" ", "") for s in statements)
        assert not conn.execute("PRAGMA foreign_key_list(external_alert_inbox)").fetchall()
        assert db.migrate(conn) == []


def test_staging_isolated_from_api_feedback_learning_evaluation_and_ip_reports(client, database, truth):
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.post(f"/api/alerts/{ref}/feedback", json={"category": "mark_false_positive"}).status_code == 200
    before_queue = client.get("/api/alerts").json()
    before_detail = client.get(f"/api/alerts/{ref}").json()
    with closing(db.connect(database)) as conn:
        before = table_rows(conn)
        evaluation = metrics.read_queue(conn, truth)
        detection_metrics = metrics.detection_metrics(evaluation)
        queue_metrics = metrics.queue_metrics(evaluation)
        overview = store.source_ip_security_overview(conn)
        source_ip = conn.execute("SELECT src_ip FROM flow_data LIMIT 1").fetchone()[0]
        ip_report = store.ip_security_report(conn, source_ip)
        report = stage_file(conn, FIXTURE, "sensor-a")
        assert report.staged == 2 and report.parsed == 2
        assert table_rows(conn) == before
        assert metrics.read_queue(conn, truth) == evaluation
        assert metrics.detection_metrics(metrics.read_queue(conn, truth)) == detection_metrics
        assert metrics.queue_metrics(metrics.read_queue(conn, truth)) == queue_metrics
        assert store.source_ip_security_overview(conn) == overview
        assert store.ip_security_report(conn, source_ip) == ip_report
        staged = list(conn.execute("SELECT * FROM external_alert_inbox ORDER BY id"))
        for row in staged:
            assert row["confidence"] is None
            assert row["review_required"] == 1
            assert row["learning_eligible"] == row["evaluation_eligible"] == 0
            assert row["proposed_evidence_class"] == "external_rule"
            snapshot = json.loads(row["canonical_snapshot"])
            assert snapshot["evidenceClass"] == "external_signature"
            assert snapshot["confidence"] is None
            assert row["native_severity"] == snapshot["detectorSeverity"]
            assert row["admission_decision"] == "hold_for_review"
            assert "pending" in row["admission_reason"]
        assert staged[1]["source_port"] is None
    assert client.get("/api/alerts").json() == before_queue
    assert client.get(f"/api/alerts/{ref}").json() == before_detail
    for row in staged:
        assert client.get(f'/api/alerts/{row["canonical_alert_id"]}').status_code == 404
        assert client.post(f'/api/alerts/{row["canonical_alert_id"]}/feedback',
                           json={"category": "needs_investigation"}).status_code == 404
    assert client.post(f"/api/alerts/{ref}/feedback", json={"category": "needs_investigation"}).status_code == 200


def test_idempotent_reformatted_and_concurrent_import(database, tmp_path):
    first = import_file(FIXTURE, "sensor-a", database)
    moved = tmp_path / "moved.jsonl"
    events = json.loads(FIXTURE.read_text())
    moved.write_text("\n".join(json.dumps(e) for e in reversed(events)), encoding="utf-8")
    assert first.staged == 2
    assert import_file(moved, "sensor-a", database).duplicate == 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: import_file(moved, "sensor-b", database), range(2)))
    assert sorted((r.staged, r.duplicate) for r in results) == [(0, 2), (2, 0)]
    assert inspect_inbox(database)["total"] == 4


def test_invalid_skipped_rejected_and_ground_truth_have_no_rows(database, tmp_path):
    event = json.loads(FIXTURE.read_text())[0]
    bad = {**event, "src_ip": "invalid"}
    truth_event = {**event, "unknown": {"nested": [{"groundTruth": "malicious"}]}}
    rejected = {**event, "alert": {**event["alert"], "severity": 99}}
    path = tmp_path / "mixed.jsonl"
    path.write_text("\n".join([json.dumps(e) for e in
                    [event, event, {"event_type": "flow"}, bad, truth_event, rejected, {}]] + ["{bad json"]), encoding="utf-8")
    result = import_file(path, "sensor-a", database)
    assert (result.parsed, result.staged, result.duplicate, result.skipped,
            result.invalid, result.rejected_by_policy) == (7, 1, 1, 1, 4, 1)
    assert inspect_inbox(database)["total"] == 1
    assert len(result.issues) == 6


def test_dry_run_and_inspection_are_read_only(database, tmp_path):
    before = database.read_bytes()
    result = import_file(FIXTURE, "sensor-a", database, dry_run=True)
    assert result.staged == 2 and result.dry_run
    assert inspect_inbox(database)["total"] == 0
    assert database.read_bytes() == before
    missing = tmp_path / "missing.db"
    assert import_file(FIXTURE, "sensor-a", missing, dry_run=True).staged == 2
    assert not missing.exists()
    with pytest.raises(sqlite3.OperationalError):
        import_file(FIXTURE, "sensor-a", missing)
    assert not missing.exists()


def test_canonical_row_is_immutable_even_without_recursive_triggers(database):
    import_file(FIXTURE, "sensor-a", database)
    with closing(sqlite3.connect(database)) as conn:
        before = conn.execute("SELECT * FROM external_alert_inbox").fetchall()
        for statement in [
            "UPDATE external_alert_inbox SET canonical_snapshot='{}'",
            "UPDATE external_alert_inbox SET proposed_operational_priority=0",
            "DELETE FROM external_alert_inbox",
            "INSERT OR REPLACE INTO external_alert_inbox SELECT * FROM external_alert_inbox",
        ]:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(statement)
            conn.rollback()
        assert conn.execute("SELECT * FROM external_alert_inbox").fetchall() == before


def test_infrastructure_failure_rolls_back_batch(database):
    with closing(db.connect(database)) as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON external_alert_inbox "
                     "WHEN NEW.native_severity=3 BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="test failure"):
            stage_file(conn, FIXTURE, "sensor-a")
        assert conn.execute("SELECT COUNT(*) FROM external_alert_inbox").fetchone()[0] == 0


@pytest.mark.parametrize("text", ['{"event_type":"alert","x":NaN}',
                                       '{"event_type":"alert","event_type":"flow"}', '[bad'])
def test_malformed_json_is_invalid(database, tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    report = import_file(path, "sensor-a", database)
    assert report.invalid == 1 and report.staged == 0


def test_cli_import_and_list(database):
    run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(FIXTURE),
                          "--sensor-id", "cli", "--database", str(database)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["staged"] == 2
    listing = subprocess.run([sys.executable, str(SCRIPT), "--database", str(database), "--list"],
                             capture_output=True, text=True)
    assert listing.returncode == 0, listing.stderr
    assert json.loads(listing.stdout)["operational_admission"] == "pending"
