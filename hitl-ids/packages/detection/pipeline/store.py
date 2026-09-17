"""The repository layer over the S2 schema (plan step S9).

Thin, explicit functions rather than an ORM: the contracts already describe every row, and
``db.insert``/``db.get`` already encode them. What is added here is the small set of reads and
registrations a detection run needs — each one a query the API (S10) and the evaluation (S15) reuse.

Registration is idempotent on the natural key — a dataset's ``(name, version)``, a model's
``version`` — so re-running detection over the same sample does not multiply rows.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
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
# The queue's order is `db.QUEUE_ORDER_BY` and is not negotiable here: it is the order an analyst
# works down. A sort that restates it would drift from it. `db.queue_order` qualifies the columns for
# a join, which `QUEUE_ORDER_BY`'s own comment requires.
# --------------------------------------------------------------------------------------------

#: The contract order, qualified for a join against flow_data.
QUEUE_ORDER_QUALIFIED = db.queue_order("a")

FILTERABLE = frozenset({"queue_class", "evidence_class", "severity", "status", "attack_category"})

#: When the flow was captured, as the dataset recorded it: capture-local text such as
#: '2018-02-14 12:28:54.334391', so text order is time order. Not the alert's created_at, which is
#: the detection run's time and identical for every alert in a run.
FLOW_TIME = "json_extract(f.flow_features, '$.Timestamp')"

#: What orders rows when the sort key ties. A tie is the normal case on this data, not the
#: exception: 4,789 of the 5,000 demo alerts share a score with more than a page of others — 975
#: sit at exactly 100.0 and 3,635 at exactly 0.0. Row id alone is arbitrary, and because it did not
#: take the requested direction it made the direction control look inert: sorting the 975 alerts at
#: 100.0 descending and ascending returned the *identical* page (measured, not assumed).
#:
#: The evidence class and the flow's capture time are the two keys that actually vary inside a tied
#: group: 200 corroborated against 775 model-only, and 975 distinct capture times. Capture time must
#: itself follow `{d}`, not be pinned to ASC: the capture times are unique, so a fixed-ASC time key
#: alone determines the order and the `id` key never engages — which reproduced the identical page
#: this constant exists to prevent. Ascending therefore means oldest traffic first, the FIFO order
#: for a queue nobody has worked yet; descending means newest first.
#:
#: `{d}` stays on `a.id` as the final key, so the result is always a total order and paging can
#: never repeat or skip an alert.
TIE_BREAK = ("a.evidence_priority ASC, a.requires_review DESC, "
             + FLOW_TIME + " {d}, a.id {d}")

#: What a client may sort by. `queue` is the contract order and the default; the rest are
#: inspection tools. Every one ends in the tie-break above, so paging is stable — without a total
#: order two pages can repeat an alert or skip one.
SORT_COLUMNS: Mapping[str, str] = {
    "queue": QUEUE_ORDER_QUALIFIED,
    "combined_score": "a.combined_score {d}, " + TIE_BREAK,
    "detection_score": "a.detection_score {d}, " + TIE_BREAK,
    "created_at": "a.created_at {d}, " + TIE_BREAK,
    "severity": ("CASE a.severity WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 "
                 "WHEN 'Low' THEN 3 ELSE 4 END {d}, " + TIE_BREAK),
    #: A checkable rule before a model-only guess. The key for a detector whose false positives
    #: carry an attack's full confidence, where no score-based key can separate them: measured on
    #: data/stress.db, this order reaches precision@100 1.000 where the contract order reaches 0.000.
    "evidence": "a.evidence_priority {d}, a.combined_score {d}, " + TIE_BREAK,
}

#: A detector flagged the alert: it sits in any band but the bottom one.
FLAGGED = "(a.queue_class != 'none')"

#: The verdict currently in force on an alert (feedback does not stack; the latest one counts).
EFFECTIVE_VERDICT = ("(SELECT fe.category FROM feedback_events fe WHERE fe.alert_id = a.id "
                     "ORDER BY fe.created_at DESC, fe.id DESC LIMIT 1)")


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
        elif key == "detection_min_score":
            clauses.append("a.detection_score >= ?")
            params.append(float(value))
        elif key == "detection_max_score":
            clauses.append("a.detection_score <= ?")
            params.append(float(value))
        elif key == "search":
            clauses.append("(f.src_ip LIKE ? OR f.dst_ip LIKE ? OR a.signature_rules LIKE ? "
                           "OR f.source_record_id LIKE ?)")
            like = f"%{value}%"
            params.extend([like, like, like, like])
        elif key == "verdict":  # the verdict currently in force, not any verdict ever recorded
            values = list(value)
            if not values:
                continue
            clauses.append(f"{EFFECTIVE_VERDICT} IN ({', '.join('?' * len(values))})")
            params.extend(values)
        elif key == "unjudged":
            # "Not yet judged": no verdict has ever been recorded on this alert. Deliberately the
            # same condition the queue row reports as `hasFeedback`, so the filter and the
            # "Verdict recorded" pill on the row can never disagree. This is the complement of the
            # `verdict` filter above, which asks about the verdict currently *in force*.
            if value:
                clauses.append("NOT EXISTS (SELECT 1 FROM feedback_events fe "
                               "WHERE fe.alert_id = a.id)")
        elif key == "owner_id":
            clauses.append("a.owner_id = ?")
            params.append(int(value))
        elif key == "unassigned":
            if value:
                clauses.append("a.owner_id IS NULL")
        elif key == "flow_from":
            clauses.append(f"{FLOW_TIME} >= ?")
            params.append(str(value))
        elif key == "flow_to":
            clauses.append(f"{FLOW_TIME} <= ?")
            params.append(str(value))
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


# --------------------------------------------------------------------------------------------
# Reads the console rebuild adds (B4, B5, B6). Aggregations run in SQL — one query per figure, never
# one per row — so the overview stays as fast as the queue.
# --------------------------------------------------------------------------------------------


def flow_time(flow: m.FlowRecord) -> str | None:
    """The flow's capture time as recorded in the dataset, or None when the capture had none."""
    value = flow.flow_features.get("Timestamp")
    return None if value is None else str(value)


