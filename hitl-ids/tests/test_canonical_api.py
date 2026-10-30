"""The additive API envelope survives real feedback and legacy migration."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from packages.contracts import db
from test_api import client, database, rows  # noqa: F401


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
    conn.execute("INSERT INTO datasets (name, version, source_file, total_records, class_distribution) "
                 "VALUES ('legacy', '1', 'old.csv', 0, '{}')")
    conn.commit()
    before = tuple(conn.execute("SELECT * FROM datasets").fetchone())
    assert db.migrate(conn) == [2]
    assert tuple(conn.execute("SELECT * FROM datasets").fetchone()) == before
    assert db.migrate(conn) == []
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
        assert list(pool.map(lambda _: upgrade(), range(2))) == [2, 2]
