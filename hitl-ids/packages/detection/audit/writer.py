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
from collections.abc import Iterable, Mapping, Sequence
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

    def status_change(self, actor_id: int | None, alert_id: int, *, action: str,
                      from_status: m.AlertStatus, to_status: m.AlertStatus,
                      from_owner: int | None, to_owner: int | None,
                      rationale: str | None = None) -> m.AuditEntry:
        """A triage action on one alert — its status, its owner, or both (console rebuild B1)."""
        return self.record(m.AuditEntry(
            event_type="ALERT_STATUS_CHANGE", actor_id=actor_id, alert_id=alert_id,
            details=_details(rationale, action=action, from_status=from_status,
                             to_status=to_status, from_owner=from_owner, to_owner=to_owner)))

    #: How many moved members one audit entry names. The count is always exact; the list is
    #: evidence, and a family of 199 alerts would otherwise write a 199-row JSON blob per verdict.
    MAX_RECORDED_MOVES = 50

    def similar_alert_learning(self, family: m.AlertFamily, *, before: m.AlertFamily | None,
                               actor_id: int, alert_id: int, feedback_id: int,
                               members_moved: int,
                               guardrail_interventions: Mapping[str, int],
                               moves: Sequence[Any] = ()) -> m.AuditEntry:
        """A verdict changed its family's learning (S7b): the family's state before and after, and
        which members it moved, so every family-driven score change is reconstructable.

        ``moves`` are ``feedback.service.MemberMove`` records. They are stored because the count
        alone cannot be audited: "3 alerts moved" is not a record of *which* three, and a score no
        analyst ever touched is exactly the change that has to stay traceable.
        """
        def state(row: m.AlertFamily | None) -> dict[str, Any] | None:
            return None if row is None else row.model_dump(
                mode="json", exclude={"id", "family_key", "updated_at"})
        recorded = [{"alert_ref": move.alert_ref, "source_record_id": move.source_record_id,
                     "score_before": move.score_before, "score_after": move.score_after,
                     "queue_class_before": move.queue_class_before,
                     "queue_class_after": move.queue_class_after}
                    for move in list(moves)[:self.MAX_RECORDED_MOVES]]
        return self.record(m.AuditEntry(
            event_type="SIMILAR_ALERT_LEARNING", actor_id=actor_id, alert_id=alert_id,
            feedback_id=feedback_id,
            details={"family_key": family.family_key, "before": state(before),
                     "after": state(family), "members_moved": members_moved,
                     "members": recorded, "members_truncated": len(moves) > len(recorded),
                     "guardrail_interventions": dict(sorted(guardrail_interventions.items()))}))

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
