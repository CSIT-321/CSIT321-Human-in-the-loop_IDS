"""Atomic direct escalation, compatibility recovery, request identity and concurrent writers."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from packages.contracts import db
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.routing import RoutingConflict, state_version
from packages.detection.tier2_cases import CaseConflict, CaseCommand, mutate_case
from packages.detection.tier2_escalation import EscalateCaseRequest, escalate_case
from test_api import client, database
from test_routing_workflow import staged, post, view, recommended


def direct(client, staged, body, **kwargs):
    return client.post(f'/api/v2/alerts/{staged[0].operational_alert_ref}/tier2/escalate-case', json=body, **kwargs)


def body_for(client, staged, action='manual_escalate'):
    return dict(requestId=str(uuid4()), expectedStateVersion=view(client, staged)['stateVersion'],
                reason='Source-host evidence needs deeper investigation', action=action)


@pytest.mark.parametrize('action', ['manual_escalate', 'approve_tier2'])
def test_direct_case_and_authenticated_snapshot(client, database, staged, action):
    if action == 'approve_tier2':
        recommended(database, staged)
    else:
        assert post(client, staged, 'admit-tier1').status_code == 200
    before = view(client, staged)
    body = body_for(client, staged, action)
    with closing(db.connect(database)) as conn:
        evidence = read_projection(conn, staged[0].id)
        untouched = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table}')]
                     for table in ('alerts', 'feedback_events', 'operational_alerts_v2', 'triage_policy_audit')
                     if conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone()}
    result = direct(client, staged, body)
    assert result.status_code == 200, result.text
    result = result.json()
    case = result['case']
    assert result['view']['state']['handlingRoute'] == 'tier2_case'
    assert result['view']['state']['workflowStage'] == 'investigation'
    assert result['view']['caseRef'] == case['caseRef']
    assert case['status'] == 'open' and case['revision'] == 1
    assert case['title'] == evidence.detection_title + ' — Tier 2 Investigation'
    snap = case['snapshot']
    assert snap['detector'] == evidence.model_dump(mode='json', by_alias=True)
    assert snap['routingDecision'] == result['audit']
    assert snap['routingDecision']['actorId'] == case['createdByActorId'] == staged[1]
    assert snap['routingDecision']['beforeState'] == before['state']
    assert snap['routingDecision']['afterState'] == snap['triage']
    assert snap['escalationReason'] == body['reason']
    assert body['reason'] in snap['tier1HandoffSummary'] and body['reason'] in snap['creationReason']
    assert evidence.detector_name in snap['tier1HandoffSummary']
    assert evidence.detection_title in snap['tier1HandoffSummary']
    assert before['state']['reviewReason'][:400] in snap['tier1HandoffSummary']
    with closing(db.connect(database)) as conn:
        for table, rows in untouched.items():
            assert rows == [tuple(row) for row in conn.execute(f'SELECT * FROM {table}')]
        event = conn.execute('SELECT * FROM tier2_case_events WHERE id=?', (result['eventId'],)).fetchone()
        assert event['event_type'] == 'V2_TIER2_CASE_CREATED' and event['actor_id'] == staged[1]
        assert json.loads(event['after_state'])['handlingRoute'] == 'tier2_case'
        assert not conn.execute('SELECT 1 FROM response_recommendations').fetchone()


def test_retry_bound_to_actor_payload_alert_and_action(client, database, staged):
    post(client, staged, 'admit-tier1')
    body = body_for(client, staged)
    first = direct(client, staged, body).json()
    with closing(db.connect(database)) as conn:
        mutate_case(conn, first['case']['caseRef'], actor_id=staged[1], action='start',
                    request=CaseCommand(request_id=uuid4(), expected_revision=1, reason='Start deeper investigation'))
    replay = direct(client, staged, body).json()
    assert replay['replayed'] and replay['case']['caseRef'] == first['case']['caseRef']
    assert replay['case']['status'] == 'investigating'  # Never rewind later case work.
    assert replay['eventId'] == first['eventId'] and replay['audit'] == first['audit']
    for changed in ({'reason': 'Different'}, {'expectedStateVersion': '0'*64}, {'action': 'approve_tier2'}):
        response = direct(client, staged, {**body, **changed})
        assert response.status_code == 409 and response.json()['error']['code'] == 'ROUTING_CONFLICT'
    assert direct(client, staged, body, headers={'Authorization': f"Bearer {client.tokens['admin']}"}).status_code == 409
    assert client.post(f'/api/v2/alerts/{uuid4()}/tier2/escalate-case', json=body).status_code == 409
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 1


@pytest.mark.parametrize('same_request', [True, False])
def test_concurrent_direct_escalations_create_one_case(client, database, staged, same_request):
    post(client, staged, 'admit-tier1')
    request = EscalateCaseRequest.model_validate(body_for(client, staged))
    def run(index):
        req = request if same_request or index == 0 else request.model_copy(update={'request_id': uuid4()})
        with closing(db.connect(database)) as conn:
            try:
                return escalate_case(conn, staged[0].operational_alert_ref, actor_id=staged[1], request=req)
            except (RoutingConflict, CaseConflict):
                return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(result != 'stale' and not result.replayed for result in results) == 1
    if same_request:
        assert results[0].case.case_ref == results[1].case.case_ref
        assert sum(result.replayed for result in results) == 1
    else:
        assert results.count('stale') == 1
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM operational_routing_audit WHERE action='manual_escalate'").fetchone()[0] == 1


@pytest.mark.parametrize('table', ['operational_routing_audit', 'tier2_cases', 'tier2_case_state', 'tier2_case_events'])
@pytest.mark.parametrize('action', ['manual_escalate', 'approve_tier2'])
def test_failure_after_escalation_begins_rolls_back_every_write(client, database, staged, table, action):
    if action == 'approve_tier2':
        recommended(database, staged)
    else:
        post(client, staged, 'admit-tier1')
    before = view(client, staged)
    request = EscalateCaseRequest.model_validate(body_for(client, staged, action))
    with closing(db.connect(database)) as conn:
        count = conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0]
        conn.execute(f"CREATE TRIGGER fail_direct BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected case failure'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match='injected case failure'):
            escalate_case(conn, staged[0].operational_alert_ref, actor_id=staged[1], request=request)
        assert not conn.in_transaction
        assert read_triage(conn, staged[0].id).model_dump(mode='json', by_alias=True) == before['state']
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == count
        for name in ('tier2_cases', 'tier2_case_state', 'tier2_case_events'):
            assert conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0] == 0
        # The same logical request can succeed after a transient storage failure is removed.
        conn.execute('DROP TRIGGER fail_direct')
        conn.commit()
        result = escalate_case(conn, staged[0].operational_alert_ref, actor_id=staged[1], request=request)
        assert not result.replayed and read_triage(conn, staged[0].id).handling_route == 'tier2_case'


def test_historical_recovery_is_explicit_and_get_is_readonly(client, database, staged):
    post(client, staged, 'admit-tier1')
    old = post(client, staged, 'tier2/escalate').json()
    for _ in range(2):
        assert view(client, staged)['state']['handlingRoute'] == 'tier2_candidate'
        assert client.get('/api/v2/tier2/cases').json()['page']['total'] == 0
    recovered = direct(client, staged, body_for(client, staged, 'recover_case'))
    assert recovered.status_code == 200, recovered.text
    result = recovered.json()
    assert result['view']['state']['handlingRoute'] == 'tier2_case'
    assert result['case']['snapshot']['routingDecision'] == old['audit']
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == 2


def test_stale_disallowed_unauthorized_and_cross_command_identity(client, database, staged):
    body = body_for(client, staged)
    assert direct(client, staged, body).status_code == 409  # Cannot skip Tier 1 admission.
    post(client, staged, 'admit-tier1')
    assert direct(client, staged, body).status_code == 409  # Stale optimistic version.
    current = body_for(client, staged)
    for action in ('approve_tier2', 'recover_case'):
        assert direct(client, staged, {**current, 'action': action}).status_code == 409
    assert direct(client, staged, current, headers={'Authorization': ''}).status_code == 401
    assert direct(client, staged, current, headers={'Authorization': f"Bearer {client.tokens['evaluator']}"}).status_code == 403
    for change in ({'reason': ' '}, {'action': 'execute'}, {'actorId': 999}, {'title': 'Fabricated'}):
        assert direct(client, staged, {**current, **change}).status_code == 400
    assert client.post(f'/api/v2/alerts/{uuid4()}/tier2/escalate-case', json={**current, 'requestId': str(uuid4())}).status_code == 404
    old = post(client, staged, 'tier2/escalate', body={'requestId': current['requestId']})
    assert old.status_code == 200
    assert direct(client, staged, current).status_code == 409  # Old command is not a compound replay.
    with closing(db.connect(database)) as conn:
        for actor in (99999, conn.execute("SELECT id FROM users WHERE username='evaluator'").fetchone()[0]):
            with pytest.raises(PermissionError):
                escalate_case(conn, staged[0].operational_alert_ref, actor_id=actor,
                              request=EscalateCaseRequest.model_validate(current))


def test_maximum_reason_preserved_without_extra_case_inputs(client, staged):
    post(client, staged, 'admit-tier1')
    body = {**body_for(client, staged), 'reason': 'R'*2000}
    body.pop('action')  # Default command is manual escalation.
    result = direct(client, staged, body)
    assert result.status_code == 200, result.text
    assert result.json()['case']['snapshot']['escalationReason'] == body['reason']
    assert body['reason'] in result.json()['case']['snapshot']['tier1HandoffSummary']


def test_http_failure_returns_no_success_and_preserves_tier1(client, database, staged):
    post(client, staged, 'admit-tier1')
    before = view(client, staged)
    body = body_for(client, staged)
    with closing(db.connect(database)) as conn:
        count = conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0]
        conn.execute("CREATE TRIGGER fail_http BEFORE INSERT ON tier2_case_events BEGIN SELECT RAISE(ABORT,'case storage unavailable'); END")
        conn.commit()
    with TestClient(client.app, raise_server_exceptions=False) as http:
        response = direct(http, staged, body, headers=dict(client.headers))
    assert response.status_code == 500
    assert view(client, staged) == before
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0] == count
