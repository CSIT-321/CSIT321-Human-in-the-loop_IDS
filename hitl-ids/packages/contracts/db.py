"""SQLite binding for the S2 contracts: connection settings, schema creation, row codec.

The repository layer (S9) is built on ``insert``/``get``; they exist here because the storage
encoding — JSON columns, booleans, timestamps — is part of the contract.
"""

from __future__ import annotations

import json
import sqlite3
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel

from . import models as m

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Queue order is part of the fusion contract (plan S6). It has had three forms, and each change is
# recorded. Ordering by score alone ranked the key detections #414 of 417 (v1.0 FIX), so the queue
# band went first. v1.31 replaced the band with severity: the band put Tier 2 candidates that are not
# severe at the top of the queue (measured - the whole top 50 was Medium), and on the demo sample
# severity tracks detection precision almost monotonically (Critical 1.000, High 0.992, Medium 0.998,
# Low 0.910, Informational 0.001), so it leads with the alerts an analyst should work first.
#
# `queue_class` and `queue_priority` remain, as the Tier 2 *label* and the band tabs, but they no
# longer order the queue. This retired invariant I5.
#
# The column names are unqualified, so this drops into any query over `alerts` alone (as
# `pipeline.store.queue` does). A query that JOINs a table with its own `id` must alias: call
# `queue_order("a")`.
SEVERITY_ORDER = ("CASE {q}severity WHEN 'Critical' THEN 4 WHEN 'High' THEN 3 "
                  "WHEN 'Medium' THEN 2 WHEN 'Low' THEN 1 ELSE 0 END DESC")


def queue_order(alias: str = "") -> str:
    """The analyst queue's order: severity worst-first, then the operational score, then id.

    One definition, qualified on request, so the queue, the API's read queries and the evaluation
    harness cannot drift apart. ``alias`` is a table alias such as ``"a"``, or empty for a query over
    ``alerts`` alone.
    """
    q = f"{alias}." if alias else ""
    return f"{SEVERITY_ORDER.format(q=q)}, {q}combined_score DESC, {q}id ASC"


QUEUE_ORDER_BY = queue_order()

TABLE_MODELS: dict[str, type[m.Contract]] = {
    "users": m.User,
    "datasets": m.Dataset,
    "signature_rules": m.SignatureRule,
    "ml_models": m.MlModel,
    "detection_runs": m.DetectionRun,
    "alerts": m.Alert,
    "flow_data": m.FlowRecord,
    "feedback_events": m.FeedbackEvent,
    "alert_notes": m.AlertNote,
    "alert_families": m.AlertFamily,
    "audit_log": m.AuditEntry,
    "guardrail_config": m.GuardrailConfigEntry,
    "evaluation_scenarios": m.EvaluationScenario,
    "evaluation_runs": m.EvaluationRun,
}
_TABLE_OF = {model: table for table, model in TABLE_MODELS.items()}

ModelT = TypeVar("ModelT", bound=m.Contract)


def connect(path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a database with the contract's pragmas.

    ``check_same_thread=False`` is for a caller that guarantees one user at a time but not one
    thread: the API opens a connection per request, and FastAPI may enter the dependency, run the
    handler and close the connection on three different worker threads.
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Belt and braces with the no_replace triggers: REPLACE fires DELETE triggers only when on.
    conn.execute("PRAGMA recursive_triggers = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables on a fresh database, seed the guardrail defaults, apply every migration."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO guardrail_config (config_key, config_value, description) VALUES (?, ?, ?)",
        [(key, value, text) for key, (value, text) in m.GUARDRAIL_DEFAULTS.items()],
    )
    conn.commit()
    migrate(conn)


#: Schema changes after S9 consumed schema.sql are migrations, never edits to it (plan S2). Each
#: entry is (version, description, SQL); `PRAGMA user_version` records the last one applied. A fresh
#: database runs schema.sql and then every migration, so both paths end at the same schema. Every
#: statement is IF NOT EXISTS, so two connections racing to apply one migration both succeed.
MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "alert_notes: the append-only analyst notes thread (console rebuild B2)", """
CREATE TABLE IF NOT EXISTS alert_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id   INTEGER NOT NULL REFERENCES alerts (id),
    user_id    INTEGER NOT NULL REFERENCES users (id),
    body       TEXT    NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
);
CREATE INDEX IF NOT EXISTS idx_notes_alert ON alert_notes (alert_id);
CREATE TRIGGER IF NOT EXISTS trg_notes_no_update BEFORE UPDATE ON alert_notes
BEGIN SELECT RAISE(ABORT, 'alert_notes is append-only: add a new note'); END;
CREATE TRIGGER IF NOT EXISTS trg_notes_no_delete BEFORE DELETE ON alert_notes
BEGIN SELECT RAISE(ABORT, 'alert_notes is append-only: add a new note'); END;
CREATE TRIGGER IF NOT EXISTS trg_notes_no_replace BEFORE INSERT ON alert_notes
WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM alert_notes WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'alert_notes is append-only: add a new note'); END;
"""),
)
SCHEMA_VERSION = MIGRATIONS[-1][0]


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply every migration newer than the database's ``user_version``, in order. Idempotent.

    Returns the versions applied, so a caller (or a test) can tell a no-op from an upgrade.
    """
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    applied: list[int] = []
    for version, _description, sql in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {int(version)};\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
        applied.append(version)
    return applied


# Fixed width, so text order is time order. Variable-width ISO text sorts wrongly
# ("12:00:00.5Z" < "12:00:00Z"), which would break every created_at range query and index.
# schema.sql's column defaults produce the same shape.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(moment: datetime) -> str:
    """The one timestamp encoding: UTC, microseconds, 27 characters. Use it for query bounds too."""
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def to_row(model: m.Contract) -> dict[str, Any]:
    row = model.model_dump(mode="json")
    for column in type(model).model_fields:
        value = getattr(model, column)
        if isinstance(value, datetime):
            row[column] = format_timestamp(value)
    return {
        column: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        for column, value in row.items()
    }


def from_row(model_cls: type[ModelT], row: sqlite3.Row | dict[str, Any]) -> ModelT:
    data = dict(row)
    for column in _json_fields(model_cls):
        if isinstance(data.get(column), str):
            data[column] = json.loads(data[column])
    return model_cls.model_validate(data)


def insert(conn: sqlite3.Connection, model: m.Contract) -> int:
    """Insert one table model and return its new id. The caller owns the transaction."""
    row = to_row(model)
    if row.get("id") is None:
        row.pop("id", None)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    cursor = conn.execute(
        f"INSERT INTO {_TABLE_OF[type(model)]} ({columns}) VALUES ({placeholders})",
        list(row.values()),
    )
    return int(cursor.lastrowid)


def get(conn: sqlite3.Connection, model_cls: type[ModelT], row_id: int) -> ModelT | None:
    row = conn.execute(f"SELECT * FROM {_TABLE_OF[model_cls]} WHERE id = ?", (row_id,)).fetchone()
    return None if row is None else from_row(model_cls, row)


def _json_fields(model_cls: type[BaseModel]) -> set[str]:
    return {name for name, field in model_cls.model_fields.items() if _is_json(field.annotation)}


def _is_json(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        return any(_is_json(arg) for arg in get_args(annotation) if arg is not type(None))
    if origin in (dict, list):
        return True
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)
