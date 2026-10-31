"""Authenticated routing, immutable history, concurrency and legacy isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from packages.contracts import db
from packages.detection.adapters.operational_v2 import materialize_source, read_triage
from packages.detection.adapters.staging import stage_file
from packages.detection.routing import RoutingRequest, RoutingConflict, route_alert, state_version
from packages.detection.triage_policy import TriageContext
from packages.detection.triage_policy_service import apply_triage_policy
from test_api import client, database

FIXTURE = Path(__file__).parent / 'fixtures/suricata-alerts.json'


@pytest.fixture
def staged(client, database):
    with closing(db.connect(database)) as conn:
        stage_file(conn, FIXTURE, 'routing-test')
        alert = materialize_source(conn, 'external_nids_alert', 1)
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        return alert, actor


def request(state):
    return RoutingRequest(request_id=uuid4(), expected_state_version=state_version(state), reason='Reviewed evidence')


def view(client, staged):
    return client.get(f'/api/v2/alerts/{staged[0].operational_alert_ref}/triage-state').json()


def post(client, staged, action, state=None, **kwargs):
    state = state or view(client, staged)
    body = {'requestId': str(uuid4()), 'expectedStateVersion': state['stateVersion'], 'reason': 'Reviewed evidence'}
    body.update(kwargs.pop('body', {}))
    return client.post(f'/api/v2/alerts/{staged[0].operational_alert_ref}/{action}', json=body, **kwargs)


def recommended(database, staged):
    with closing(db.connect(database)) as conn:
        return apply_triage_policy(conn, staged[0].id, actor_id=staged[1],
            expected_state=read_triage(conn, staged[0].id), context=TriageContext(unresolved_by_tier1=True))


def all_other_tables(conn):
    names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT IN ('sqlite_sequence','operational_triage_state_v2','operational_routing_audit')")]
    return {name: [tuple(row) for row in conn.execute(f'SELECT * FROM {name} ORDER BY 1')] for name in names}


def test_admission_manual_escalation_and_legacy_isolation(client, database, staged):
    with closing(db.connect(database)) as conn:
        before = all_other_tables(conn)
    original = view(client, staged)
    assert original['state']['handlingRoute'] == 'unassigned'
    admitted = post(client, staged, 'admit-tier1').json()
    assert admitted['view']['state']['handlingRoute'] == 'tier1_review'
    assert admitted['view']['state']['workflowStage'] == 'triage'
    assert not admitted['view']['state']['tier2Recommended']
    assert admitted['view']['state']['reviewRequired']
    escalated = post(client, staged, 'tier2/escalate').json()
    assert escalated['view']['state']['handlingRoute'] == 'tier2_candidate'
    assert escalated['view']['state']['workflowStage'] == 'assessment'
    assert escalated['view']['state']['decisionSource'] == 'analyst'
    assert escalated['audit']['beforeState'] == admitted['view']['state']
    assert escalated['audit']['afterState'] == escalated['view']['state']
    with closing(db.connect(database)) as conn:
        assert before == all_other_tables(conn)
        assert [row[0] for row in conn.execute('SELECT event_type FROM operational_routing_audit ORDER BY id')] == [
            'V2_TIER1_ADMITTED', 'V2_MANUAL_ESCALATION']
        for sql in ('UPDATE operational_routing_audit SET reason=\'changed\'',
                    'DELETE FROM operational_routing_audit',
                    'INSERT OR REPLACE INTO operational_routing_audit SELECT * FROM operational_routing_audit'):
            with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                conn.execute(sql)
            conn.rollback()


@pytest.mark.parametrize('action,event,route', [('tier2/approve', 'V2_TIER2_APPROVED', 'tier2_candidate'),
    ('tier2/reject', 'V2_TIER2_REJECTED', 'tier1_review')])
def test_recommendation_and_human_decision_separate(client, database, staged, action, event, route):
    recommended(database, staged)
    before = view(client, staged)
    assert before['state']['tier2Recommended'] and before['state']['handlingRoute'] == 'tier1_review'
    result = post(client, staged, action).json()
    assert result['view']['state']['handlingRoute'] == route
    assert result['audit']['eventType'] == event
    assert result['audit']['beforeState'] == before['state']
    for key in ('tier2RecommendationReasons', 'tier2Recommended', 'operationalPriority', 'priorityBand', 'triagePolicyVersion'):
        assert result['view']['state'][key] == before['state'][key]
    assert result['view']['stateVersion'] != before['stateVersion']
    with closing(db.connect(database)) as conn:
        with pytest.raises(ValueError, match='cannot overwrite'):
            apply_triage_policy(conn, staged[0].id, actor_id=staged[1], expected_state=read_triage(conn, staged[0].id))


@pytest.mark.parametrize('action', ['tier2/approve', 'tier2/reject', 'tier2/escalate'])
def test_unassigned_cannot_skip_tier1(client, staged, action):
    assert post(client, staged, action).status_code == 409


@pytest.mark.parametrize('action', ['tier2/approve', 'tier2/reject'])
def test_requires_recommendation(client, staged, action):
    assert post(client, staged, 'admit-tier1').status_code == 200
    assert post(client, staged, action).status_code == 409


@pytest.mark.parametrize('action', ['admit-tier1', 'tier2/approve', 'tier2/reject', 'tier2/escalate'])
def test_candidate_terminal_in_this_increment(client, staged, action):
    post(client, staged, 'admit-tier1')
    post(client, staged, 'tier2/escalate')
    assert post(client, staged, action).status_code == 409


def test_stale_retry_collision_and_no_state_rewind(client, database, staged):
    before = view(client, staged)
    key = str(uuid4())
    first = post(client, staged, 'admit-tier1', before, body={'requestId': key}).json()
    assert post(client, staged, 'tier2/escalate', before).status_code == 409
    assert post(client, staged, 'tier2/escalate').status_code == 200
    retry = post(client, staged, 'admit-tier1', before, body={'requestId': key}).json()
    assert retry['replayed'] and retry['audit'] == first['audit']
    assert retry['view']['state']['handlingRoute'] == 'tier2_candidate'
    assert post(client, staged, 'admit-tier1', before, body={'requestId': key, 'reason': 'different'}).status_code == 409
    assert post(client, staged, 'admit-tier1', before, body={'requestId': key},
                headers={'Authorization': f"Bearer {client.tokens['admin']}"}).status_code == 409
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == 2


@pytest.mark.parametrize('action', ['admit-tier1', 'tier2/approve', 'tier2/reject', 'tier2/escalate'])
def test_evaluator_and_unauthenticated_denied(client, staged, action):
    assert post(client, staged, action, headers={'Authorization': f"Bearer {client.tokens['evaluator']}"}).status_code == 403
    assert post(client, staged, action, headers={'Authorization': ''}).status_code == 401
    result = client.get(f'/api/v2/alerts/{staged[0].operational_alert_ref}/triage-state',
                        headers={'Authorization': f"Bearer {client.tokens['evaluator']}"})
    assert result.status_code == 200 and result.json()['allowedActions'] == []


def test_admin_matches_existing_triage_rights(client, staged):
    assert post(client, staged, 'admit-tier1', headers={'Authorization': f"Bearer {client.tokens['admin']}"}).status_code == 200


@pytest.mark.parametrize('body', [{'reason': ''}, {'reason': '   '}, {'reason': 'a' * 2001},
    {'actorId': 1}, {'expectedStateVersion': 'bad'}, {'requestId': 'not-a-uuid'}])
def test_bad_requests_rejected(client, staged, body):
    assert post(client, staged, 'admit-tier1', body=body).status_code == 400


def test_atomic_failure_and_service_authorization(client, database, staged):
    with closing(db.connect(database)) as conn:
        before = read_triage(conn, staged[0].id)
        req = request(before)
        with pytest.raises(PermissionError):
            route_alert(conn, staged[0].id, actor_id=99999, action='admit_tier1', request=req)
        conn.execute("CREATE TRIGGER fail_routing BEFORE INSERT ON operational_routing_audit "
                     "BEGIN SELECT RAISE(ABORT, 'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match='injected'):
            route_alert(conn, staged[0].id, actor_id=staged[1], action='admit_tier1', request=req)
        assert read_triage(conn, staged[0].id) == before
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == 0


@pytest.mark.parametrize('same_request', [True, False])
def test_concurrent_decisions(client, database, staged, same_request):
    with closing(db.connect(database)) as conn:
        before = read_triage(conn, staged[0].id)
    req = request(before)
    def decide(index):
        with closing(db.connect(database)) as conn:
            try:
                return route_alert(conn, staged[0].id, actor_id=staged[1], action='admit_tier1',
                    request=req if same_request or index == 0 else request(before))[1]
            except RoutingConflict:
                return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, range(2)))
    assert results.count(False) == 1
    assert (True in results) if same_request else ('stale' in results)
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == 1


def test_list_pagination_missing_and_auth(client, staged):
    result = client.get('/api/v2/alerts?limit=1').json()
    assert result['page']['returned'] == 1
    assert result['items'][0]['operationalAlertRef'] == str(staged[0].operational_alert_ref)
    assert client.get('/api/v2/alerts?offset=1').json()['items'] == []
    assert client.get('/api/v2/alerts?limit=201').status_code == 400
    assert client.get('/api/v2/alerts', headers={'Authorization': ''}).status_code == 401
    assert client.get(f'/api/v2/alerts/{uuid4()}/triage-state').status_code == 404


def test_legacy_projection_routes_without_legacy_writes(client, database):
    with closing(db.connect(database)) as conn:
        legacy_id = conn.execute('SELECT id FROM alerts ORDER BY id LIMIT 1').fetchone()[0]
        alert = materialize_source(conn, 'legacy_flow_alert', legacy_id)
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        before = all_other_tables(conn)
        route_alert(conn, alert.id, actor_id=actor, action='admit_tier1', request=request(read_triage(conn, alert.id)))
        route_alert(conn, alert.id, actor_id=actor, action='manual_escalate', request=request(read_triage(conn, alert.id)))
        assert before == all_other_tables(conn)


def test_migration_six_is_additive_idempotent_and_preserves_rows(tmp_path, monkeypatch):
    migrations = db.MIGRATIONS
    path = tmp_path / 'old.db'
    with closing(db.connect(path)) as conn:
        monkeypatch.setattr(db, 'MIGRATIONS', migrations[:-1])
        db.create_schema(conn)
        stage_file(conn, FIXTURE, 'old-schema')
        alert = materialize_source(conn, 'external_nids_alert', 1)
        before = all_other_tables(conn)
        state = read_triage(conn, alert.id)
        monkeypatch.setattr(db, 'MIGRATIONS', migrations)
        trace = []
        conn.set_trace_callback(trace.append)
        assert db.migrate(conn) == [6]
        assert db.migrate(conn) == []
        assert before == all_other_tables(conn)
        assert read_triage(conn, alert.id) == state
        assert not any(sql.lstrip().upper().startswith(('DROP ', 'ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
