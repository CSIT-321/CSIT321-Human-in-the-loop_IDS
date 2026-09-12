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


# --------------------------------------------------------------------------------------------
# Reads the API adds (plan step S10b).
#
# The queue's order is `db.QUEUE_ORDER_BY` and is not negotiable here: feedback moves an alert
# between queue *bands*, so a sort that ignores `queue_priority` hides the re-ranking the system
# exists to perform (`deviations.md` C13). `db.QUEUE_ORDER_BY`'s columns are unqualified, and its
# own comment warns that a query joining a table with its own `id` must qualify them — which every
# query here does.
# --------------------------------------------------------------------------------------------

#: The contract order, qualified for a join against flow_data.
QUEUE_ORDER_QUALIFIED = "a.queue_priority ASC, a.combined_score DESC, a.id ASC"

#: What a client may sort by. `queue` is the contract order and the default; the rest are
#: inspection tools. Every one ends in `a.id` so paging is stable — without a total order two
#: pages can repeat an alert or skip one.
SORT_COLUMNS: Mapping[str, str] = {
    "queue": QUEUE_ORDER_QUALIFIED,
    "combined_score": "a.combined_score {d}, a.id ASC",
    "detection_score": "a.detection_score {d}, a.id ASC",
    "created_at": "a.created_at {d}, a.id ASC",
    "severity": ("CASE a.severity WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 "
                 "WHEN 'Low' THEN 3 ELSE 4 END {d}, a.combined_score DESC, a.id ASC"),
}

FILTERABLE = frozenset({"queue_class", "evidence_class", "severity", "status", "attack_category"})


