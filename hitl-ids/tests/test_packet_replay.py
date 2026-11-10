"""Packet Replay: both detection chains of one capture arrive step by step in one Replay workspace.

The flow chain and the Suricata chain share one database (the system-routing guard compares only its own rows),
a flow group built over several steps equals the group built in one pass, and Operational is never written.
"""
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from uuid import uuid4

from apps.api import alert_stream_routes as stream
from apps.api import packet_replay, workspaces
from flow_group_fixture import GROUPS, grouped_database  # noqa: F401  (pytest fixture)
from test_flow_queue import membership
from test_operational_workspaces import _client

ADMIN = {'reason': 'Disposable packet replay test', 'mode': 'packet'}
ADVANCE = '/api/admin/workspaces/v3-1-replay/advance'


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_data(tmp_path, grouped, monkeypatch, cut=7):
    """A small packet-replay input: the grouped fixture's flows in two steps, one Suricata alert in each."""
    data = tmp_path / 'packet-replay'
    data.mkdir()
    shutil.copyfile(grouped, data / 'base.db')
    with closing(sqlite3.connect(data / 'base.db')) as conn:
        total = conn.execute('SELECT max(id) FROM alerts').fetchone()[0]
    steps = [{'throughAlertId': cut if step == 0 else total, 'captureTime': None} for step in range(160)]
    (data / 'steps.json').write_text(json.dumps(steps), encoding='utf-8')
    with workspaces.WORKLOAD.open(encoding='utf-8') as source:
        events = [json.loads(source.readline()) for _ in range(2)]
    (data / 'eve.jsonl').write_text(''.join(
        json.dumps({'step': step, 'linkedRecord': None, 'event': event}) + '\n'
        for step, event in enumerate(events)), encoding='utf-8')
    monkeypatch.setattr(packet_replay, 'DATA', data)
    return total


def replay_state(response):
    assert response.status_code == 200, response.text
    return response.json()['workspaces'][1]


def test_packet_replay_needs_its_data(tmp_path, monkeypatch):
    client, _, tokens = _client(tmp_path)
    monkeypatch.setattr(packet_replay, 'DATA', tmp_path / 'absent')
    response = client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=ADMIN)
    assert (response.status_code, response.json()['error']['code']) == (503, 'REPLAY_WORKLOAD_UNAVAILABLE')
    assert not (tmp_path / 'workspaces/v3-1-replay.db').exists()


def test_both_chains_arrive_step_by_step_in_one_workspace(tmp_path, grouped_database, monkeypatch):
    client, operational, tokens = _client(tmp_path)
    total = replay_data(tmp_path, grouped_database, monkeypatch)
    before = digest(operational)
    for role in ('analyst', 'evaluator'):
        assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens[role], json=ADMIN).status_code == 403

    prepared = replay_state(client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=ADMIN))
    assert (prepared['preparationMode'], prepared['rawRecords'], prepared['alertCount'], prepared['holdoutArrived'],
            prepared['holdoutRemaining'], prepared['playbackState'], prepared['learningProcessed']) == (
                'packet', total, 0, 0, 160, 'paused', 0)
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=ADMIN).status_code == 200
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    assert stream._flow_arrival(replay, 0) is None

    def advance():
        return replay_state(client.post(ADVANCE, headers=tokens['admin'], json={
            'reason': 'Next capture step', 'requestId': str(uuid4()), 'count': 1}))

    first = advance()
    assert (first['holdoutArrived'], first['holdoutRemaining'], first['stagedAlerts']) == (1, 159, 1)
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM alerts').fetchone()[0] == 7
        kinds = dict(conn.execute('SELECT source_kind, count(*) FROM operational_alerts_v2 GROUP BY 1'))
    assert kinds['external_nids_alert'] == 1 and kinds['legacy_flow_alert'] >= 1
    flow_event = stream._flow_arrival(replay, 0)
    assert flow_event is not None and stream._flow_arrival(replay, flow_event['id']) is None

    second = advance()
    assert (second['holdoutArrived'], second['stagedAlerts']) == (2, 2)
    with closing(sqlite3.connect(replay)) as conn:
        conn.row_factory = sqlite3.Row
        # The step cut is inside a group: the group built over two steps is the group built in one pass.
        assert sorted(membership(conn).values()) == sorted(GROUPS.values())
        assert conn.execute('SELECT count(*) FROM alerts').fetchone()[0] == total
        unrouted = conn.execute('SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN operational_system_routing s '
                                'ON s.operational_alert_id=o.id WHERE s.operational_alert_id IS NULL').fetchone()[0]
        # The second Suricata alert was admitted into a database that already held routed flow alerts.
        admitted = conn.execute('SELECT count(*) FROM external_operational_admission').fetchone()[0]
        assert (unrouted, admitted) == (0, 2)
        assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
        queue = conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]
    assert second['alertCount'] == queue

    third = advance()                                   # a step with nothing new changes only the cursor
    assert (third['holdoutArrived'], third['alertCount'], third['stagedAlerts']) == (3, queue, 2)
    assert digest(operational) == before


def test_packet_replay_without_the_flow_chain(tmp_path, grouped_database, monkeypatch):
    """flowChain=false: the capture's flows never enter the database; the queue holds only Suricata alerts."""
    client, _, tokens = _client(tmp_path)
    replay_data(tmp_path, grouped_database, monkeypatch)
    prepared = replay_state(client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'],
                                        json={**ADMIN, 'flowChain': False}))
    assert prepared['flowChainEnabled'] is False
    client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=ADMIN)
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    for _ in range(2):
        replay_state(client.post(ADVANCE, headers=tokens['admin'], json={
            'reason': 'Pure Suricata step', 'requestId': str(uuid4()), 'count': 1}))
    with closing(sqlite3.connect(replay)) as conn:
        assert conn.execute('SELECT count(*) FROM alerts').fetchone()[0] == 0        # no flow copied
        assert conn.execute('SELECT count(*) FROM flow_data').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM operational_alerts_v2 "
                            "WHERE source_kind='legacy_flow_alert'").fetchone()[0] == 0
    state = replay_state(client.post(ADVANCE, headers=tokens['admin'], json={
        'reason': 'Pure Suricata step', 'requestId': str(uuid4()), 'count': 1}))
    assert state['alertCount'] == state['stagedAlerts'] == 2                          # only Suricata queue items
    actions = [item['action'] for item in client.get('/api/admin/workspaces', headers=tokens['admin']).json()['actions']]
    assert 'packet_replay_prepared' in actions and 'presentation_manual_advance' in actions
