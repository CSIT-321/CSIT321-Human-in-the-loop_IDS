"""S18a — real sign-in: bcrypt accounts, JWT bearers, RBAC.

What the role-switch stub could never test, this file must: that each account gets only its own
role, that a token is checked rather than trusted, and that every database self-heals its accounts
the way it self-heals its schema.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db

from test_api import client, database, rows  # noqa: F401  (shared fixtures)

ACCOUNTS = [
    ("g.ang", "analyst-demo", "security_analyst"),
    ("admin", "admin-demo", "system_admin"),
    ("evaluator", "evaluator-demo", "evaluator"),
]


def login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# --------------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("username", "password", "role"), ACCOUNTS)
def test_each_seeded_account_signs_in_with_its_own_role(client, username, password, role):
    response = login(client, username, password)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["username"], body["role"]) == (username, role)
    assert body["token"]


def test_a_wrong_password_and_an_unknown_user_answer_identically(client):
    wrong_password = login(client, "g.ang", "admin-demo")
    unknown_user = login(client, "nobody", "whatever")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"] == unknown_user.json()["error"]


def test_a_successful_sign_in_records_last_login(client, database):
    assert login(client, "admin", "admin-demo").status_code == 200
    conn = db.connect(str(database))
    try:
        row = conn.execute("SELECT last_login FROM users WHERE username = 'admin'").fetchone()
        assert row["last_login"] is not None
    finally:
        conn.close()


def test_a_disabled_account_cannot_sign_in(client, database):
    conn = db.connect(str(database))
    try:
        with conn:
            conn.execute("UPDATE users SET status = 'inactive' WHERE username = 'admin'")
    finally:
        conn.close()
    assert login(client, "admin", "admin-demo").status_code == 401


# --------------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------------

def test_the_token_names_the_account(client):
    token = login(client, "g.ang", "analyst-demo").json()["token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"username": "g.ang", "displayName": "Glenn Ang",
                               "role": "security_analyst"}


def test_no_token_is_refused(database):
    bare = TestClient(create_app(database))
    response = bare.get("/api/alerts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_a_tampered_token_is_refused(client):
    token = client.tokens["g.ang"]
    assert token[-4:] != "AAAA"
    response = client.get("/api/alerts", headers={"Authorization": f"Bearer {token[:-4]}AAAA"})
    assert response.status_code == 401


def test_an_expired_sign_in_is_refused(client):
    claims = pyjwt.decode(client.tokens["admin"], auth.DEV_SECRET, algorithms=["HS256"])
    claims["exp"] = int(time.time()) - 10
    expired = pyjwt.encode(claims, auth.DEV_SECRET, algorithm="HS256")
    response = client.get("/api/alerts", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


# --------------------------------------------------------------------------------------------
# RBAC — the matrix the stub could only pretend to have checked
# --------------------------------------------------------------------------------------------

def test_the_analyst_cannot_admin_and_the_evaluator_cannot_triage(client):
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.put("/api/config/guardrails",
                      json={"criticalAlertFloor": 50, "rationale": "x"},
                      headers={"Authorization": f"Bearer {client.tokens['g.ang']}"}).status_code == 403
    assert client.post(f"/api/alerts/{ref}/status", json={"status": "claimed"},
                       headers={"Authorization": f"Bearer {client.tokens['evaluator']}"
                               }).status_code == 403
    assert client.post(f"/api/alerts/{ref}/notes", json={"body": "x"},
                       headers={"Authorization": f"Bearer {client.tokens['evaluator']}"
                               }).status_code == 403


def test_every_account_can_read_the_queue_it_owns_a_view_of(client):
    for username in ("g.ang", "admin", "evaluator"):
        response = client.get("/api/alerts", params={"limit": 1},
                              headers={"Authorization": f"Bearer {client.tokens[username]}"})
        assert response.status_code == 200, username


def test_a_verdict_is_attributed_to_the_signed_in_account(client):
    ref = rows(client, limit=1)[0]["alertRef"]
    assert client.post(f"/api/alerts/{ref}/feedback",
                       json={"category": "needs_investigation"},
                       headers={"Authorization": f"Bearer {client.tokens['admin']}"}).status_code == 200
    history = client.get(f"/api/alerts/{ref}/feedback-history").json()
    assert history["events"][-1]["actor"]["displayName"] == "System Administrator"


# --------------------------------------------------------------------------------------------
# Seeding — every database self-heals its accounts
# --------------------------------------------------------------------------------------------

def test_seeding_is_idempotent(database):
    conn = db.connect(str(database))
    try:
        auth.ensure_demo_accounts(conn)
        auth.ensure_demo_accounts(conn)
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE username IN ('g.ang', 'admin', 'evaluator')"
        ).fetchone()["n"]
        assert count == 3
    finally:
        conn.close()


def test_a_fresh_database_seeds_on_first_sign_in(database):
    """No seeding hook, no startup event: the first login against an empty users table works."""
    bare = TestClient(create_app(database))
    response = bare.post("/api/auth/login",
                         json={"username": "evaluator", "password": "evaluator-demo"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "evaluator"
