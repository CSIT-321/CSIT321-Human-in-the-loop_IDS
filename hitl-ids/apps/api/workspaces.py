"""Durable, allowlisted operational workspace selection and isolated replay preparation.

Every request snapshots the active workspace before opening its operational connection.
An in-flight request finishes against that same connection after a switch; the next
request resolves the newly active workspace. Control state is never stored in either
operational database.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import Request

from apps.api import auth
from apps.api.deps import ApiError, database_path
from packages.contracts import db
from packages.detection.adapters.staging import stage_file
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)

REPOSITORY = Path(__file__).resolve().parents[3]
WORKLOAD = REPOSITORY / "evaluation/protocol-v3.1/workload/operational-workload.jsonl"
IDS = ("operational", "v3-1-replay")
NAMES = {"operational": "Operational", "v3-1-replay": "V3.1 Demo Replay"}


def paths(request: Request) -> tuple[Path, Path, Path]:
    operational = Path(getattr(request.app.state, "database_path", None) or database_path()).resolve()
    directory = operational.parent / "workspaces"
    return operational, directory / "control.db", directory / "v3-1-replay.db"


def _control(path: Path, *, create: bool = False) -> sqlite3.Connection | None:
    if not create and not path.exists():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if create:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS selection (id INTEGER PRIMARY KEY CHECK (id=1), workspace TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS replay_meta (id INTEGER PRIMARY KEY CHECK (id=1), prepared_at TEXT NOT NULL,
            raw_records INTEGER NOT NULL, staged_alerts INTEGER NOT NULL, operational_alerts INTEGER NOT NULL,
            workload_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
            workspace TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT OR IGNORE INTO selection(id,workspace) VALUES (1,'operational');
        """)
    return conn


def active_id(control: Path) -> str:
    conn = _control(control)
    if conn is None:
        return "operational"
    try:
        row = conn.execute("SELECT workspace FROM selection WHERE id=1").fetchone()
        value = row[0] if row else "operational"
        if value not in IDS:
            raise ApiError(503, "WORKSPACE_STATE_INVALID", "Active workspace state is invalid.")
        return value
    except sqlite3.DatabaseError as exc:
        raise ApiError(503, "WORKSPACE_STATE_INVALID", "Workspace control state is unavailable.") from exc
    finally:
        conn.close()


def active_database(request: Request) -> Path:
    selected = getattr(request.state, "selected_operational_database", None)
    if selected is not None:
        return selected
    operational, control, replay = paths(request)
    selected = replay if active_id(control) == "v3-1-replay" else operational
    request.state.selected_operational_database = selected
    return selected


def _count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            return int(conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0])
    except sqlite3.DatabaseError:
        return None


def state(request: Request) -> dict:
    operational, control, replay = paths(request)
    active = active_id(control)
    meta = None
    actions = []
    conn = _control(control)
    if conn is not None:
        try:
            row = conn.execute("SELECT * FROM replay_meta WHERE id=1").fetchone()
            meta = dict(row) if row else None
            actions = [dict(row) for row in conn.execute(
                "SELECT actor,action,workspace,reason,created_at FROM actions ORDER BY id DESC LIMIT 20")]
        finally:
            conn.close()
    return {"activeWorkspaceId": active, "activeWorkspaceName": NAMES[active],
            "actions": actions,
            "workspaces": [
                {"id": key, "name": NAMES[key], "active": key == active,
                 "ready": _count(path) is not None, "alertCount": _count(path),
                 "lastPreparedAt": meta["prepared_at"] if key == "v3-1-replay" and meta else None,
                 "rawRecords": meta["raw_records"] if key == "v3-1-replay" and meta else None,
                 "stagedAlerts": meta["staged_alerts"] if key == "v3-1-replay" and meta else None,
                 "workloadSha256": meta["workload_sha256"] if key == "v3-1-replay" and meta else None}
                for key, path in (("operational", operational), ("v3-1-replay", replay))]}


def _audit(conn: sqlite3.Connection, actor: str, action: str, workspace: str, reason: str) -> None:
    conn.execute("INSERT INTO actions(actor,action,workspace,reason,created_at) VALUES (?,?,?,?,?)",
                 (actor, action, workspace, reason, datetime.now(timezone.utc).isoformat()))


