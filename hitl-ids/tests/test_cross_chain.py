"""Cross-chain join: one queue item per connection, the more severe reading shown, nothing deleted."""
import json
import sqlite3
from contextlib import closing

from packages.detection import cross_chain
from packages.detection.cross_chain import community_id
from test_packet_replay import ADMIN, ADVANCE, replay_data, replay_state
from test_operational_workspaces import _client
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)
from uuid import uuid4


def test_community_id_matches_the_published_vector_in_both_directions():
    # corelight/community-id-spec baseline, TCP 128.232.110.120:34855 -> 66.35.250.204:80, seed 0
    expected = "1:LQU9qZlK+B5F3KDmev6m5PMibrg="
    assert community_id("128.232.110.120", 34855, "66.35.250.204", 80, "TCP") == expected
    assert community_id("66.35.250.204", 80, "128.232.110.120", 34855, "tcp") == expected
    assert community_id("10.0.0.1", 1, "10.0.0.2", 2, "GRE-UNKNOWN") is None


def _suricata_on_a_flow(tmp_path, grouped, monkeypatch, severity):
    """Replay input: the grouped fixture's flows, and one Suricata alert on the 5-tuple of its first flow."""
    replay_data(tmp_path, grouped, monkeypatch)
    data = tmp_path / 'packet-replay'
    with closing(sqlite3.connect(data / 'base.db')) as conn:
        src, sport, dst, dport, proto, features = conn.execute(
            'SELECT src_ip, src_port, dst_ip, dst_port, protocol, flow_features FROM flow_data ORDER BY alert_id'
        ).fetchone()
    when = json.loads(features)['Timestamp']
    lines = [json.loads(line) for line in (data / 'eve.jsonl').read_text(encoding='utf-8').splitlines()]
    event = lines[0]['event']
    event.update(src_ip=src, src_port=sport, dest_ip=dst, dest_port=dport, proto=proto,
                 timestamp=when.replace(' ', 'T') + ('' if '+' in when else '+0000'))
    event['alert']['severity'] = severity
    (data / 'eve.jsonl').write_text(json.dumps({'step': 0, 'linkedRecord': None, 'event': event}) + '\n',
                                    encoding='utf-8')
    return community_id(src, sport, dst, dport, proto)


def _run_one_step(tmp_path):
    client, _, tokens = _client(tmp_path)
    assert client.post('/api/admin/workspaces/v3-1-replay/prepare', headers=tokens['admin'], json=ADMIN).status_code == 200
    assert client.post('/api/admin/workspaces/v3-1-replay/activate', headers=tokens['admin'], json=ADMIN).status_code == 200
    state = replay_state(client.post(ADVANCE, headers=tokens['admin'], json={
        'reason': 'Join step', 'requestId': str(uuid4()), 'count': 1}))
    return client, tokens, state, tmp_path / 'workspaces/v3-1-replay.db'


def test_the_join_hides_one_item_and_keeps_both_rows(tmp_path, grouped_database, monkeypatch):
    cid = _suricata_on_a_flow(tmp_path, grouped_database, monkeypatch, severity=1)
    client, tokens, state, replay = _run_one_step(tmp_path)
    with closing(sqlite3.connect(replay)) as conn:
        links = conn.execute('SELECT community_id, suricata_operational_alert_id, flow_operational_alert_id, '
                             'shown_operational_alert_id, hidden_operational_alert_id FROM cross_chain_links').fetchall()
        assert len(links) == 1 and links[0][0] == cid
        _, suricata, flow, shown, hidden = links[0]
        assert {shown, hidden} == {suricata, flow}
        total = conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]
        visible = conn.execute(f'SELECT count(*) FROM {cross_chain.VISIBLE}').fetchone()[0]
        # Nothing deleted: both rows stay; the queue shows one item for the connection.
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2 WHERE id IN (?,?)', (suricata, flow)).fetchone()[0] == 2
        assert visible == total - 1
        try:
            conn.execute('DELETE FROM cross_chain_links')
            raise AssertionError('cross_chain_links must be append-only')
        except sqlite3.DatabaseError:
            pass
    assert state['alertCount'] == visible
    queue = client.get('/api/v2/operational-queue?limit=500', headers=tokens['analyst'])
    if queue.status_code == 200:      # the queue route lists only visible items
        assert queue.json()['total'] == visible


def test_the_more_severe_reading_is_shown(tmp_path, grouped_database, monkeypatch):
    _suricata_on_a_flow(tmp_path, grouped_database, monkeypatch, severity=1)
    _, _, _, replay = _run_one_step(tmp_path)
    with closing(sqlite3.connect(replay)) as conn:
        suricata, flow, shown, reason = conn.execute(
            'SELECT suricata_operational_alert_id, flow_operational_alert_id, shown_operational_alert_id, reason '
            'FROM cross_chain_links').fetchone()
        rank = {}
        for item in (suricata, flow):
            rank[item] = cross_chain._strength(conn, item)
    assert shown == (suricata if rank[suricata] > rank[flow] else flow)
    assert reason == ('suricata more severe' if shown == suricata else 'flow as severe or more')