def family_sizes(conn: sqlite3.Connection,
                 family_keys: Sequence[str | None]) -> dict[str, int]:
    """Members per family for a page of alerts, in one query."""
    keys = sorted({key for key in family_keys if key})
    if not keys:
        return {}
    rows = conn.execute(
        f"SELECT family_key, COUNT(*) AS n FROM alerts "
        f"WHERE family_key IN ({', '.join('?' * len(keys))}) GROUP BY family_key", keys)
    return {str(row["family_key"]): int(row["n"]) for row in rows}


def _top(conn: sqlite3.Connection, expr: str, *, limit: int, where: str = "",
         params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """The most frequent values of ``expr``, flagged alerts first. ``params`` bind ``expr`` first,
    then ``where``."""
    sql = (f"SELECT {expr} AS v, COUNT(*) AS n, SUM({FLAGGED}) AS fl "
           f"FROM alerts a JOIN flow_data f ON f.alert_id = a.id{where} "
           f"GROUP BY v ORDER BY fl DESC, n DESC, v LIMIT ?")
    return [{"value": str(row["v"]), "count": int(row["n"]), "flagged": int(row["fl"] or 0)}
            for row in conn.execute(sql, [*params, limit])]


def _verdict_mix(conn: sqlite3.Connection, where: str = "",
                 params: Sequence[Any] = ()) -> dict[str, int]:
    sql = (f"SELECT {EFFECTIVE_VERDICT} AS c, COUNT(*) AS n "
           f"FROM alerts a JOIN flow_data f ON f.alert_id = a.id{where} GROUP BY c")
    return {str(row["c"]): int(row["n"]) for row in conn.execute(sql, list(params))
            if row["c"] is not None}


def breakdowns(conn: sqlite3.Connection, *, limit: int = 10) -> dict[str, Any]:
    """The overview's breakdowns (B4).

    The histogram is **capture time**, bucketed by hour: these are recorded flows, so it shows when
    the traffic happened, not how fast alerts are arriving now.
    """
    histogram = [
        {"bucket": f"{row['h']}:00", "count": int(row["n"]), "flagged": int(row["fl"] or 0)}
        for row in conn.execute(
            f"SELECT substr({FLOW_TIME}, 1, 13) AS h, COUNT(*) AS n, SUM({FLAGGED}) AS fl "
            f"FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
            f"WHERE {FLOW_TIME} IS NOT NULL GROUP BY h ORDER BY h")]
    interventions = {
        str(row["code"]): int(row["n"]) for row in conn.execute(
            "SELECT json_extract(i.value, '$.code') AS code, COUNT(*) AS n "
            "FROM audit_log al, json_each(al.details, '$.outcome.interventions') AS i "
            "WHERE al.event_type IN ('GUARDRAIL_INTERVENTION', 'GUARDRAIL_REJECTION') "
            "GROUP BY code") if row["code"] is not None}
    return {
        "top_source_ips": _top(conn, "f.src_ip", limit=limit),
        "top_destination_ips": _top(conn, "f.dst_ip", limit=limit),
        "top_destination_ports": _top(conn, "f.dst_port", limit=limit),
        "verdict_mix": _verdict_mix(conn),
        "status_mix": counts_by(conn, "status"),
        "guardrail_interventions": interventions,
        "flow_time_histogram": histogram,
    }


def entity_ip(conn: sqlite3.Connection, ip: str, *, limit: int = 10) -> dict[str, Any] | None:
    """Everything the recorded flows say about one IP (B5); None when no alert involves it."""
    where = " WHERE (f.src_ip = ? OR f.dst_ip = ?)"
    params = [ip, ip]
    head = conn.execute(
        f"SELECT COUNT(*) AS n, SUM(f.src_ip = ?) AS src, SUM(f.dst_ip = ?) AS dst, "
        f"SUM({FLAGGED}) AS fl, MIN({FLOW_TIME}) AS first_seen, MAX({FLOW_TIME}) AS last_seen "
        f"FROM alerts a JOIN flow_data f ON f.alert_id = a.id{where}",
        [ip, ip, *params]).fetchone()
    if not head["n"]:
        return None

    def grouped(expr: str) -> dict[str, int]:
        return {str(row["v"]): int(row["n"]) for row in conn.execute(
            f"SELECT {expr} AS v, COUNT(*) AS n FROM alerts a "
            f"JOIN flow_data f ON f.alert_id = a.id{where} GROUP BY v", params)
            if row["v"] is not None}

    return {
        "ip": ip,
        "alerts": int(head["n"]),
        "as_source": int(head["src"] or 0),
        "as_destination": int(head["dst"] or 0),
        "flagged": int(head["fl"] or 0),
        "first_seen": head["first_seen"],
        "last_seen": head["last_seen"],
        "by_queue_class": grouped("a.queue_class"),
        "by_attack_category": grouped("a.attack_category"),
        "verdict_mix": _verdict_mix(conn, where, params),
        "top_peers": _top(conn, "CASE WHEN f.src_ip = ? THEN f.dst_ip ELSE f.src_ip END",
                          where=where, params=[ip, *params], limit=limit),
        "top_destination_ports": _top(conn, "f.dst_port", where=where, params=params,
                                      limit=limit),
    }


CONFIRMED_MALICIOUS = frozenset({"confirm_true_positive", "escalate"})


def _ip_report_recommendation(*, confirmed: int, benign: int,
                              destination_hosts: int) -> dict[str, str]:
    """Transparent prototype advice. This never mutates an alert or network control."""
    if confirmed >= 2 and benign >= 2 and abs(confirmed - benign) <= 1:
        return {
            "action": "Mixed evidence — investigate before action",
            "reason": (f"Analysts recorded {confirmed} malicious confirmations and {benign} "
                       "false-positive or expected-activity outcomes; the evidence is strongly "
                       "mixed."),
        }
    if confirmed >= 3 and confirmed >= benign + 2:
        return {
            "action": "Review for temporary block",
            "reason": (f"{confirmed} analyst-confirmed malicious alerts across "
                       f"{destination_hosts} destination hosts clearly exceed {benign} "
                       "false-positive or expected-activity outcomes."),
        }
    if confirmed >= 1:
        return {
            "action": "Investigate / monitor",
            "reason": (f"{confirmed} analyst-confirmed malicious alerts were recorded across "
                       f"{destination_hosts} destination hosts, but the evidence is limited or "
                       "does not clearly outweigh benign outcomes."),
        }
    if benign >= 3:
        return {
            "action": "Review for suppression / allow-listing",
            "reason": (f"No malicious outcome is confirmed, while analysts recorded {benign} "
                       "false-positive or expected-activity outcomes."),
        }
    return {
        "action": "Monitor",
        "reason": ("No analyst-confirmed malicious activity is available and there is not enough "
                   "benign feedback to justify suppression."),
    }


def ip_security_report(conn: sqlite3.Connection, source_ip: str, *,
                       from_date: str | None = None,
                       to_date: str | None = None) -> dict[str, Any]:
    """Build one source-IP report from capture-time flows and effective analyst verdicts.

    One joined query supplies every timeline row. Aggregations are derived from that frozen result,
    so the summary and tables cannot disagree and no per-alert query is needed.
    """
    clauses = ["f.src_ip = ?"]
    params: list[Any] = [source_ip]
    if from_date is not None:
        clauses.append(f"substr({FLOW_TIME}, 1, 10) >= ?")
        params.append(from_date)
    if to_date is not None:
        clauses.append(f"substr({FLOW_TIME}, 1, 10) <= ?")
        params.append(to_date)
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"SELECT {FLOW_TIME} AS capture_time, a.alert_ref, f.source_record_id, "
        "f.src_ip, f.dst_ip, f.dst_port, f.protocol, a.attack_category, "
        "a.detection_score, a.combined_score, a.status, "
        f"{EFFECTIVE_VERDICT} AS effective_verdict "
        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        f"WHERE {where} ORDER BY capture_time, a.id",
        params,
    ).fetchall()

    timeline = [
        {
            "capture_time": row["capture_time"],
            "alert_ref": str(row["alert_ref"]),
            "source_record_id": str(row["source_record_id"]),
            "source_ip": str(row["src_ip"]),
            "destination_ip": str(row["dst_ip"]),
            "destination_port": int(row["dst_port"]),
            "protocol": str(row["protocol"]),
            "attack_category": row["attack_category"],
            "detection_score": float(row["detection_score"]),
            "operational_score": float(row["combined_score"]),
            "effective_verdict": row["effective_verdict"],
            "status": str(row["status"]),
        }
        for row in rows
    ]
    verdicts = Counter(row["effective_verdict"] for row in timeline
                       if row["effective_verdict"] is not None)

    def confirmed(row: dict[str, Any]) -> bool:
        return row["effective_verdict"] in CONFIRMED_MALICIOUS

    behaviour: dict[str, dict[str, Any]] = {}
    hosts: dict[str, dict[str, Any]] = {}
    ports: dict[int, dict[str, Any]] = {}
    for row in timeline:
        category = str(row["attack_category"] or "No detection")
        behaviour_entry = behaviour.setdefault(
            category, {"attack_category": category, "alert_count": 0,
                       "confirmed_malicious": 0})
        behaviour_entry["alert_count"] += 1
        behaviour_entry["confirmed_malicious"] += int(confirmed(row))

        host = str(row["destination_ip"])
        host_entry = hosts.setdefault(
            host, {"destination_ip": host, "alerts": 0,
                   "confirmed_malicious": 0, "last_seen": None})
        host_entry["alerts"] += 1
        host_entry["confirmed_malicious"] += int(confirmed(row))
        seen = row["capture_time"]
        if seen is not None and (host_entry["last_seen"] is None
                                 or seen > host_entry["last_seen"]):
            host_entry["last_seen"] = seen

        port = int(row["destination_port"])
        port_entry = ports.setdefault(
            port, {"port": port, "alerts": 0, "confirmed_malicious": 0})
        port_entry["alerts"] += 1
        port_entry["confirmed_malicious"] += int(confirmed(row))

    capture_times = [str(row["capture_time"]) for row in timeline
                     if row["capture_time"] is not None]
    first_seen = min(capture_times) if capture_times else None
    last_seen = max(capture_times) if capture_times else None
    true_positive = verdicts["confirm_true_positive"]
    escalated = verdicts["escalate"]
    confirmed_count = true_positive + escalated
    false_positive = verdicts["mark_false_positive"]
    expected_activity = verdicts["mark_expected_activity"]
    benign_count = false_positive + expected_activity

    return {
        "source_ip": source_ip,
        "from_date": from_date or (first_seen[:10] if first_seen else None),
        "to_date": to_date or (last_seen[:10] if last_seen else None),
        "summary": {
            "total_alerts": len(timeline),
            "confirmed_malicious": confirmed_count,
            "true_positive": true_positive,
            "escalated": escalated,
            "false_positive": false_positive,
            "expected_activity": expected_activity,
            "needs_investigation": verdicts["needs_investigation"],
            "distinct_attack_categories": len({row["attack_category"] for row in timeline
                                                if row["attack_category"] is not None}),
            "distinct_destination_hosts": len(hosts),
            "distinct_destination_ports": len(ports),
            "first_seen": first_seen,
            "last_seen": last_seen,
        },
        "attack_behaviour": sorted(behaviour.values(),
                                   key=lambda item: (-item["alert_count"],
                                                     item["attack_category"])),
        "targeted_hosts": sorted(hosts.values(),
                                 key=lambda item: (-item["alerts"], item["destination_ip"])),
        "destination_ports": sorted(ports.values(),
                                    key=lambda item: (-item["alerts"], item["port"])),
        "timeline": timeline,
        "recommendation": _ip_report_recommendation(
            confirmed=confirmed_count, benign=benign_count, destination_hosts=len(hosts)),
    }
