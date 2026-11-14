"""Durable, allowlisted operational workspace selection and isolated replay preparation.

Every request snapshots the active workspace before opening its operational connection.
An in-flight request finishes against that same connection after a switch; the next
request resolves the newly active workspace. Control state is never stored in either
operational database.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import Request

from apps.api import auth
from apps.api.deps import ApiError, database_path
from packages.contracts import db
from packages.detection.adapters.staging import stage_file
from packages.detection.cross_chain import VISIBLE
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)
from apps.api import packet_replay, presentation_replay

REPOSITORY = Path(__file__).resolve().parents[3]
WORKLOAD = REPOSITORY / "evaluation/protocol-v3.1/workload/operational-workload.jsonl"
IDS = ("operational", "v3-1-replay")
NAMES = {"operational": "Operational", "v3-1-replay": "V3.1 Demo Replay"}


def paths(request: Request) -> tuple[Path, Path, Path]:
    operational = Path(getattr(request.app.state, "database_path", None) or database_path()).resolve()
    directory = operational.parent / "workspaces"
    return operational, directory / "control.db", directory / "v3-1-replay.db"


def _control(path: Path, *, create: bool = False) -> sqlite3.Connection | None:
    """Open the control file. Any existing file is brought to the current schema, because readers
    (including the 0.5 s playback tick) must find every table they use."""
    if not path.exists():
        if not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_control_schema(conn)
    return conn


def _ensure_control_schema(conn: sqlite3.Connection) -> None:
    """Idempotent. Runs on every open so a control file from an older version still serves its readers."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS selection (id INTEGER PRIMARY KEY CHECK (id=1), workspace TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS replay_meta (id INTEGER PRIMARY KEY CHECK (id=1), prepared_at TEXT NOT NULL,
        raw_records INTEGER NOT NULL, staged_alerts INTEGER NOT NULL, operational_alerts INTEGER NOT NULL,
        workload_sha256 TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
        workspace TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS presentation (id INTEGER PRIMARY KEY CHECK(id=1),
        cursor INTEGER NOT NULL CHECK(cursor BETWEEN 0 AND 160), initial_holdout INTEGER NOT NULL,
        arrival_order TEXT NOT NULL CHECK(json_valid(arrival_order)),
        playback_state TEXT NOT NULL CHECK(playback_state IN ('paused','running','complete')),
        next_due_at TEXT, last_arrival_at TEXT, preparing_admin TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS presentation_requests (request_id TEXT PRIMARY KEY,
        actor TEXT NOT NULL, count INTEGER NOT NULL, resulting_cursor INTEGER NOT NULL,
        created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL,
        updated_at TEXT NOT NULL, actor TEXT NOT NULL);
    INSERT OR IGNORE INTO selection(id,workspace) VALUES (1,'operational');
    """)
    columns = [column[1] for column in conn.execute('PRAGMA table_info(presentation)')]
    if 'mode' not in columns:
        conn.execute("ALTER TABLE presentation ADD COLUMN mode TEXT NOT NULL DEFAULT 'presentation'")
    if 'flow_chain' not in columns:
        conn.execute("ALTER TABLE presentation ADD COLUMN flow_chain INTEGER NOT NULL DEFAULT 1")
    # A replay prepared while the switch sat on the presentation row keeps that choice once.
    conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_at,actor) "
                 "SELECT 'flow_chain_enabled', CASE WHEN flow_chain=1 THEN '1' ELSE '0' END, "
                 "datetime('now'), 'system' FROM presentation WHERE id=1")
    conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_at,actor) "
                 "VALUES ('flow_chain_enabled','1',datetime('now'),'system')")
    conn.commit()


def detection(conn: sqlite3.Connection) -> dict:
    """The program's detector settings. They belong to the product, not to a workspace or a replay."""
    row = conn.execute("SELECT value FROM settings WHERE key='flow_chain_enabled'").fetchone()
    return {'flowChainEnabled': True if row is None else row[0] == '1'}


def configure_presentation_database(path: Path) -> None:
    """Allow Replay arrivals to commit while Analyst/SSE readers remain active."""
    if not path.is_file():
        return
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        if conn.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'wal':
            mode = conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]
            if mode.lower() != 'wal':
                raise sqlite3.OperationalError('Presentation Replay requires WAL journaling')


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


