"""Typed, append-only audit writer (plan step S8).

Every write to ``audit_log`` goes through :class:`AuditWriter`, which builds contract-validated
:class:`~packages.contracts.models.AuditEntry` rows, persists them with
``packages.contracts.db.insert`` and reads them back with ``db.get`` — so a caller holds the stored
row, not the object it handed in, and sees exactly what a later reader will see.

NFR-02/03: the trail is append-only, and every entry names its actor, its timestamp and — where the
caller supplies one — a rationale. The class therefore offers no UPDATE or DELETE path; the
triggers in ``packages/contracts/schema.sql`` would refuse one anyway.

Transactions belong to the caller: :meth:`AuditWriter.record` never commits, so a caller can commit
an action and its audit entry — or roll back both — as one unit.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.contracts import db
from packages.contracts import models as m

#: ``export_csv`` column order — the TDM §7.2.8 columns.
CSV_COLUMNS: tuple[str, ...] = (
    "id", "created_at", "event_type", "actor_id", "alert_id", "feedback_id", "details",
)


def _details(rationale: str | None, **carried: Any) -> dict[str, Any]:
    """The ``details`` payload: this event's carried fields, plus the rationale when one is given."""
    details = dict(carried)
    if rationale is not None:
        details["rationale"] = rationale
    return details


class AuditWriter:
    """Writes and queries the append-only audit trail. The caller owns the transaction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- core ----------------------------------------------------------------------------------

    def record(self, entry: m.AuditEntry) -> m.AuditEntry:
        """Insert ``entry`` and return it as stored. Does not commit."""
        row_id = db.insert(self._conn, entry)
        stored = db.get(self._conn, m.AuditEntry, row_id)
        if stored is None:
            raise RuntimeError(f"audit entry {row_id} was not readable after insert")
        return stored

    # -- typed constructors --------------------------------------------------------------------

    def login(self, actor_id: int, *, rationale: str | None = None) -> m.AuditEntry:
        return self.record(m.AuditEntry(
            event_type="LOGIN", actor_id=actor_id, details=_details(rationale)))

    def logout(self, actor_id: int, *, rationale: str | None = None) -> m.AuditEntry:
        return self.record(m.AuditEntry(
            event_type="LOGOUT", actor_id=actor_id, details=_details(rationale)))

    def detection_run(self, run: m.DetectionRun, *, actor_id: int | None = None,
                      rationale: str | None = None) -> m.AuditEntry:
        """One detection run, with the provenance S9 needs to replay it from the trail alone."""
        return self.record(m.AuditEntry(
            event_type="DETECTION_RUN", actor_id=actor_id,
            details=_details(
                rationale, run_id=run.id, dataset_id=run.dataset_id,
                model_version=run.model_version, rule_set_version=run.rule_set_version,
                seed=run.seed, status=run.status, alert_count=run.alert_count)))

    def feedback(self, actor_id: int, alert_id: int, feedback_id: int, *,
                 category: m.FeedbackCategory, rationale: str | None = None) -> m.AuditEntry:
        return self.record(m.AuditEntry(
            event_type="FEEDBACK", actor_id=actor_id, alert_id=alert_id, feedback_id=feedback_id,
            details=_details(rationale, category=category)))

    def guardrail(self, outcome: m.GuardrailOutcome, *, alert_id: int, feedback_id: int,
                  actor_id: int | None = None) -> m.AuditEntry:
        """The decision S7 reached, stored whole so a cap or a refusal stays reconstructable."""
        event_type: m.AuditEventType = (
            "GUARDRAIL_REJECTION" if outcome.action == "rejected" else "GUARDRAIL_INTERVENTION")
        return self.record(m.AuditEntry(
            event_type=event_type, actor_id=actor_id, alert_id=alert_id, feedback_id=feedback_id,
            details={"outcome": outcome.model_dump(mode="json")}))

    def rule_change(self, rule: m.SignatureRule, *, actor_id: int, created: bool,
                    rationale: str | None = None) -> m.AuditEntry:
        return self.record(m.AuditEntry(
            event_type="RULE_CREATE" if created else "RULE_UPDATE", actor_id=actor_id,
            details=_details(
                rationale, rule_id=rule.rule_id, version=rule.version, enabled=rule.enabled)))

    def config_change(self, actor_id: int, *, key: str, old_value: Any, new_value: Any,
                      rationale: str | None = None) -> m.AuditEntry:
        return self.record(m.AuditEntry(
            event_type="CONFIG_CHANGE", actor_id=actor_id,
            details=_details(rationale, key=key, old_value=old_value, new_value=new_value)))

    # -- reads ---------------------------------------------------------------------------------

    def query(self, *, actor_id: int | None = None, event_types: Iterable[str] | None = None,
              since: datetime | None = None, until: datetime | None = None,
              alert_id: int | None = None, limit: int | None = None) -> list[m.AuditEntry]:
        """Entries matching every supplied filter, oldest first.

        ``since`` is inclusive and ``until`` exclusive; both are encoded with
        ``db.format_timestamp``, so the text comparison is a time comparison. An empty
        ``event_types`` selects nothing. Every caller value is bound, never formatted into SQL.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if event_types is not None:
            wanted = list(event_types)
            if not wanted:
                return []
            clauses.append(f"event_type IN ({', '.join('?' * len(wanted))})")
            params.extend(wanted)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(db.format_timestamp(since))
        if until is not None:
            clauses.append("created_at < ?")
            params.append(db.format_timestamp(until))
        if alert_id is not None:
            clauses.append("alert_id = ?")
            params.append(alert_id)
        sql = "SELECT * FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [db.from_row(m.AuditEntry, row) for row in self._conn.execute(sql, params)]

    def export_csv(self, entries: Iterable[m.AuditEntry], path: str | Path) -> int:
        """Write ``entries`` to ``path`` and return the number of data rows written.

        ``details`` is compact JSON with sorted keys, so two exports of the same trail are
        byte-identical; the header is always written.
        """
        written = 0
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
            writer.writeheader()
            for entry in entries:
                writer.writerow({
                    "id": entry.id,
                    "created_at": db.format_timestamp(entry.created_at),
                    "event_type": entry.event_type,
                    "actor_id": entry.actor_id,
                    "alert_id": entry.alert_id,
                    "feedback_id": entry.feedback_id,
                    "details": json.dumps(entry.details, sort_keys=True, separators=(",", ":")),
                })
                written += 1
        return written
