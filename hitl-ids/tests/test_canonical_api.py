"""The additive API envelope survives real feedback and legacy migration."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from packages.contracts import db, models as m
from packages.detection.fusion.cef import FusionConfig
from packages.detection.pipeline import store
from test_api import client, database, rows  # noqa: F401
from test_contracts import FAMILY_KEY, T0, make_alert


def test_api_snapshot_survives_feedback(client):
    ref = rows(client, limit=1)[0]["alertRef"]
    before = client.get(f"/api/alerts/{ref}").json()
    assert before["detector"]["canonicalAlertId"] == ref
    assert before["detector"]["confidence"] is not None
    response = client.post(f"/api/alerts/{ref}/feedback",
                           json={"category": "needs_investigation", "note": "Inspect evidence"})
    assert response.status_code == 200
    after = client.get(f"/api/alerts/{ref}").json()
    assert after["detector"] == before["detector"]
    assert after["feedbackCount"] == before["feedbackCount"] + 1


def test_snapshot_cannot_be_deleted_or_replaced(client, database):
    ref = rows(client, limit=1)[0]["alertRef"]
    conn = sqlite3.connect(database)  # prove replacement protection without recursive_triggers
    for sql in (
        "DELETE FROM alerts WHERE alert_ref = ?",
        "INSERT OR REPLACE INTO alerts SELECT * FROM alerts WHERE alert_ref = ?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(sql, (ref,))
        conn.rollback()
    conn.close()


def test_migration_preserves_existing_rows_and_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "legacy.db")
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.executescript(db.MIGRATIONS[0][2])
    conn.execute("PRAGMA user_version = 1")
    dataset_id = store.register_dataset(
        conn, name="legacy", version="1", source_file="old.csv", total_records=1,
        class_distribution={}, now=T0)
    store.register_model(conn, version="legacy-model", model_file="fixture", now=T0)
    run_id = store.start_run(
        conn, dataset_id=dataset_id, model_version="legacy-model", rule_set_version="legacy-rule",
        fusion_weights=FusionConfig().snapshot(), guardrail_config={}, now=T0)
    user_id = db.insert(conn, m.User(
        username="legacy-analyst", password_hash="fixture", display_name="Legacy Analyst",
        email="legacy@example.test", role="security_analyst", created_at=T0))
    alert = make_alert(dataset_id, run_id, combined_score=70, severity="Medium",
                       owner_id=user_id, status="in_progress", family_key=FAMILY_KEY,
                       queue_class="tier2_candidate", queue_priority=0, requires_review=True)
    # Serialize with today's contract, but insert only columns present in the legacy schema.
    row = db.to_row(alert)
    row.pop("detector")
    row.pop("id")
    columns = list(row)
    alert_id = conn.execute(
        f"INSERT INTO alerts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [row[column] for column in columns]).lastrowid
    db.insert(conn, m.FlowRecord(
        alert_id=alert_id, source_record_id="legacy-record", src_ip="192.0.2.1",
        dst_ip="198.51.100.1", src_port=51514, dst_port=22, protocol="TCP",
        duration=1, packets=2, bytes=10,
        flow_features={"Timestamp": "2018-02-14 12:28:54.334391"}))
    feedback_id = db.insert(conn, m.FeedbackEvent(
        alert_id=alert_id, user_id=user_id, category="mark_false_positive",
        original_score=92, requested_delta=-30, actual_delta=-22,
        guardrail_action="capped", guardrail_reason="critical_alert_floor", created_at=T0))
    db.insert(conn, m.AuditEntry(
        event_type="FEEDBACK", actor_id=user_id, alert_id=alert_id, feedback_id=feedback_id,
        details={"legacy": True}, created_at=T0))
    conn.commit()
    tables = ("datasets", "alerts", "flow_data", "feedback_events", "audit_log")
    before = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
              for table in tables}
    assert db.migrate(conn) == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    migrated = dict(conn.execute("SELECT * FROM alerts").fetchone())
    assert migrated.pop("detector") is None
    assert migrated == before["alerts"][0]
    for table in tables:
        if table != "alerts":
            assert [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")] == before[table]
    assert db.migrate(conn) == []
    assert dict(conn.execute("SELECT * FROM alerts").fetchone()) == {**migrated, "detector": None}
    assert "detector" in {r["name"] for r in conn.execute("PRAGMA table_info(alerts)")}
    conn.close()


def test_concurrent_first_requests_can_migrate_the_same_database(tmp_path):
    path = tmp_path / "concurrent.db"
    conn = db.connect(path)
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()
    ready = Barrier(2)

    def upgrade():
        connection = db.connect(path)
        try:
            ready.wait(timeout=5)
            db.migrate(connection)
            return connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: upgrade(), range(2))) == [db.SCHEMA_VERSION] * 2