def _queue_filters(filters: Mapping[str, Any]) -> tuple[str, list[Any]]:
    """The WHERE clause for a queue query.

    An unknown key raises rather than being ignored: a filter silently dropped returns a plausible
    wrong answer, which is worse than an error.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if value is None:
            continue
        if key in FILTERABLE:
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            if not values:
                continue
            clauses.append(f"a.{key} IN ({', '.join('?' * len(values))})")
            params.extend(values)
        elif key == "requires_review":
            clauses.append("a.requires_review = ?")
            params.append(int(bool(value)))
        elif key == "run_id":
            clauses.append("a.run_id = ?")
            params.append(int(value))
        elif key == "min_score":
            clauses.append("a.combined_score >= ?")
            params.append(float(value))
        elif key == "max_score":
            clauses.append("a.combined_score <= ?")
            params.append(float(value))
        elif key == "search":
            clauses.append("(f.src_ip LIKE ? OR f.dst_ip LIKE ? OR a.signature_rules LIKE ?)")
            like = f"%{value}%"
            params.extend([like, like, like])
        else:
            raise ValueError(f"{key!r} is not a queue filter")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def flows_for_alerts(conn: sqlite3.Connection,
                     alert_ids: Sequence[int]) -> dict[int, m.FlowRecord]:
    """The flows behind a set of alerts, in one query rather than one per row."""
    ids = [int(i) for i in alert_ids]
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT * FROM flow_data WHERE alert_id IN ({', '.join('?' * len(ids))})", ids)
    return {int(row["alert_id"]): db.from_row(m.FlowRecord, row) for row in rows}


def queue_page(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0,
               sort: str = "queue", direction: str = "desc",
               **filters: Any) -> tuple[list[tuple[m.Alert, m.FlowRecord]], int]:
    """One page of the queue with its total, each alert paired with its flow.

    ``total`` counts every alert matching the filters *before* paging: an analyst needs to know how
    deep the queue is, not only what is on screen. Two queries, never one per row.
    """
    if sort not in SORT_COLUMNS:
        raise ValueError(f"{sort!r} is not a sort key; expected one of {sorted(SORT_COLUMNS)}")
    if direction not in ("asc", "desc"):
        raise ValueError(f"{direction!r} is not a sort direction; expected asc or desc")
    where, params = _queue_filters(filters)
    joined = "FROM alerts a JOIN flow_data f ON f.alert_id = a.id" + where

    total = int(conn.execute(f"SELECT COUNT(*) AS n {joined}", params).fetchone()["n"])
    order = SORT_COLUMNS[sort]
    if sort != "queue":  # the contract order is fixed; only the inspection sorts take a direction
        order = order.format(d=direction.upper())
    rows = conn.execute(f"SELECT a.* {joined} ORDER BY {order} LIMIT ? OFFSET ?",
                        [*params, limit, offset]).fetchall()

    alerts = [db.from_row(m.Alert, row) for row in rows]
    flows = flows_for_alerts(conn, [a.id for a in alerts if a.id is not None])
    paired: list[tuple[m.Alert, m.FlowRecord]] = []
    for alert in alerts:
        flow = flows.get(alert.id)
        if flow is None:
            raise LookupError(
                f"alert {alert.id} has no flow_data row; the 1:1 invariant is broken")
        paired.append((alert, flow))
    return paired, total


def alert_by_ref(conn: sqlite3.Connection, alert_ref: str) -> m.Alert | None:
    """The alert with this public UUID. A row id is never accepted from a client."""
    row = conn.execute("SELECT * FROM alerts WHERE alert_ref = ?", (str(alert_ref),)).fetchone()
    return None if row is None else db.from_row(m.Alert, row)


def flow_for_alert(conn: sqlite3.Connection, alert_id: int) -> m.FlowRecord | None:
    row = conn.execute("SELECT * FROM flow_data WHERE alert_id = ?", (alert_id,)).fetchone()
    return None if row is None else db.from_row(m.FlowRecord, row)


def family_by_key(conn: sqlite3.Connection, family_key: str | None) -> m.AlertFamily | None:
    if family_key is None:
        return None
    row = conn.execute("SELECT * FROM alert_families WHERE family_key = ?",
                       (family_key,)).fetchone()
    return None if row is None else db.from_row(m.AlertFamily, row)


def family_size(conn: sqlite3.Connection, family_key: str | None) -> int:
    if family_key is None:
        return 0
    return int(conn.execute("SELECT COUNT(*) AS n FROM alerts WHERE family_key = ?",
                            (family_key,)).fetchone()["n"])


def feedback_for_alert(conn: sqlite3.Connection, alert_id: int) -> list[m.FeedbackEvent]:
    """Every verdict on one alert, oldest first. Append-only, so this is the whole history."""
    return [db.from_row(m.FeedbackEvent, row) for row in conn.execute(
        "SELECT * FROM feedback_events WHERE alert_id = ? ORDER BY created_at, id", (alert_id,))]


def has_feedback(conn: sqlite3.Connection, alert_ids: Sequence[int]) -> set[int]:
    """Which of these alerts carry a verdict — one query for a whole page."""
    ids = [int(i) for i in alert_ids]
    if not ids:
        return set()
    rows = conn.execute(
        f"SELECT DISTINCT alert_id FROM feedback_events "
        f"WHERE alert_id IN ({', '.join('?' * len(ids))})", ids)
    return {int(row["alert_id"]) for row in rows}


def users_by_id(conn: sqlite3.Connection, ids: Sequence[int]) -> dict[int, m.User]:
    """The users behind a set of actor ids, in one query rather than one per row."""
    wanted = sorted({int(i) for i in ids if i is not None})
    if not wanted:
        return {}
    rows = conn.execute(
        f"SELECT * FROM users WHERE id IN ({', '.join('?' * len(wanted))})", wanted)
    return {int(row["id"]): db.from_row(m.User, row) for row in rows}


def audit_page(conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0,
               event_type: Sequence[str] | None = None, actor_id: int | None = None,
               since: str | None = None,
               until: str | None = None) -> tuple[list[m.AuditEntry], int]:
    """A page of the audit trail with its total, newest first.

    Newest first because an administrator is asking what *just* happened. Timestamp bounds are
    fixed-width UTC text, so text order is time order (`db.format_timestamp`).
    """
    clauses: list[str] = []
    params: list[Any] = []
    if event_type:
        clauses.append(f"event_type IN ({', '.join('?' * len(event_type))})")
        params.extend(event_type)
    if actor_id is not None:
        clauses.append("actor_id = ?")
        params.append(int(actor_id))
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    total = int(conn.execute(f"SELECT COUNT(*) AS n FROM audit_log{where}",
                             params).fetchone()["n"])
    rows = conn.execute(
        f"SELECT * FROM audit_log{where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset])
    return [db.from_row(m.AuditEntry, row) for row in rows], total


def guardrail_settings(conn: sqlite3.Connection) -> list[m.GuardrailConfigEntry]:
    return [db.from_row(m.GuardrailConfigEntry, row) for row in
            conn.execute("SELECT * FROM guardrail_config ORDER BY config_key")]


def dashboard_counts(conn: sqlite3.Connection, *, run_id: int | None = None) -> dict[str, Any]:
    """The summary the analyst lands on.

    ``alerts_moved_by_feedback`` compares each alert's operational score and band against what
    detection produced. It is the one number that says whether the human in the loop is doing
    anything at all, which is why it is on the landing screen rather than buried in the evaluation.
    """
    where, params = (" WHERE run_id = ?", [run_id]) if run_id is not None else ("", [])
    joiner = " AND" if where else " WHERE"
    total = int(conn.execute(f"SELECT COUNT(*) AS n FROM alerts{where}", params).fetchone()["n"])
    bands = [
        {"queue_class": row["queue_class"], "count": int(row["n"]),
         "requires_review": int(row["r"] or 0)}
        for row in conn.execute(
            f"SELECT queue_class, COUNT(*) AS n, SUM(requires_review) AS r FROM alerts{where} "
            f"GROUP BY queue_class ORDER BY MIN(queue_priority)", params)
    ]
    return {
        "total_alerts": total,
        "by_queue_class": bands,
        "by_evidence_class": counts_by(conn, "evidence_class", run_id=run_id),
        "by_severity": counts_by(conn, "severity", run_id=run_id),
        "by_status": counts_by(conn, "status", run_id=run_id),
        "by_attack_category": {
            str(row["attack_category"]): int(row["n"]) for row in conn.execute(
                f"SELECT attack_category, COUNT(*) AS n FROM alerts{where} "
                f"GROUP BY attack_category", params) if row["attack_category"] is not None},
        "requires_review": int(conn.execute(
            f"SELECT COUNT(*) AS n FROM alerts{where}{joiner} requires_review = 1",
            params).fetchone()["n"]),
        "tier2_candidates": int(conn.execute(
            f"SELECT COUNT(*) AS n FROM alerts{where}{joiner} queue_class = 'tier2_candidate'",
            params).fetchone()["n"]),
        "feedback_events": int(conn.execute(
            "SELECT COUNT(*) AS n FROM feedback_events").fetchone()["n"]),
        "guardrail_interventions": int(conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE event_type LIKE 'GUARDRAIL%'"
        ).fetchone()["n"]),
        "alerts_moved_by_feedback": int(conn.execute(
            # An alert has been moved by a human if its operational score has left its detection
            # score, or if it belongs to a family whose gate is open and which is applying a
            # learned adjustment (S7b — the member itself may carry no verdict).
            #
            # NOT `queue_class != evidence_class`: detection itself places alerts in the
            # `tier2_candidate` band, so that comparison reports 644 movements on a database with
            # zero feedback events. Measured, not assumed.
            f"SELECT COUNT(*) AS n FROM alerts a{where.replace(' WHERE ', ' WHERE ')}{joiner} ("
            f"  a.combined_score != a.detection_score"
            f"  OR EXISTS (SELECT 1 FROM feedback_events fe WHERE fe.alert_id = a.id)"
            f"  OR EXISTS (SELECT 1 FROM alert_families af WHERE af.family_key = a.family_key"
            f"             AND af.gate_open = 1"
            f"             AND (af.applied_adjustment != 0 OR af.applied_offset != 0)))",
            params).fetchone()["n"]),
    }


def latest_run(conn: sqlite3.Connection) -> m.DetectionRun | None:
    row = conn.execute("SELECT * FROM detection_runs ORDER BY id DESC LIMIT 1").fetchone()
    return None if row is None else db.from_row(m.DetectionRun, row)
