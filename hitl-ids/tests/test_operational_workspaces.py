"""Real staging/admission and durable, backend-enforced workspace isolation."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.requests import Request

from apps.api.main import create_app
from apps.api import auth
from apps.api import workspaces
from apps.api.workspaces import WORKLOAD
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.analyst_work import read_work
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)


def _client(tmp_path: Path) -> tuple[TestClient, Path, dict[str, dict[str, str]]]:
    operational = tmp_path / "operational.db"
    with db.connect(operational) as conn:
        db.create_schema(conn)
    client = TestClient(create_app(operational))
    tokens = {}
    for role, username, password in (("admin", "admin", "admin-demo"),
                                      ("analyst", "g.ang", "analyst-demo"),
                                      ("evaluator", "evaluator", "evaluator-demo")):
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        tokens[role] = {"Authorization": f"Bearer {response.json()['token']}"}
    return client, operational, tokens


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_workspace_rbac_and_allowlist(tmp_path):
    client, operational, tokens = _client(tmp_path)
    body = {"reason": "Test isolated workspace setup"}
    for role in ("analyst", "evaluator"):
        assert client.get("/api/admin/workspaces", headers=tokens[role]).status_code == 403
        for path in ("/api/admin/workspaces/v3-1-replay/prepare",
                     "/api/admin/workspaces/v3-1-replay/reset",
                     "/api/admin/workspaces/operational/activate"):
            assert client.post(path, headers=tokens[role], json=body).status_code == 403
    assert client.get("/api/workspace/current", headers=tokens["analyst"]).json() == {
        "id": "operational", "name": "Operational"}
    assert client.post("/api/admin/workspaces/../../escape/activate", headers=tokens["admin"], json=body).status_code in (404, 405)
    assert client.post("/api/admin/workspaces/invalid/activate", headers=tokens["admin"], json=body).status_code == 404
    assert not (tmp_path / "workspaces/v3-1-replay.db").exists()


def test_failed_replay_preparation_creates_no_partial_database(tmp_path, monkeypatch):
    client, operational, tokens = _client(tmp_path)
    initial = _hash(operational)
    malformed = tmp_path / "invalid-workload.jsonl"
    malformed.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(workspaces, "WORKLOAD", malformed)
    response = client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"],
                           json={"reason": "Reject incomplete workload"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "REPLAY_WORKLOAD_INVALID"
    assert not (tmp_path / "workspaces/v3-1-replay.db").exists()
    assert not list((tmp_path / "workspaces").glob(".v3-1-prepare-*.db"))
    assert _hash(operational) == initial


def test_each_request_keeps_its_selected_database(tmp_path):
    client, operational, tokens = _client(tmp_path)
    app = client.app
    request = Request({"type": "http", "app": app, "method": "GET", "path": "/api/v2/alerts",
                       "headers": [], "query_string": b""})
    assert workspaces.active_database(request) == operational
    _, control, replay = workspaces.paths(request)
    with closing(workspaces._control(control, create=True)) as conn:
        conn.execute("UPDATE selection SET workspace='v3-1-replay' WHERE id=1")
        conn.commit()
    assert workspaces.active_database(request) == operational
    next_request = Request({"type": "http", "app": app, "method": "GET", "path": "/api/v2/alerts",
                            "headers": [], "query_string": b""})
    assert workspaces.active_database(next_request) == replay


def test_signed_account_resolves_across_different_local_user_ids(tmp_path):
    operational = tmp_path / "operational.db"
    with closing(db.connect(operational)) as conn:
        db.create_schema(conn)
        db.insert(conn, m.User(username="extra", password_hash=auth.hash_password("extra-password"),
                               display_name="Extra", email="extra@demo.local", role="security_analyst"))
        conn.commit()
    client = TestClient(create_app(operational))
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin-demo"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    body = {"reason": "Account identity across workspace databases"}
    assert client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=headers, json=body).status_code == 200
    replay = tmp_path / "workspaces/v3-1-replay.db"
    with closing(sqlite3.connect(operational)) as conn:
        op_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    with closing(sqlite3.connect(replay)) as conn:
        replay_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    assert op_id != replay_id
    assert client.post("/api/admin/workspaces/v3-1-replay/activate", headers=headers, json=body).status_code == 200
    assert client.get("/api/admin/workspaces", headers=headers).status_code == 200


def test_prepare_switch_and_reset_preserve_operational(tmp_path):
    client, operational, tokens = _client(tmp_path)
    initial = _hash(operational)
    body = {"reason": "Prepare interactive V3.1 workload for analyst demo"}
    response = client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"], json=body)
    assert response.status_code == 200, response.text
    replay = tmp_path / "workspaces/v3-1-replay.db"
    assert replay.exists()
    assert _hash(operational) == initial
    status = response.json()
    assert status["activeWorkspaceId"] == "operational"
    replay_status = status["workspaces"][1]
    assert replay_status["rawRecords"] == 200
    assert replay_status["stagedAlerts"] == 200
    assert replay_status["alertCount"] == 200
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0] == 200
        assert conn.execute("SELECT count(*) FROM tier2_cases").fetchone()[0] == 10
        assert conn.execute("SELECT count(*) FROM analyst_verdict_events").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM prospective_runs").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None
    response = client.post("/api/admin/workspaces/v3-1-replay/activate", headers=tokens["admin"], json=body)
    assert response.status_code == 200, response.text
    assert client.get("/api/workspace/current", headers=tokens["analyst"]).json()["id"] == "v3-1-replay"
    alerts = client.get("/api/v2/alerts?limit=1", headers=tokens["analyst"])
    assert alerts.status_code == 200, alerts.text
    assert alerts.json()["page"]["total"] == 200
    response = client.post("/api/admin/workspaces/operational/activate", headers=tokens["admin"], json=body)
    assert response.status_code == 200, response.text
    assert client.get("/api/v2/alerts?limit=1", headers=tokens["analyst"]).json()["page"]["total"] == 0
    assert _hash(operational) == initial
    response = client.post("/api/admin/workspaces/v3-1-replay/reset", headers=tokens["admin"], json=body)
    assert response.status_code == 200, response.text
    assert not replay.exists()
    assert _hash(operational) == initial


def test_admin_reset_supersedes_an_active_replay_and_open_claims(tmp_path):
    """The Administrator resets Replay in one action, even while it is active and an Analyst holds a claim."""
    client, operational, tokens = _client(tmp_path)
    initial = _hash(operational)
    body = {"reason": "Reset during a demo"}
    assert client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"], json=body).status_code == 200
    assert client.post("/api/admin/workspaces/v3-1-replay/activate", headers=tokens["admin"], json=body).status_code == 200
    replay = tmp_path / "workspaces/v3-1-replay.db"
    ref = _claimable(client, replay, tokens["analyst"])
    claim = client.post(f"/api/v2/alerts/{ref}/work/claim", headers=tokens["analyst"],
                        json={"requestId": str(uuid4()), "expectedRevision": 0})
    assert claim.status_code == 200 and claim.json()["outcome"] == "claimed", claim.text

    response = client.post("/api/admin/workspaces/v3-1-replay/reset", headers=tokens["admin"], json=body)

    assert response.status_code == 200, response.text
    status = response.json()
    assert status["activeWorkspaceId"] == "operational"
    assert status["workspaces"][1]["ready"] is False and not replay.exists()
    assert client.get("/api/workspace/current", headers=tokens["analyst"]).json()["id"] == "operational"
    assert client.get("/api/v2/alerts/summary", headers=tokens["analyst"]).json()["totalAlerts"] == 0
    actions = [(a["action"], a["workspace"], a["reason"]) for a in status["actions"][:2]]
    assert actions[0][0] == "replay_reset" and "released 1 open Analyst claim" in actions[0][2]
    assert actions[1][:2] == ("workspace_activated", "operational")
    assert _hash(operational) == initial


def test_reset_waits_for_in_flight_requests_then_refuses_cleanly(tmp_path, monkeypatch):
    """A handle that never closes ends in a clear 409 after the drain window, with nothing reset."""
    import pathlib
    operational = tmp_path / 'operational.db'
    operational.touch()
    directory = tmp_path / 'workspaces'
    directory.mkdir()
    replay = directory / 'v3-1-replay.db'
    replay.write_bytes(b'')
    with closing(workspaces._control(directory / 'control.db', create=True)) as conn:
        conn.execute("UPDATE selection SET workspace='operational' WHERE id=1")
        conn.commit()
    original = pathlib.Path.unlink

    def held(self, *args, **kwargs):
        if self == replay:
            raise PermissionError(13, 'in use')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'unlink', held)
    monkeypatch.setattr(workspaces, 'DRAIN_SECONDS', 0.6)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_path=str(operational))))
    try:
        workspaces.reset(request, 'admin', 'Held handle')
    except workspaces.ApiError as exc:
        assert exc.status_code == 409 and exc.code == 'REPLAY_IN_USE'
    else:
        raise AssertionError('reset must refuse while the file stays open')
    assert replay.exists()


def _one_operational_alert(operational: Path, tmp_path: Path) -> None:
    source = tmp_path / "one-real-eve-record.jsonl"
    source.write_text(WORKLOAD.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with closing(db.connect(operational)) as conn:
        auth.ensure_demo_accounts(conn)
        actor = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        report = stage_file(conn, source, "one-operational-alert", capture_scope="one-operational-alert")
        assert report.staged == 1
        inbox_id = conn.execute("SELECT id FROM external_alert_inbox").fetchone()[0]
        review = review_eligibility(conn, inbox_id, actor_id=actor, request=EligibilityRequest(
            requestId=uuid4(), expectedReviewId=None, decision="accepted", reason="Isolated workspace test"))
        admit_external(conn, inbox_id, actor_id=actor, request=AdmissionRequest(
            requestId=uuid4(), expectedReviewId=review["id"], reason="Isolated workspace test"))


def _claimable(client: TestClient, database: Path, analyst_headers: dict[str, str]) -> str:
    with closing(db.connect(database)) as conn:
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        refs = [row[0] for row in conn.execute("SELECT operational_alert_ref FROM operational_alerts_v2")]
        for ref in refs:
            alert_id = conn.execute("SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?", (ref,)).fetchone()[0]
            if read_work(conn, alert_id, actor).can_claim:
                response = client.get(f"/api/v2/alerts/{ref}/work", headers=analyst_headers)
                assert response.status_code == 200 and response.json()["canClaim"]
                return ref
    raise AssertionError("No Tier 1 claimable alert in workspace")


def test_claim_selection_is_bound_to_the_queue_workspace(tmp_path):
    client, operational, tokens = _client(tmp_path)
    _one_operational_alert(operational, tmp_path)
    queue = client.get('/api/v2/alerts', headers=tokens['analyst'])
    assert queue.status_code == 200
    assert queue.headers['X-Operational-Workspace'] == 'operational'
    reason = {'reason': 'Test workspace change before claim'}
    assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=reason).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=reason).status_code == 200
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    ref = _claimable(client, replay, tokens['analyst'])
    work = client.get(f'/api/v2/alerts/{ref}/work', headers=tokens['analyst'])
    assert work.status_code == 200 and work.headers['X-Operational-Workspace'] == 'v3-1-replay'
    rejected = client.post(f'/api/v2/alerts/{ref}/work/claim',
                           headers={**tokens['analyst'], 'X-Operational-Workspace': queue.headers['X-Operational-Workspace']},
                           json={'requestId': str(uuid4()), 'expectedRevision': work.json()['revision']})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'WORKSPACE_CHANGED'
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM analyst_claim_intents').fetchone()[0] == 0
    with closing(sqlite3.connect(operational)) as conn:
        assert conn.execute('SELECT count(*) FROM analyst_claim_intents').fetchone()[0] == 0


def test_analyst_claims_stay_in_selected_database_and_oracle_is_absent(tmp_path):
    client, operational, tokens = _client(tmp_path)
    _one_operational_alert(operational, tmp_path)
    operational_before = _hash(operational)
    body = {"reason": "Isolated Analyst claim test"}
    assert client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"], json=body).status_code == 200
    replay = tmp_path / "workspaces/v3-1-replay.db"
    replay_before = _hash(replay)
    assert client.post("/api/admin/workspaces/v3-1-replay/activate", headers=tokens["admin"], json=body).status_code == 200
    ref = _claimable(client, replay, tokens["analyst"])
    alert = client.get(f"/api/v2/alerts/{ref}/evidence", headers=tokens["analyst"])
    assert alert.status_code == 200
    assert "oracle" not in alert.text.lower() and "safe_deferral" not in alert.text.lower()
    claim = client.post(f"/api/v2/alerts/{ref}/work/claim", headers=tokens["analyst"],
                        json={"requestId": str(uuid4()), "expectedRevision": 0})
    assert claim.status_code == 200, claim.text
    assert claim.json()["outcome"] == "claimed"
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute("SELECT count(*) FROM analyst_claim_intents").fetchone()[0] == 1
    assert _hash(operational) == operational_before
    replay_after_claim = _hash(replay)
    assert replay_after_claim != replay_before
    assert client.post("/api/admin/workspaces/operational/activate", headers=tokens["admin"], json=body).status_code == 200
    op_ref = _claimable(client, operational, tokens["analyst"])
    claim = client.post(f"/api/v2/alerts/{op_ref}/work/claim", headers=tokens["analyst"],
                        json={"requestId": str(uuid4()), "expectedRevision": 0})
    assert claim.status_code == 200, claim.text
    with closing(sqlite3.connect(operational)) as conn:
        assert conn.execute("SELECT count(*) FROM analyst_claim_intents").fetchone()[0] == 1
    assert _hash(replay) == replay_after_claim


def _legacy_control(path, flow_chain=None):
    """A control.db as an older install left it: no settings table, maybe a stored per-replay switch."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE selection (id INTEGER PRIMARY KEY CHECK (id=1), workspace TEXT NOT NULL);
        INSERT INTO selection VALUES (1,'v3-1-replay');
        CREATE TABLE presentation (id INTEGER PRIMARY KEY CHECK(id=1), cursor INTEGER NOT NULL,
            initial_holdout INTEGER NOT NULL, arrival_order TEXT NOT NULL, playback_state TEXT NOT NULL,
            next_due_at TEXT, last_arrival_at TEXT, preparing_admin TEXT NOT NULL);
        INSERT INTO presentation VALUES (1,0,0,'[]','running',NULL,NULL,'admin');
    """)
    if flow_chain is not None:
        conn.execute("ALTER TABLE presentation ADD COLUMN flow_chain INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE presentation SET flow_chain=?", (flow_chain,))
    conn.commit()
    conn.close()


def test_tick_migrates_a_control_file_that_predates_the_program_setting(tmp_path):
    """The 0.5 s playback tick opens the control file read-only for schema purposes. It must still find
    every table it uses, or an older install's playback pauses on an OperationalError."""
    operational = tmp_path / 'operational.db'
    operational.touch()
    directory = tmp_path / 'workspaces'
    directory.mkdir()
    _legacy_control(directory / 'control.db')

    workspaces.tick(operational)

    with closing(sqlite3.connect(directory / 'control.db')) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key='flow_chain_enabled'").fetchone()[0] == '1'
        reason = conn.execute("SELECT reason FROM actions WHERE action='presentation_playback_paused' "
                              "ORDER BY id DESC LIMIT 1").fetchone()
    # It got past the settings lookup into the replay work: the pause names the missing replay, not a schema error.
    assert reason and 'PRESENTATION_NOT_PREPARED' in reason[0] and 'OperationalError' not in reason[0]