def activate(request: Request, workspace: str, actor: str, reason: str) -> dict:
    if workspace not in IDS:
        raise ApiError(404, "NOT_FOUND", "Unknown operational workspace.")
    operational, control, replay = paths(request)
    if _count(replay if workspace == "v3-1-replay" else operational) is None:
        raise ApiError(409, "WORKSPACE_NOT_READY", "Prepare this workspace before activation.")
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE selection SET workspace=? WHERE id=1", (workspace,))
        _audit(conn, actor, "workspace_activated", workspace, reason)
        conn.commit()
    finally:
        conn.close()
    return state(request)


def prepare(request: Request, actor: str, reason: str) -> dict:
    operational, control, replay = paths(request)
    conn = _control(control, create=True)
    assert conn is not None
    temporary = replay.with_name(f".v3-1-prepare-{uuid4().hex}.db")
    published = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT workspace FROM selection WHERE id=1").fetchone()[0] == "v3-1-replay":
            raise ApiError(409, "REPLAY_ACTIVE", "Activate Operational before preparing Replay.")
        if replay.exists():
            raise ApiError(409, "REPLAY_ALREADY_PREPARED", "Reset Replay before preparing it again.")
        try:
            raw = WORKLOAD.read_bytes()
        except OSError as exc:
            raise ApiError(503, "REPLAY_WORKLOAD_UNAVAILABLE", "Frozen V3.1 workload is unavailable.") from exc
        if len(raw.splitlines()) != 200:
            raise ApiError(503, "REPLAY_WORKLOAD_INVALID", "Frozen V3.1 workload must contain 200 records.")
        with closing(db.connect(temporary)) as target:
            db.create_schema(target)
            auth.ensure_demo_accounts(target)
            admin = target.execute("SELECT id FROM users WHERE username=? AND role='system_admin'",
                                   (actor,)).fetchone()
            if admin is None:
                raise ApiError(409, "REPLAY_ACTOR_MISSING", "Administrator account cannot be prepared in Replay.")
            actor_id = admin[0]
            report = stage_file(target, WORKLOAD, "v3-1-demo-replay", capture_scope="v3-1-demo-replay")
            if report.invalid or report.rejected_by_policy or report.parsed != 200:
                raise ApiError(503, "REPLAY_STAGING_FAILED", "The frozen workload did not stage cleanly.")
            inbox_ids = [row[0] for row in target.execute("SELECT id FROM external_alert_inbox ORDER BY id")]
            for inbox_id in inbox_ids:
                review = review_eligibility(target, inbox_id, actor_id=actor_id, request=EligibilityRequest(
                    requestId=uuid5(NAMESPACE_URL, f"v3-1-replay:review:{inbox_id}"),
                    expectedReviewId=None, decision="accepted", reason="Admin prepared isolated V3.1 demo replay"))
                admit_external(target, inbox_id, actor_id=actor_id, request=AdmissionRequest(
                    requestId=uuid5(NAMESPACE_URL, f"v3-1-replay:admit:{inbox_id}"),
                    expectedReviewId=review["id"], reason="Admin prepared isolated V3.1 demo replay"))
            count = int(target.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0])
            if target.execute("PRAGMA foreign_key_check").fetchone():
                raise ApiError(503, "REPLAY_INTEGRITY_FAILED", "Replay database has foreign key violations.")
        os.replace(temporary, replay)
        published = True
        conn.execute("INSERT OR REPLACE INTO replay_meta VALUES (1,?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), 200, report.staged, count,
                      hashlib.sha256(raw).hexdigest()))
        _audit(conn, actor, "replay_prepared", "v3-1-replay", reason)
        conn.commit()
    except Exception:
        conn.rollback()
        if temporary.exists():
            temporary.unlink()
        if published and replay.exists():
            replay.unlink()
        raise
    finally:
        conn.close()
    return state(request)


def reset(request: Request, actor: str, reason: str) -> dict:
    _, control, replay = paths(request)
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT workspace FROM selection WHERE id=1").fetchone()[0] == "v3-1-replay":
            raise ApiError(409, "REPLAY_ACTIVE", "Activate Operational before resetting Replay.")
        if replay.exists():
            try:
                replay.unlink()
            except PermissionError as exc:
                raise ApiError(409, "REPLAY_IN_USE", "Replay is still in use; retry after active requests finish.") from exc
        conn.execute("DELETE FROM replay_meta WHERE id=1")
        _audit(conn, actor, "replay_reset", "v3-1-replay", reason)
        conn.commit()
    finally:
        conn.close()
    return state(request)
