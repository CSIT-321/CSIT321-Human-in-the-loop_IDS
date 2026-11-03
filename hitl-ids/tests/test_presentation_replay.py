"""Presentation Replay uses frozen inputs, real commands and durable isolated arrivals."""
import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from time import sleep
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api import alert_stream_routes, workspaces
from apps.api.main import create_app
from packages.contracts import db
from test_operational_workspaces import _client


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def test_presentation_checkpoint_arrivals_resume_and_isolation(tmp_path):
    client, operational, tokens = _client(tmp_path)
    frozen = [workspaces.WORKLOAD, workspaces.REPOSITORY / 'evaluation/protocol-v3.1-run-001/adaptive/feedback.jsonl']
    original = {str(path): digest(path) for path in [operational, *frozen]}
    body = {'reason': 'Disposable progressive V3.1 demo', 'mode': 'presentation'}
    for role in ('analyst', 'evaluator'):
        for suffix in ('prepare', 'advance', 'start', 'pause'):
            assert client.post(f'/api/admin/workspaces/v3-1-replay/{suffix}', headers=tokens[role],
                               json=body).status_code == 403
    prepared = client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=body)
    assert prepared.status_code == 200, prepared.text
    status = prepared.json()['workspaces'][1]
    assert (status['preparationMode'], status['rawRecords'], status['learningProcessed'],
            status['holdoutArrived'], status['holdoutRemaining'], status['alertCount']) == (
                'presentation', 200, 40, 10, 150, 50)
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    structure = json.loads(workspaces.REPOSITORY.joinpath('evaluation/protocol-v3.1/expected/workload-structure.json').read_text())
    with closing(sqlite3.connect(replay)) as conn:
        refs = {row[0] for row in conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2')}
        inbox = {row[0] for row in conn.execute('SELECT canonical_alert_id FROM external_alert_inbox')}
        assert refs == inbox == {item['alertRef'] for item in structure[:50]}
        assert conn.execute('SELECT count(*) FROM analyst_verdict_events').fetchone()[0] == 40
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM analyst_work WHERE status='completed'").fetchone()[0] == 40
        assert conn.execute('SELECT count(*) FROM triage_memory_lessons').fetchone()[0] == 20
        assert conn.execute("SELECT count(*) FROM triage_memory_decisions WHERE action='activate'").fetchone()[0] == 10
        assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
    assert digest(operational) == original[str(operational)]

    active = client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=body)
    assert active.status_code == 200, active.text
    endpoint = '/api/admin/workspaces/v3-1-replay/advance'
    req = {'reason': 'Present next frozen Holdout alert', 'requestId': str(uuid4()), 'count': 1}
    advanced = client.post(endpoint, headers=tokens['admin'], json=req)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()['workspaces'][1]['holdoutArrived'] == 11
    assert client.post(endpoint, headers=tokens['admin'], json=req).json()['workspaces'][1]['holdoutArrived'] == 11
    assert client.post(endpoint, headers=tokens['admin'], json={**req, 'count': 5}).status_code == 409
    five = client.post(endpoint, headers=tokens['admin'], json={**req, 'requestId': str(uuid4()), 'count': 5})
    assert five.status_code == 200, five.text
    assert five.json()['workspaces'][1]['holdoutArrived'] == 16
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0] == 56
        assert conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0] == 56
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] >= 1  # Unknown arrived first.
        unknown_ref = structure[workspaces.presentation_replay.arrival_order(structure)[10]]['alertRef']
        assert conn.execute('''SELECT count(*) FROM tier2_cases c JOIN operational_alerts_v2 a
            ON a.id=c.primary_operational_alert_id WHERE a.operational_alert_ref=?''', (unknown_ref,)).fetchone()[0] == 1
        assert conn.execute('''SELECT count(*) FROM analyst_verdict_events v JOIN operational_alerts_v2 a
            ON a.id=v.operational_alert_id WHERE a.operational_alert_ref NOT IN
            (''' + ','.join('?' for _ in range(40)) + ')',
            tuple(item['alertRef'] for item in structure[:40])).fetchone()[0] == 0
        assert not any(row[0] in refs for row in conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2 WHERE id>50'))
        assert 'oracle' not in '\n'.join(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))

    start = client.post('/api/admin/workspaces/v3-1-replay/start', headers=tokens['admin'], json=body)
    assert start.status_code == 200 and start.json()['workspaces'][1]['playbackState'] == 'running'
    assert client.post('/api/admin/workspaces/v3-1-replay/start', headers=tokens['admin'], json=body).status_code == 200
    switch = client.post('/api/admin/workspaces/operational/activate', headers=tokens['admin'], json=body)
    assert switch.status_code == 200 and switch.json()['workspaces'][1]['playbackState'] == 'paused'
    control = tmp_path / 'workspaces/control.db'
    with closing(sqlite3.connect(control)) as conn:
        assert conn.execute("SELECT count(*) FROM actions WHERE action='presentation_playback_paused'").fetchone()[0] >= 1
    workspaces.tick(operational)
    assert client.get('/api/admin/workspaces', headers=tokens['admin']).json()['workspaces'][1]['holdoutArrived'] == 16
    assert digest(operational) == original[str(operational)]
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=body).status_code == 200
    remaining = client.post(endpoint, headers=tokens['admin'], json={**req, 'requestId': str(uuid4()), 'count': 150})
    assert remaining.status_code == 200, remaining.text
    assert remaining.json()['workspaces'][1]['holdoutArrived'] == 160
    assert remaining.json()['workspaces'][1]['holdoutRemaining'] == 0
    assert remaining.json()['workspaces'][1]['playbackState'] == 'complete'
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0] == 200
        assert conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0] == 200
        assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
    assert {str(path): digest(path) for path in [operational, *frozen]} == original
    audit = client.get('/api/admin/audit/current', headers=tokens['admin'],
                       params={'category': 'WORKSPACE', 'limit': 200})
    assert audit.status_code == 200
    actions = {item['action'] for item in audit.json()['items']}
    assert {'Presentation Replay prepared', 'Presentation manually advanced',
            'Presentation playback started', 'Presentation playback paused',
            'Presentation playback completed'} <= actions