def test_a_stored_off_switch_is_adopted_once(tmp_path):
    """A replay prepared while the switch sat on the presentation row keeps its choice on upgrade."""
    operational = tmp_path / 'operational.db'
    operational.touch()
    directory = tmp_path / 'workspaces'
    directory.mkdir()
    _legacy_control(directory / 'control.db', flow_chain=0)

    with closing(workspaces._control(directory / 'control.db')) as conn:
        assert workspaces.detection(conn)['flowChainEnabled'] is False


def test_reset_retries_a_transient_handle(tmp_path, monkeypatch):
    """Windows keeps a reader's handle briefly after its request. Reset retries, then succeeds."""
    import pathlib
    operational = tmp_path / 'operational.db'
    operational.touch()
    directory = tmp_path / 'workspaces'
    directory.mkdir()
    replay = directory / 'v3-1-replay.db'
    replay.write_bytes(b'')
    with closing(workspaces._control(directory / 'control.db', create=True)) as conn:
        conn.execute("UPDATE selection SET workspace='operational' WHERE id=1")
        conn.commit()
    original = pathlib.Path.unlink
    attempts = {'n': 0}

    def flaky(self, *args, **kwargs):
        if self == replay and attempts['n'] < 2:
            attempts['n'] += 1
            raise PermissionError(13, 'in use')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'unlink', flaky)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_path=str(operational))))
    workspaces.reset(request, 'admin', 'Retry test')
    assert attempts['n'] == 2 and not replay.exists()


