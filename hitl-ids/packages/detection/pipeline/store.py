"""The repository layer over the S2 schema (plan step S9).

Thin, explicit functions rather than an ORM: the contracts already describe every row, and
``db.insert``/``db.get`` already encode them. What is added here is the small set of reads and
registrations a detection run needs — each one a query the API (S10) and the evaluation (S15) reuse.

Registration is idempotent on the natural key — a dataset's ``(name, version)``, a model's
``version`` — so re-running detection over the same sample does not multiply rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from packages.contracts import db
from packages.contracts import models as m

GROUPABLE = frozenset({"evidence_class", "queue_class", "severity", "status"})


def guardrail_snapshot(conn: sqlite3.Connection) -> dict[str, float]:
    """Every guardrail setting as configured now, for ``detection_runs.guardrail_config``."""
    return {row["config_key"]: row["config_value"]
            for row in conn.execute("SELECT config_key, config_value FROM guardrail_config")}


def register_dataset(conn: sqlite3.Connection, *, name: str, version: str, source_file: str,
                     total_records: int, class_distribution: Mapping[str, Any],
                     preparation_meta: Mapping[str, Any] | None = None,
                     created_by: int | None = None, now: datetime | None = None) -> int:
    """The dataset's id, inserting it the first time. Idempotent on ``(name, version)``."""
    row = conn.execute("SELECT id FROM datasets WHERE name = ? AND version = ?",
                       (name, version)).fetchone()
    if row is not None:
        return int(row["id"])
    return db.insert(conn, m.Dataset(
        name=name, version=version, source_file=source_file, total_records=total_records,
        class_distribution=dict(class_distribution),
        preparation_meta=dict(preparation_meta) if preparation_meta is not None else None,
        created_by=created_by, created_at=now if now is not None else m.utc_now()))


def register_model(conn: sqlite3.Connection, *, version: str, model_file: str,
                   model_type: str = "XGBoost", metrics: Mapping[str, Any] | None = None,
                   status: str = "active", now: datetime | None = None) -> None:
    """Register the model this run used. Idempotent on ``version`` (the column is UNIQUE)."""
    if conn.execute("SELECT 1 FROM ml_models WHERE version = ?", (version,)).fetchone():
        return
    macro = (metrics or {}).get("report", {}).get("macro avg", {})
    db.insert(conn, m.MlModel(
        version=version, model_type=model_type, model_file=model_file, status=status,
        f1_score=macro.get("f1-score"), precision=macro.get("precision"),
        recall=macro.get("recall"), created_at=now if now is not None else m.utc_now()))


def start_run(conn: sqlite3.Connection, *, dataset_id: int, model_version: str,
              rule_set_version: str, fusion_weights: Mapping[str, Any],
              guardrail_config: Mapping[str, float], seed: int | None = None,
              now: datetime | None = None) -> int:
    """Open a detection run. Its configuration snapshot is what makes the run replayable."""
    return db.insert(conn, m.DetectionRun(
        dataset_id=dataset_id, model_version=model_version, rule_set_version=rule_set_version,
        fusion_weights=dict(fusion_weights), guardrail_config=dict(guardrail_config),
        status="running", seed=seed, started_at=now if now is not None else m.utc_now()))


def finish_run(conn: sqlite3.Connection, run_id: int, *, alert_count: int, now: datetime,
               status: str = "completed") -> m.DetectionRun:
    """Close the run and return the stored row."""
    conn.execute("UPDATE detection_runs SET status = ?, alert_count = ?, completed_at = ? "
                 "WHERE id = ?", (status, alert_count, db.format_timestamp(now), run_id))
    run = db.get(conn, m.DetectionRun, run_id)
    if run is None:
        raise LookupError(f"detection run {run_id} vanished")
    return run


def insert_alert(conn: sqlite3.Connection, alert: m.Alert, flow: m.FlowRecord) -> int:
    """One scored flow: the alert, then its 1:1 ``flow_data`` row. Returns the alert's id."""
    alert_id = db.insert(conn, alert)
    db.insert(conn, flow.model_copy(update={"alert_id": alert_id}))
    return alert_id


def queue(conn: sqlite3.Connection, *, limit: int | None = None,
          run_id: int | None = None) -> list[m.Alert]:
    """The analyst queue, in the order the contract defines (``db.QUEUE_ORDER_BY``)."""
    sql = "SELECT * FROM alerts"
    params: list[Any] = []
    if run_id is not None:
        sql += " WHERE run_id = ?"
        params.append(run_id)
    sql += f" ORDER BY {db.QUEUE_ORDER_BY}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [db.from_row(m.Alert, row) for row in conn.execute(sql, params)]


def alert_by_source_record(conn: sqlite3.Connection, source_record_id: str) -> m.Alert | None:
    """The alert for one source flow — the join the evaluation uses to reach ground truth."""
    row = conn.execute(
        "SELECT a.* FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        "WHERE f.source_record_id = ?", (source_record_id,)).fetchone()
    return None if row is None else db.from_row(m.Alert, row)


def counts_by(conn: sqlite3.Connection, column: str, *,
              run_id: int | None = None) -> dict[str, int]:
    """Alert counts grouped by one of the queue's own columns."""
    if column not in GROUPABLE:
        raise ValueError(f"{column!r} is not a column this summary groups by")
    sql = f"SELECT {column} AS bucket, COUNT(*) AS n FROM alerts"
    params: Sequence[Any] = ()
    if run_id is not None:
        sql += " WHERE run_id = ?"
        params = (run_id,)
    sql += " GROUP BY bucket"
    return {str(row["bucket"]): int(row["n"]) for row in conn.execute(sql, params)}
