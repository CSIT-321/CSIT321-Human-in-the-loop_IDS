"""Console rebuild backend (B1, B2, B4, B5, B6): status and ownership, notes, the queue's new filters,
breakdowns and the IP entity view — driven over HTTP, plus the migration that adds notes.

Status is workflow, not judgement: these tests also pin that a status change never moves a score.
"""

from __future__ import annotations

import sqlite3

import pytest

from packages.contracts import db
from test_api import client, database, rows  # noqa: F401  (shared fixtures)

ANALYST = {"X-Demo-Role": "security_analyst"}
ADMIN = {"X-Demo-Role": "system_admin"}
EVALUATOR = {"X-Demo-Role": "evaluator"}


def status(client, ref, to, headers=ANALYST):  # noqa: F811
    return client.post(f"/api/alerts/{ref}/status", json={"status": to}, headers=headers)


def assign(client, ref, owner, headers=ANALYST):  # noqa: F811
    return client.post(f"/api/alerts/{ref}/assign", json={"owner": owner}, headers=headers)


# --------------------------------------------------------------------------------------------
# Migration
# --------------------------------------------------------------------------------------------

def test_a_fresh_database_is_created_at_the_current_schema_version(tmp_path):
    conn = db.connect(tmp_path / "fresh.db")
    db.create_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'alert_notes'").fetchone()
    assert db.migrate(conn) == []  # idempotent
    conn.close()


def test_a_database_from_before_the_migration_is_upgraded_in_place(tmp_path):
    """Exactly the demo database built before notes existed: schema.sql only, user_version 0."""
    conn = db.connect(tmp_path / "old.db")
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert db.migrate(conn) == [1]
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'alert_notes'").fetchone()
    conn.close()


def test_notes_are_append_only_at_the_database(client, database):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.post(f"/api/alerts/{ref}/notes", json={"body": "first look"},
                       headers=ANALYST).status_code == 200
    conn = db.connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE alert_notes SET body = 'rewritten'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM alert_notes")
    finally:
        conn.close()


# --------------------------------------------------------------------------------------------
# Status and ownership (B1)
# --------------------------------------------------------------------------------------------

def test_claiming_an_alert_makes_the_caller_its_owner_and_is_audited(client):  # noqa: F811
    row = rows(client, limit=1)[0]
    assert row["status"] == "new" and row["owner"] is None
    response = status(client, row["alertRef"], "claimed")
    assert response.status_code == 200, response.text
    alert = response.json()["alert"]
    assert alert["status"] == "claimed"
    assert alert["owner"]["role"] == "security_analyst"
    assert alert["combinedScore"] == row["combinedScore"]  # workflow never moves a score

    audit = client.get("/api/audit-log", params={"eventType": ["ALERT_STATUS_CHANGE"]},
                       headers=ADMIN).json()["items"]
    assert audit[0]["alertRef"] == row["alertRef"]
    assert audit[0]["details"]["from_status"] == "new"
    assert audit[0]["details"]["to_status"] == "claimed"
    assert audit[0]["eventId"] == response.json()["auditEventId"]