def test_remove_database_takes_the_wal_and_shm_with_it(tmp_path):
    target = tmp_path / "replay.db"
    target.write_bytes(b"main")
    Path(str(target) + "-wal").write_bytes(b"stale wal")
    Path(str(target) + "-shm").write_bytes(b"stale shm")
    workspaces._remove_database(target)
    assert not target.exists()
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()


def test_prepare_accepts_a_stale_presentation_row(tmp_path):
    if not workspaces.packet_replay.available():
        import pytest
        pytest.skip("packet replay data is a local build artefact")
    client, operational, tokens = _client(tmp_path)
    body = {"reason": "Packet replay recovery", "mode": "packet"}
    assert client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"], json=body).status_code == 200
    control = tmp_path / "workspaces/control.db"
    with closing(sqlite3.connect(control)) as conn:
        conn.execute("INSERT OR REPLACE INTO presentation VALUES "
                     "(1,0,0,'[]','paused',NULL,NULL,'admin','packet',1)")
        conn.commit()
    assert client.post("/api/admin/workspaces/v3-1-replay/reset", headers=tokens["admin"],
                       json={"reason": "Clear the replay"}).status_code == 200
    replay = tmp_path / "workspaces/v3-1-replay.db"
    for suffix in ("", "-wal", "-shm"):
        assert not Path(str(replay) + suffix).exists()
    assert client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"], json=body).status_code == 200
