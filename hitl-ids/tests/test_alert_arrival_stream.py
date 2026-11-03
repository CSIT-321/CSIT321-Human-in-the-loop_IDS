"""Arrival notifications observe committed rows without changing either workspace."""
import asyncio
import hashlib
import json
from uuid import uuid4

from apps.api import alert_stream_routes as stream
from test_operational_workspaces import _client


class Connected:
    async def is_disconnected(self):
        return False


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stream_requires_current_bearer_and_authenticates_analyst(tmp_path, monkeypatch):
    client, operational, tokens = _client(tmp_path)
    assert client.get('/api/v2/alerts/stream').status_code == 401
    assert client.get('/api/v2/alerts/stream', headers={'Authorization': 'Bearer invalid'}).status_code == 401

    async def finite(*_args):
        yield ': connected\n\n'
    monkeypatch.setattr(stream, 'stream_arrivals', finite)
    before = fingerprint(operational)
    response = client.get('/api/v2/alerts/stream', headers=tokens['analyst'])
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['x-operational-workspace'] == 'operational'
    assert response.text == ': connected\n\n'
    assert fingerprint(operational) == before


def test_replay_arrival_is_persisted_scoped_and_switch_invalidates(tmp_path, monkeypatch):
    client, operational, tokens = _client(tmp_path)
    body = {'reason': 'Disposable arrival stream test', 'mode': 'presentation'}
    assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=body).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=body).status_code == 200
    replay = tmp_path / 'workspaces/v3-1-replay.db'
    control = tmp_path / 'workspaces/control.db'
    workspace, epoch = stream._selection(control)
    assert workspace == 'v3-1-replay'
    assert stream._arrivals(replay, stream._last_id(replay)) == []
    operational_before, replay_before = fingerprint(operational), fingerprint(replay)

    async def immediate(_seconds):
        return None
    monkeypatch.setattr(stream.asyncio, 'sleep', immediate)

    async def journey():
        events = stream.stream_arrivals(Connected(), replay, control, workspace, epoch)
        assert await events.__anext__() == ': connected\n\n'
        assert fingerprint(replay) == replay_before
        response = client.post('/api/admin/workspaces/v3-1-replay/advance', headers=tokens['admin'],
                               json={'reason': 'Next persisted alert', 'requestId': str(uuid4()), 'count': 1})
        assert response.status_code == 200, response.text
        message = await events.__anext__()
        assert 'event: alert_arrived' in message
        payload = json.loads(message.split('data: ', 1)[1])
        assert payload['workspaceId'] == 'v3-1-replay'
        assert payload['eventId'].startswith('v3-1-replay:')
        assert set(payload) == {'eventId', 'workspaceId', 'operationalAlertRef', 'timestamp'}
        assert payload['operationalAlertRef'] in {row['operational_alert_ref'] for row in stream._arrivals(replay, 0)}
        assert not any(key in message.lower() for key in ('oracle', 'stratum', 'expected', 'unsafe'))
        assert fingerprint(operational) == operational_before
        assert client.post('/api/admin/workspaces/operational/activate', headers=tokens['admin'], json=body).status_code == 200
        changed = await events.__anext__()
        assert 'event: workspace_changed' in changed
        assert 'operationalAlertRef' not in changed
        assert '"operational"' in changed
        await events.aclose()

    asyncio.run(journey())
    assert fingerprint(operational) == operational_before