def test_releasing_an_alert_clears_its_owner(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    status(client, ref, "in_progress")
    released = status(client, ref, "new").json()["alert"]
    assert released["status"] == "new" and released["owner"] is None


@pytest.mark.parametrize(("first", "then"), [
    ("resolved", "claimed"),     # a closed alert reopens only to in_progress
    ("dismissed", "new"),
    ("claimed", "claimed"),      # no-op changes are refused, not silently accepted
])
def test_a_refused_transition_is_a_conflict(client, first, then):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    assert status(client, ref, first).status_code == 200
    refused = status(client, ref, then)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "CONFLICT"


def test_a_closed_alert_can_be_reopened(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    status(client, ref, "resolved")
    assert status(client, ref, "in_progress").json()["alert"]["status"] == "in_progress"


def test_assigning_claims_a_new_alert_and_unassigning_releases_it(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    claimed = assign(client, ref, "me").json()["alert"]
    assert claimed["status"] == "claimed" and claimed["owner"]["role"] == "security_analyst"
    released = assign(client, ref, None).json()["alert"]
    assert released["status"] == "new" and released["owner"] is None


def test_a_closed_alert_cannot_be_reassigned(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    status(client, ref, "dismissed")
    assert assign(client, ref, "me").status_code == 409


def test_the_evaluator_cannot_triage(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    assert status(client, ref, "claimed", headers=EVALUATOR).status_code == 403
    assert client.post(f"/api/alerts/{ref}/notes", json={"body": "x"},
                       headers=EVALUATOR).status_code == 403


def test_the_owner_filter_finds_my_alerts_and_the_unassigned_ones(client):  # noqa: F811
    mine = rows(client, limit=1)[0]["alertRef"]
    assert rows(client, owner="me", limit=50) == []  # a role that never acted owns nothing
    assign(client, mine, "me")
    assert [r["alertRef"] for r in rows(client, owner="me", limit=50)] == [mine]
    assert mine not in {r["alertRef"] for r in rows(client, owner="unassigned", limit=200)}


# --------------------------------------------------------------------------------------------
# Notes (B2)
# --------------------------------------------------------------------------------------------

def test_notes_form_a_thread_oldest_first_with_their_author(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    for body in ("Checked the destination: internal web server.", "No exploit payload found."):
        assert client.post(f"/api/alerts/{ref}/notes", json={"body": body},
                           headers=ANALYST).status_code == 200
    thread = client.get(f"/api/alerts/{ref}/notes").json()
    assert [n["body"] for n in thread["notes"]] == [
        "Checked the destination: internal web server.", "No exploit payload found."]
    assert thread["notes"][0]["author"]["role"] == "security_analyst"


@pytest.mark.parametrize("body", ["", "   "])
def test_an_empty_note_is_refused(client, body):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    response = client.post(f"/api/alerts/{ref}/notes", json={"body": body}, headers=ANALYST)
    assert response.status_code in (400, 422)
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------------------------
# Queue additions (B6)
# --------------------------------------------------------------------------------------------

def test_the_verdict_filter_uses_the_verdict_in_force(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    client.post(f"/api/alerts/{ref}/feedback", json={"category": "needs_investigation"})
    client.post(f"/api/alerts/{ref}/feedback", json={"category": "mark_false_positive"})
    in_force = {r["alertRef"] for r in rows(client, verdict=["mark_false_positive"], limit=200)}
    superseded = {r["alertRef"] for r in rows(client, verdict=["needs_investigation"], limit=200)}
    assert ref in in_force and ref not in superseded


def test_rows_carry_capture_time_and_family_size(client):  # noqa: F811
    row = rows(client, limit=1)[0]
    assert row["flowTime"] and row["flowTime"][:4].isdigit()
    detail = client.get(f"/api/alerts/{row['alertRef']}").json()
    assert row["familySize"] == detail["family"]["members"]


def test_the_capture_time_filter_bounds_the_queue(client):  # noqa: F811
    first_day = min(r["flowTime"] for r in rows(client, limit=200))[:10]
    same_day = rows(client, flowFrom=first_day, flowTo=first_day, limit=200)
    assert same_day and all(r["flowTime"].startswith(first_day) for r in same_day)
    assert rows(client, flowFrom="2999-01-01", limit=200) == []
    assert client.get("/api/alerts", params={"flowFrom": "yesterday"}).status_code in (400, 422)


# --------------------------------------------------------------------------------------------
# Breakdowns (B4) and the entity view (B5)
# --------------------------------------------------------------------------------------------

def test_breakdowns_account_for_every_alert(client):  # noqa: F811
    body = client.get("/api/dashboard/breakdowns", params={"limit": 3}).json()
    total = client.get("/api/dashboard/summary").json()["totalAlerts"]
    assert sum(bucket["count"] for bucket in body["flowTimeHistogram"]) == total
    assert len(body["topSourceIps"]) <= 3
    assert sum(body["statusMix"].values()) == total
    assert all(entry["flagged"] <= entry["count"] for entry in body["topDestinationPorts"])


def test_breakdowns_count_the_verdicts_in_force(client):  # noqa: F811
    ref = rows(client, limit=1)[0]["alertRef"]
    client.post(f"/api/alerts/{ref}/feedback", json={"category": "mark_false_positive"})
    body = client.get("/api/dashboard/breakdowns").json()
    assert body["verdictMix"].get("mark_false_positive") == 1


def test_the_entity_view_describes_an_address(client):  # noqa: F811
    row = rows(client, limit=1)[0]
    body = client.get(f"/api/entities/ip/{row['srcIp']}").json()
    assert body["alerts"] >= 1 and body["asSource"] >= 1
    assert body["alerts"] == sum(body["byQueueClass"].values())
    assert body["firstSeen"] <= body["lastSeen"]


def test_the_entity_view_refuses_a_non_address_and_reports_an_unseen_one(client):  # noqa: F811
    assert client.get("/api/entities/ip/not-an-ip").status_code == 400
    missing = client.get("/api/entities/ip/203.0.113.9")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"