def test_automatic_tick_is_due_only_once(tmp_path):
    client, operational, tokens = _client(tmp_path)
    body = {'reason': 'Automatic replay controller test', 'mode': 'presentation'}
    assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=body).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=body).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/start', headers=tokens['admin'], json=body).status_code == 200
    control = tmp_path / 'workspaces/control.db'
    with closing(sqlite3.connect(control)) as conn:
        conn.execute("UPDATE presentation SET next_due_at='2000-01-01T00:00:00+00:00' WHERE id=1")
        conn.commit()
    workspaces.tick(operational)
    workspaces.tick(operational)
    assert client.get('/api/admin/workspaces', headers=tokens['admin']).json()['workspaces'][1]['holdoutArrived'] == 11
    with TestClient(create_app(operational)) as restarted:
        assert restarted.get('/api/admin/workspaces', headers=tokens['admin']).json()['workspaces'][1]['holdoutArrived'] == 11
        advanced = restarted.post('/api/admin/workspaces/v3-1-replay/advance', headers=tokens['admin'],
            json={'reason': 'Resume after application restart', 'requestId': str(uuid4()), 'count': 1})
        assert advanced.status_code == 200 and advanced.json()['workspaces'][1]['holdoutArrived'] == 12
    paused = client.post('/api/admin/workspaces/v3-1-replay/pause', headers=tokens['admin'], json=body)
    assert paused.status_code == 200 and paused.json()['workspaces'][1]['playbackState'] == 'paused'
    sleep(.1)
    workspaces.tick(operational)
    assert client.get('/api/admin/workspaces', headers=tokens['admin']).json()['workspaces'][1]['holdoutArrived'] == 12


