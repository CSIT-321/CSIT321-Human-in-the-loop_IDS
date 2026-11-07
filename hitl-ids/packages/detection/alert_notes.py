"""C6 (decision Q7 option A): append-only, owner-guarded Tier 1 notes on a V2 operational alert.

The owner check is the claim: only the analyst who holds the alert In Review adds a note. The database
(migration 25, operational_note_owner) refuses any other insert, so this module is not the only guard.
"""
from uuid import UUID
from pydantic import Field, field_validator
from packages.contracts import db
from packages.contracts.operational_v2 import V2Contract
from packages.detection.analyst_work import WorkConflict, _actor, _id, require_owner, now


class NoteCommand(V2Contract):
    request_id: UUID
    body: str = Field(max_length=2000)

    @field_validator('body')
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value: raise ValueError('A note cannot be empty.')
        return value


class Note(V2Contract):
    id: int
    actor_id: int
    actor_name: str
    body: str
    created_at: str


class NoteResult(V2Contract):
    replayed: bool
    note: Note


def _note(row):
    return Note(id=row['id'], actor_id=row['actor_id'], actor_name=row['actor_name'], body=row['body'], created_at=row['created_at'])


def list_notes(conn, alert_id):
    return [_note(r) for r in conn.execute(
        'SELECT * FROM operational_alert_notes WHERE operational_alert_id=? ORDER BY id', (alert_id,))]


def add_note(conn, ref, *, actor_id, request):
    request = NoteCommand.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('add_note requires foreign keys and no open transaction')
    try:
        conn.execute('BEGIN IMMEDIATE'); actor = _actor(conn, actor_id); alert_id = _id(conn, ref)
        prior = conn.execute('SELECT * FROM operational_alert_notes WHERE request_id=?', (str(request.request_id),)).fetchone()
        if prior:
            if prior['actor_id'] != actor_id or prior['operational_alert_id'] != alert_id:
                raise WorkConflict('requestId belongs to another note')
            result = NoteResult(replayed=True, note=_note(prior)); conn.commit(); return result
        require_owner(conn, alert_id, actor_id)
        cursor = conn.execute('INSERT INTO operational_alert_notes(operational_alert_id,actor_id,actor_name,body,request_id,created_at)'
                              ' VALUES (?,?,?,?,?,?)', (alert_id, actor_id, actor.display_name, request.body,
                                                        str(request.request_id), db.format_timestamp(now())))
        row = conn.execute('SELECT * FROM operational_alert_notes WHERE id=?', (cursor.lastrowid,)).fetchone()
        result = NoteResult(replayed=False, note=_note(row)); conn.commit(); return result
    except Exception:
        conn.rollback(); raise