def selected_id(request: Request) -> str:
    """The allowlisted workspace bound to this request's operational connection."""
    _, _, replay = paths(request)
    return "v3-1-replay" if active_database(request) == replay else "operational"


def _count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            try:   # the visible queue: an item hidden by the cross-chain join is not counted
                return int(conn.execute(f"SELECT count(*) FROM {VISIBLE}").fetchone()[0])
            except sqlite3.OperationalError:   # a database from before migration 27 has no join table
                return int(conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0])
    except sqlite3.DatabaseError:
        return None


def state(request: Request) -> dict:
    operational, control, replay = paths(request)
    active = active_id(control)
    meta = None
    presentation = None
    progressive = 'full'
    actions = []
    settings = {'flowChainEnabled': True}
    conn = _control(control)
    if conn is not None:
        try:
            row = conn.execute("SELECT * FROM replay_meta WHERE id=1").fetchone()
            meta = dict(row) if row else None
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='presentation'").fetchone():
                row = conn.execute("SELECT * FROM presentation WHERE id=1").fetchone()
                presentation = dict(row) if row else None
                if presentation:
                    progressive = presentation.get('mode', 'presentation')
            actions = [dict(row) for row in conn.execute(
                "SELECT actor,action,workspace,reason,created_at FROM actions ORDER BY id DESC LIMIT 20")]
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone():
                settings = detection(conn)
        finally:
            conn.close()
    return {"activeWorkspaceId": active, "activeWorkspaceName": NAMES[active],
            "actions": actions, "detection": settings,
            "workspaces": [
                {"id": key, "name": NAMES[key], "active": key == active,
                 "ready": (count := _count(path)) is not None, "alertCount": count,
                 "preparedFile": path.exists(),
                 "lastPreparedAt": meta["prepared_at"] if key == "v3-1-replay" and meta else None,
                 "rawRecords": meta["raw_records"] if key == "v3-1-replay" and meta else None,
                 "stagedAlerts": meta["staged_alerts"] if key == "v3-1-replay" and meta else None,
                 "preparationMode": progressive if key == 'v3-1-replay' and meta else None,
                 "learningProcessed": 40 if progressive == 'presentation' and key == 'v3-1-replay' else 0 if key == 'v3-1-replay' and meta else None,
                 "holdoutArrived": presentation['cursor'] if presentation and key == 'v3-1-replay' else 160 if key == 'v3-1-replay' and meta else None,
                 "holdoutRemaining": 160-presentation['cursor'] if presentation and key == 'v3-1-replay' else 0 if key == 'v3-1-replay' and meta else None,
                 "playbackState": presentation['playback_state'] if presentation and key == 'v3-1-replay' else None,
                 "lastArrivalAt": presentation['last_arrival_at'] if presentation and key == 'v3-1-replay' else None,
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
        if workspace == 'operational':
            paused = conn.execute("UPDATE presentation SET playback_state='paused',next_due_at=NULL WHERE id=1 AND playback_state='running'").rowcount
            if paused:
                _audit(conn, actor, 'presentation_playback_paused', 'v3-1-replay', 'Paused automatically when Operational became active')
        conn.execute("UPDATE selection SET workspace=? WHERE id=1", (workspace,))
        _audit(conn, actor, "workspace_activated", workspace, reason)
        conn.commit()
    finally:
        conn.close()
    return state(request)


def prepare(request: Request, actor: str, reason: str, mode: str = 'full') -> dict:
    if mode not in ('full', 'presentation', 'packet'):
        raise ApiError(400, 'INVALID_REPLAY_MODE', 'Choose Full Replay, Presentation Replay or Packet Replay.')
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
        records, raw = 200, b''
        if mode == 'packet':
            if not packet_replay.available():
                raise ApiError(503, "REPLAY_WORKLOAD_UNAVAILABLE",
                               "Packet replay data is missing. Run scripts/build_packet_replay.py.")
            records, staged, count = packet_replay.build(temporary), 0, 0
            workload_hash = packet_replay.source_hash()
        else:
            try:
                raw = WORKLOAD.read_bytes()
            except OSError as exc:
                raise ApiError(503, "REPLAY_WORKLOAD_UNAVAILABLE", "Frozen V3.1 workload is unavailable.") from exc
            if len(raw.splitlines()) != 200:
                raise ApiError(503, "REPLAY_WORKLOAD_INVALID", "Frozen V3.1 workload must contain 200 records.")
            workload_hash = hashlib.sha256(raw).hexdigest()
        if mode == 'packet':
            pass
        elif mode == 'presentation':
            source_hash, learning_counts, count = presentation_replay.build(temporary, actor)
            if source_hash != workload_hash:
                raise ApiError(503, 'REPLAY_WORKLOAD_CHANGED', 'Frozen workload changed during preparation.')
            staged = count
        else:
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
                staged = report.staged
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(replay) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        os.replace(temporary, replay)
        published = True
        _checkpoint(replay)
        if mode != 'full':
            configure_presentation_database(replay)
        conn.execute("INSERT OR REPLACE INTO replay_meta VALUES (1,?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), records, staged, count, workload_hash))
        if mode == "packet":
            # The capture steps arrive in order; nothing has arrived yet.
            conn.execute("DELETE FROM presentation WHERE id=1")
            conn.execute("INSERT INTO presentation VALUES (1,0,0,?,'paused',NULL,NULL,?,'packet',1)",
                         (json.dumps(list(range(160))), actor))
            _audit(conn, actor, 'packet_replay_prepared', 'v3-1-replay', reason)
        elif mode == 'presentation':
            conn.execute("DELETE FROM presentation WHERE id=1")
            order = presentation_replay.arrival_order(json.loads(presentation_replay.STRUCTURE.read_text(encoding='utf-8')))
            conn.execute("INSERT INTO presentation VALUES (1,?,?,?,?,?,?,?,'presentation',1)",
                (presentation_replay.INITIAL_HOLDOUT, presentation_replay.INITIAL_HOLDOUT,
                 json.dumps(order), 'paused', None, datetime.now(timezone.utc).isoformat(), actor))
            _audit(conn, actor, 'presentation_replay_prepared', 'v3-1-replay', reason)
        else:
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


# Requests that started before the switch to Operational finish in Replay and hold the file
# (Windows refuses to delete an open file). Measured 2026-11-13: 6 Analyst tabs on the 11,064-alert
# packet replay released it 6.9 s after the switch. Wait for them instead of asking Analysts to leave.
DRAIN_SECONDS = 30


def _remove_database(path: Path) -> None:
    """Delete a database and its WAL sidecars.

    A reader can hold the file for a moment after its request ends (Windows keeps
    the handle until the connection closes). Wait for in-flight requests to drain
    before refusing. The -wal and -shm must go too: a stale WAL attached to a
    freshly built file reads as "database disk image is malformed".
    """
    deadline = time.monotonic() + DRAIN_SECONDS
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(path) + suffix)
        if not target.exists():
            continue
        delay = 0.25
        while True:
            try:
                target.unlink()
                break
            except PermissionError as exc:
                if time.monotonic() >= deadline:
                    raise ApiError(409, "REPLAY_IN_USE",
                                   f"Replay requests did not finish within {DRAIN_SECONDS} s. "
                                   "Nothing was reset. Retry Reset Replay.") from exc
                time.sleep(delay)
                delay = min(delay * 2, 1.0)


def _checkpoint(path: Path) -> None:
    """Merge a freshly built WAL into the main file so a read-only open works."""
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _open_claims(replay: Path) -> int:
    """Analyst claims the reset discards (for the audit line). 0 when the file or table is absent."""
    if not replay.exists():
        return 0
    try:
        with closing(sqlite3.connect(replay.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            return int(conn.execute("SELECT count(*) FROM analyst_work WHERE status='in_review'").fetchone()[0])
    except sqlite3.Error:
        return 0


def reset(request: Request, actor: str, reason: str) -> dict:
    """Administrator reset. Supersedes Analysts: an active Replay is switched to Operational first,
    open claims are discarded with the file, and in-flight Analyst requests are waited for."""
    _, control, replay = paths(request)
    if active_id(control) == "v3-1-replay":
        activate(request, "operational", actor, f"{reason} · Reset Replay moved Analysts to Operational")
    claims = _open_claims(replay)
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT workspace FROM selection WHERE id=1").fetchone()[0] == "v3-1-replay":
            # Only if another Administrator re-activated Replay between the switch and this transaction.
            raise ApiError(409, "REPLAY_ACTIVE", "Replay was activated again during the reset. Retry Reset Replay.")
        _remove_database(replay)
        conn.execute("DELETE FROM replay_meta WHERE id=1")
        conn.execute("DELETE FROM presentation WHERE id=1")
        conn.execute("DELETE FROM presentation_requests")
        _audit(conn, actor, "replay_reset", "v3-1-replay",
               f"{reason} · released {claims} open Analyst claim{'s' if claims != 1 else ''}" if claims else reason)
        conn.commit()
    finally:
        conn.close()
    return state(request)


def _advance_locked(conn: sqlite3.Connection, replay: Path, count: int, actor: str, reason: str) -> int:
    row = conn.execute('SELECT * FROM presentation WHERE id=1').fetchone()
    if row is None or not replay.exists():
        raise ApiError(409, 'PRESENTATION_NOT_PREPARED', 'Prepare Presentation Replay first.')
    order = json.loads(row['arrival_order'])
    cursor = row['cursor']
    packet = 'mode' in row.keys() and row['mode'] == 'packet'   # a control file from before Packet Replay has no column
    for _ in range(min(count, 160-cursor)):
        # The flow-chain switch is a program setting, not a replay option: every step reads it.
        flow_on = detection(conn)['flowChainEnabled']
        for attempt in range(3):
            try:
                if packet:
                    staged, total = packet_replay.advance_one(replay, order[cursor], row['preparing_admin'],
                                                              project_flows=flow_on)
                else:
                    presentation_replay.advance_one(replay, order[cursor], row['preparing_admin'])
                    staged = total = 41 + cursor
                break
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc).lower() and 'busy' not in str(exc).lower():
                    raise
                if attempt == 2:
                    raise ApiError(503, 'REPLAY_DATABASE_BUSY',
                                   'Presentation Replay database remained busy after bounded retry.') from exc
                time.sleep(.1 * (2 ** attempt))
        cursor += 1
        stamp = datetime.now(timezone.utc).isoformat()
        conn.execute('UPDATE presentation SET cursor=?,last_arrival_at=? WHERE id=1', (cursor, stamp))
        conn.execute('UPDATE replay_meta SET staged_alerts=?,operational_alerts=? WHERE id=1', (staged, total))
    if cursor == 160 and row['playback_state'] != 'complete':
        conn.execute("UPDATE presentation SET playback_state='complete',next_due_at=NULL WHERE id=1")
        _audit(conn, actor, 'presentation_playback_completed', 'v3-1-replay', reason)
    return cursor


def advance(request: Request, count: int, actor: str, reason: str, request_id: str) -> dict:
    if count not in (1, 5, 150):
        raise ApiError(400, 'INVALID_ADVANCE_COUNT', 'Choose Next Alert, Next 5, or Load Remaining.')
    _, control, replay = paths(request)
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT workspace FROM selection WHERE id=1').fetchone()[0] != 'v3-1-replay':
            raise ApiError(409, 'REPLAY_INACTIVE', 'Activate V3.1 Demo Replay before advancing.')
        previous = conn.execute('SELECT actor,count FROM presentation_requests WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if previous['actor'] != actor or previous['count'] != count:
                raise ApiError(409, 'REQUEST_ID_CONFLICT', 'Request ID belongs to another advance command.')
        else:
            current = _advance_locked(conn, replay, count, actor, reason)
            conn.execute('INSERT INTO presentation_requests VALUES (?,?,?,?,?)',
                         (request_id, actor, count, current, datetime.now(timezone.utc).isoformat()))
            _audit(conn, actor, 'presentation_manual_advance', 'v3-1-replay',
                   f'{reason} · requested {count}; arrived {current}/160')
        conn.commit()
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
            raise ApiError(503, 'REPLAY_DATABASE_BUSY',
                           'Presentation Replay database remained busy after bounded retry.') from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return state(request)


def playback(request: Request, actor: str, reason: str, action: str) -> dict:
    _, control, replay = paths(request)
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM presentation WHERE id=1').fetchone()
        if row is None or not replay.exists():
            raise ApiError(409, 'PRESENTATION_NOT_PREPARED', 'Prepare Presentation Replay first.')
        active = conn.execute('SELECT workspace FROM selection WHERE id=1').fetchone()[0]
        if action == 'start':
            if active != 'v3-1-replay':
                raise ApiError(409, 'REPLAY_INACTIVE', 'Activate V3.1 Demo Replay before playback.')
            if row['playback_state'] == 'paused' and row['cursor'] < 160:
                due = datetime.now(timezone.utc) + timedelta(seconds=presentation_replay.RATE_SECONDS)
                conn.execute("UPDATE presentation SET playback_state='running',next_due_at=? WHERE id=1", (due.isoformat(),))
                _audit(conn, actor, 'presentation_playback_started', 'v3-1-replay', reason)
        elif action == 'pause':
            if row['playback_state'] == 'running':
                conn.execute("UPDATE presentation SET playback_state='paused',next_due_at=NULL WHERE id=1")
                _audit(conn, actor, 'presentation_playback_paused', 'v3-1-replay', reason)
        else:
            raise ApiError(400, 'INVALID_PLAYBACK_ACTION', 'Unknown presentation playback action.')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return state(request)


def set_detection_chain(request: Request, actor: str, reason: str, enabled: bool) -> dict:
    """Program-wide switch: does the CICFlowMeter chain process arriving flow records?

    Off: flow records still arrive and are stored, but the program does not group, project or route
    them. On: the program processes everything not yet processed, so a backlog is caught up.
    Independent of any workspace or replay; no prepare and no reset.
    """
    _, control, _ = paths(request)
    conn = _control(control, create=True)
    assert conn is not None
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("INSERT INTO settings(key,value,updated_at,actor) VALUES ('flow_chain_enabled',?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, "
                     "actor=excluded.actor", ('1' if enabled else '0', datetime.now(timezone.utc).isoformat(), actor))
        _audit(conn, actor, 'detection_flow_chain_set', 'program',
               f'{reason} · CICFlowMeter flow chain {"on" if enabled else "off"}')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return state(request)


def tick(operational: Path) -> None:
    """At most one due arrival; SQLite control lock coordinates duplicate app workers."""
    control = operational.resolve().parent / 'workspaces' / 'control.db'
    replay = control.parent / 'v3-1-replay.db'
    conn = _control(control)
    if conn is None:
        return
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='presentation'").fetchone():
            return
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM presentation WHERE id=1').fetchone()
        if row is None or row['playback_state'] != 'running':
            conn.commit(); return
        if conn.execute('SELECT workspace FROM selection WHERE id=1').fetchone()[0] != 'v3-1-replay':
            conn.execute("UPDATE presentation SET playback_state='paused',next_due_at=NULL WHERE id=1")
            _audit(conn, row['preparing_admin'], 'presentation_playback_paused', 'v3-1-replay',
                   'Paused because Replay is not active')
            conn.commit(); return
        if row['next_due_at'] and datetime.now(timezone.utc) < datetime.fromisoformat(row['next_due_at']):
            conn.commit(); return
        try:
            cursor = _advance_locked(conn, replay, 1, 'System Policy', 'Automatic presentation arrival')
            if cursor < 160:
                due = datetime.now(timezone.utc) + timedelta(seconds=presentation_replay.RATE_SECONDS)
                conn.execute('UPDATE presentation SET next_due_at=? WHERE id=1', (due.isoformat(),))
        except Exception as exc:
            conn.execute("UPDATE presentation SET playback_state='paused',next_due_at=NULL WHERE id=1")
            _audit(conn, 'System Policy', 'presentation_playback_paused', 'v3-1-replay',
                   f'Automatic arrival paused after error: {exc.code if isinstance(exc, ApiError) else type(exc).__name__}')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