def test_manual_and_automatic_arrivals_survive_long_analyst_reader_past_57(tmp_path, monkeypatch):
    client, operational, tokens = _client(tmp_path)
    body = {'reason': 'Concurrent Analyst and SSE Replay regression', 'mode': 'presentation'}
    assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=body).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=body).status_code == 200
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    control = tmp_path / 'workspaces/control.db'
    stop = threading.Event()
    errors = []

    def sse_reader():
        while not stop.is_set():
            try:
                alert_stream_routes._arrivals(replay, 0)
            except Exception as exc:
                errors.append(exc)
            sleep(.02)

    thread = threading.Thread(target=sse_reader, daemon=True)
    thread.start()
    try:
        with closing(sqlite3.connect(replay.resolve().as_uri() + '?mode=ro', uri=True)) as long_reader:
            long_reader.execute('BEGIN')
            long_reader.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()
            assert long_reader.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
            manual = client.post('/api/admin/workspaces/v3-1-replay/advance', headers=tokens['admin'],
                json={'reason': 'Manual Next Alert with reader held open', 'requestId': str(uuid4()), 'count': 1})
            assert manual.status_code == 200, manual.text
            assert manual.json()['workspaces'][1]['holdoutArrived'] == 11
            assert client.post('/api/admin/workspaces/v3-1-replay/start', headers=tokens['admin'], json=body).status_code == 200
            # Drive the actual automatic controller without waiting 5 seconds per arrival.
            for expected in range(12, 77):
                with closing(sqlite3.connect(control)) as conn:
                    conn.execute("UPDATE presentation SET next_due_at='2000-01-01T00:00:00+00:00'")
                    conn.commit()
                workspaces.tick(operational)
                with closing(sqlite3.connect(control)) as conn:
                    cursor, state = conn.execute('SELECT cursor,playback_state FROM presentation').fetchone()
                assert (cursor, state) == (expected, 'running')
            assert client.get('/api/workspace/current', headers=tokens['analyst']).status_code == 200
    finally:
        stop.set()
        thread.join(timeout=2)
    assert not errors
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0] == 116
        assert conn.execute('SELECT count(*) FROM external_operational_admission').fetchone()[0] == 116
        assert conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0] == 116
        assert not conn.execute('''SELECT external_inbox_id FROM external_operational_admission
            GROUP BY external_inbox_id HAVING count(*)>1''').fetchone()
        assert not conn.execute('''SELECT operational_alert_id FROM operational_system_routing
            GROUP BY operational_alert_id HAVING count(*)>1''').fetchone()
        assert not conn.execute('''SELECT primary_operational_alert_id FROM tier2_cases
            GROUP BY primary_operational_alert_id HAVING count(*)>1''').fetchone()
    with closing(sqlite3.connect(control)) as conn:
        assert not conn.execute("SELECT 1 FROM actions WHERE reason LIKE '%error:%'").fetchone()

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError('database is locked')

    monkeypatch.setattr(workspaces.presentation_replay, 'advance_one', locked)
    failed = client.post('/api/admin/workspaces/v3-1-replay/advance', headers=tokens['admin'],
        json={'reason': 'Bounded lock failure', 'requestId': str(uuid4()), 'count': 1})
    assert failed.status_code == 503 and failed.json()['error']['code'] == 'REPLAY_DATABASE_BUSY'
    with closing(sqlite3.connect(control)) as conn:
        assert conn.execute('SELECT cursor,playback_state FROM presentation').fetchone() == (76, 'running')
        conn.execute("UPDATE presentation SET next_due_at='2000-01-01T00:00:00+00:00'")
        conn.commit()
    workspaces.tick(operational)
    with closing(sqlite3.connect(control)) as conn:
        assert conn.execute('SELECT cursor,playback_state FROM presentation').fetchone() == (76, 'paused')
        assert 'REPLAY_DATABASE_BUSY' in conn.execute('SELECT reason FROM actions ORDER BY id DESC LIMIT 1').fetchone()[0]
