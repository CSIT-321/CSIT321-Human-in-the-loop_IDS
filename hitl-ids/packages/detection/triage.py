"""Alert status, ownership and notes (console rebuild, B1 and B2).

The four triage controls every SOC console offers are owner, status, severity and a closing
classification (`docs/research/soc-console-research.md` §4). Verdicts already carry the
classification and the score; this module carries the other two, and the analyst's notes.

**Status is workflow, not judgement.** Changing status never moves a score, never touches a family
and never involves the guardrails — those belong to verdicts (`feedback/service.py`). Keeping the two
apart is what lets an analyst claim an alert, work it and close it without the ranking shifting under
them.

**Transitions are explicit.** An alert is new, claimed, in progress, resolved or dismissed. Working
an alert (claimed, in progress) makes the actor its owner when it has none; returning it to `new`
releases it; a closed alert (resolved, dismissed) can only be reopened to `in_progress`. A refused
transition raises :class:`TransitionRefused`, which the API reports as a conflict.

Every change writes an ``ALERT_STATUS_CHANGE`` audit entry in the same transaction as the update.
Notes are append-only at the database (migration 1), so a correction is a new note.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import AuditWriter

#: The allowed next statuses for each status.
TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"claimed", "in_progress", "resolved", "dismissed"}),
    "claimed": frozenset({"new", "in_progress", "resolved", "dismissed"}),
    "in_progress": frozenset({"new", "claimed", "resolved", "dismissed"}),
    "resolved": frozenset({"in_progress"}),
    "dismissed": frozenset({"in_progress"}),
}
CLOSED = frozenset({"resolved", "dismissed"})
WORKING = frozenset({"claimed", "in_progress"})


class TransitionRefused(ValueError):
    """The requested status or owner change is not allowed from the alert's current state."""


@dataclass(frozen=True)
class TriageResult:
    alert: m.Alert
    audit: m.AuditEntry


def _label(status: str) -> str:
    return status.replace("_", " ")


def _load(conn: sqlite3.Connection, alert_id: int) -> m.Alert:
    alert = db.get(conn, m.Alert, alert_id)
    if alert is None:
        raise LookupError(f"no alert {alert_id}")
    return alert


def change_status(conn: sqlite3.Connection, *, alert_id: int, actor_id: int | None,
                  to_status: m.AlertStatus, reason: str | None = None,
                  now: datetime | None = None) -> TriageResult:
    alert = _load(conn, alert_id)
    if to_status == alert.status:
        raise TransitionRefused(f"The alert is already {_label(to_status)}.")
    allowed = TRANSITIONS[alert.status]
    if to_status not in allowed:
        raise TransitionRefused(
            f"An alert that is {_label(alert.status)} cannot become {_label(to_status)}; "
            f"allowed: {', '.join(sorted(_label(s) for s in allowed))}.")
    owner = alert.owner_id
    if to_status in WORKING and owner is None:
        owner = actor_id
    if to_status == "new":
        owner = None
    return _write(conn, alert, status=to_status, owner=owner, actor_id=actor_id,
                  action="status", reason=reason, now=now)


def assign(conn: sqlite3.Connection, *, alert_id: int, actor_id: int | None,
           owner_id: int | None, reason: str | None = None,
           now: datetime | None = None) -> TriageResult:
    alert = _load(conn, alert_id)
    if alert.status in CLOSED:
        raise TransitionRefused("A closed alert cannot be reassigned; reopen it first.")
    if owner_id == alert.owner_id:
        raise TransitionRefused("The alert already has that owner." if owner_id is not None
                                else "The alert is already unassigned.")
    status: m.AlertStatus = alert.status
    if owner_id is not None and status == "new":
        status = "claimed"
    if owner_id is None and status == "claimed":
        status = "new"
    return _write(conn, alert, status=status, owner=owner_id, actor_id=actor_id,
                  action="assign", reason=reason, now=now)


def _write(conn: sqlite3.Connection, alert: m.Alert, *, status: m.AlertStatus, owner: int | None,
           actor_id: int | None, action: str, reason: str | None,
           now: datetime | None) -> TriageResult:
    alert_id = int(alert.id or 0)
    moment = now or m.utc_now()
    with conn:
        conn.execute("UPDATE alerts SET status = ?, owner_id = ?, updated_at = ? WHERE id = ?",
                     (status, owner, db.format_timestamp(moment), alert_id))
        entry = AuditWriter(conn).status_change(
            actor_id, alert_id, action=action, from_status=alert.status, to_status=status,
            from_owner=alert.owner_id, to_owner=owner, rationale=reason)
    return TriageResult(alert=_load(conn, alert_id), audit=entry)


def add_note(conn: sqlite3.Connection, *, alert_id: int, user_id: int, body: str,
             now: datetime | None = None) -> m.AlertNote:
    text = body.strip()
    if not text:
        raise ValueError("A note cannot be empty.")
    _load(conn, alert_id)
    with conn:
        note_id = db.insert(conn, m.AlertNote(alert_id=alert_id, user_id=user_id, body=text,
                                              created_at=now or m.utc_now()))
    stored = db.get(conn, m.AlertNote, note_id)
    if stored is None:
        raise RuntimeError(f"note {note_id} was not readable after insert")
    return stored


def notes_for_alert(conn: sqlite3.Connection, alert_id: int) -> list[m.AlertNote]:
    """The whole thread, oldest first."""
    return [db.from_row(m.AlertNote, row) for row in conn.execute(
        "SELECT * FROM alert_notes WHERE alert_id = ? ORDER BY created_at, id", (alert_id,))]
