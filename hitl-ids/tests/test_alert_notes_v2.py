"""C6 (decision Q7 option A, approved 2026-11-08): Tier 1 investigation notes on the V2 operational alert.

- Append-only: no update, no delete, no replace. The database refuses each one.
- Owner-guarded: only the analyst who holds the claim (In Review) adds a note. The database refuses a note
  from anyone else, so a bypass of the Python guard still fails.
- Everyone with read access reads the notes, oldest first.
- A retry with the same request id adds nothing. The same request id from another actor or alert is refused.
- Body is 1-2000 characters after trimming.
- The notes stay after the claim ends (verdict, escalation or release).
"""
from contextlib import closing
from uuid import uuid4
import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db
from packages.detection import alert_notes as notes
from packages.detection import analyst_work as work
from test_analyst_work_claim import headers, setup  # noqa: F401  (fixture: users 1-3 analysts, 4 evaluator, 5 admin)
from work_claim_fixture import claim_work


def add(c, alert, actor, body='Source host is the lab scanner.', request_id=None):
    return notes.add_note(c, alert.operational_alert_ref, actor_id=actor,
                          request=notes.NoteCommand(request_id=request_id or uuid4(), body=body))


def test_the_owner_adds_notes_and_everyone_reads_them_oldest_first(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        first = add(c, a, 1, '  Source host is the lab scanner.  ')
        second = add(c, a, 1, 'Asked IT to confirm.')
        assert not first.replayed and first.note.body == 'Source host is the lab scanner.'
        assert first.note.actor_name == 'Analyst 1' and first.note.created_at
        listed = notes.list_notes(c, a.id)
        assert [n.body for n in listed] == ['Source host is the lab scanner.', 'Asked IT to confirm.']
        assert listed[1].id == second.note.id


def test_no_one_but_the_owner_can_add_a_note(setup):
    path, alerts = setup
    a, unclaimed = alerts[0], alerts[1]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(work.WorkConflict):
            add(c, a, 2)                      # another analyst
        with pytest.raises(work.WorkConflict):
            add(c, a, 5)                      # an administrator is not the owner
        with pytest.raises(work.WorkConflict):
            add(c, unclaimed, 1)              # no claim at all
        with pytest.raises(PermissionError):
            add(c, a, 4)                      # an evaluator, by role
        assert notes.list_notes(c, a.id) == [] and notes.list_notes(c, unclaimed.id) == []


def test_the_database_refuses_a_note_from_a_non_owner_even_without_the_python_guard(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(sqlite3.IntegrityError, match='owner'):
            c.execute("INSERT INTO operational_alert_notes(operational_alert_id,actor_id,actor_name,body,request_id,created_at)"
                      " VALUES (?,2,'Analyst 2','bypass',?, '2026-11-08T00:00:00.000000Z')", (a.id, str(uuid4())))
        c.rollback()


def test_notes_cannot_be_edited_deleted_or_replaced(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        note = add(c, a, 1).note
        for sql in ("UPDATE operational_alert_notes SET body='changed' WHERE id=?",
                    "DELETE FROM operational_alert_notes WHERE id=?"):
            with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                c.execute(sql, (note.id,))
            c.rollback()
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            c.execute("INSERT INTO operational_alert_notes(id,operational_alert_id,actor_id,actor_name,body,request_id,created_at)"
                      " VALUES (?,?,1,'Analyst 1','replace',?,'2026-11-08T00:00:00.000000Z')", (note.id, a.id, str(uuid4())))
        c.rollback()
        assert [n.body for n in notes.list_notes(c, a.id)] == ['Source host is the lab scanner.']


def test_a_retry_with_the_same_request_id_adds_nothing(setup):
    path, alerts = setup
    a, b = alerts[0], alerts[1]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        claim_work(c, b, actor_id=1)
        rid = uuid4()
        first = add(c, a, 1, 'Once', request_id=rid)
        again = add(c, a, 1, 'Once', request_id=rid)
        assert again.replayed and again.note.id == first.note.id
        assert len(notes.list_notes(c, a.id)) == 1
        with pytest.raises(work.WorkConflict, match='requestId'):
            add(c, b, 1, 'Once', request_id=rid)


@pytest.mark.parametrize('body', ['', '   ', 'x' * 2001])
def test_the_body_must_be_1_to_2000_characters(setup, body):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(ValueError):
            add(c, a, 1, body)
        assert notes.list_notes(c, a.id) == []


def test_notes_stay_after_the_claim_ends(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claimed = claim_work(c, a, actor_id=1)
        add(c, a, 1, 'Kept after release')
        work.release(c, a.operational_alert_ref, actor_id=1,
                     request=work.ReleaseCommand(request_id=uuid4(), expected_revision=claimed.revision))
        assert [n.body for n in notes.list_notes(c, a.id)] == ['Kept after release']
        with pytest.raises(work.WorkConflict):
            add(c, a, 1, 'Not the owner any more')


def test_the_api_reads_and_adds_notes_with_the_same_rules(setup):
    path, alerts = setup
    a = alerts[0]
    ref = a.operational_alert_ref
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
    with TestClient(create_app(path)) as client:
        rid = str(uuid4())
        ok = client.post(f'/api/v2/alerts/{ref}/notes', headers=headers(path, 1), json={'requestId': rid, 'body': 'Checked the source host.'})
        assert ok.status_code == 200 and ok.json()['note']['body'] == 'Checked the source host.' and not ok.json()['replayed']
        assert client.post(f'/api/v2/alerts/{ref}/notes', headers=headers(path, 1), json={'requestId': rid, 'body': 'Checked the source host.'}).json()['replayed']
        other = client.post(f'/api/v2/alerts/{ref}/notes', headers=headers(path, 2), json={'requestId': str(uuid4()), 'body': 'Not mine'})
        assert other.status_code == 409 and other.json()['error']['code'] == 'WORK_CONFLICT'
        blank = client.post(f'/api/v2/alerts/{ref}/notes', headers=headers(path, 1), json={'requestId': str(uuid4()), 'body': '   '})
        assert blank.status_code in (400, 422)
        evaluator = client.post(f'/api/v2/alerts/{ref}/notes', headers=headers(path, 4), json={'requestId': str(uuid4()), 'body': 'x'})
        assert evaluator.status_code == 403
        for reader in (2, 4, 5):
            listed = client.get(f'/api/v2/alerts/{ref}/notes', headers=headers(path, reader))
            assert listed.status_code == 200 and [n['body'] for n in listed.json()] == ['Checked the source host.']
        assert client.get(f'/api/v2/alerts/{uuid4()}/notes', headers=headers(path, 1)).status_code == 404
