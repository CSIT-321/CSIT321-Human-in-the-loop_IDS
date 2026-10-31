"""Explicit eligibility, atomic materialization/policy/routing and legacy isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from packages.contracts import db
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_projection, read_triage, materialize_source
from packages.detection.external_admission import (
    EligibilityRequest, AdmissionRequest, AdmissionConflict, review_eligibility, admit_external,
    validate_source,
)
from packages.detection.triage_policy import TriageContext
from test_api import client, database
from test_operational_v2 import snapshot

FIXTURE = Path(__file__).parent / 'fixtures/suricata-alerts.json'


@pytest.fixture
def inbox(client, database):
    with closing(db.connect(database)) as conn:
        stage_file(conn, FIXTURE, 'admission-test')
        return conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]


def review_request(decision='accepted', expected=None):
    return EligibilityRequest(request_id=uuid4(), expected_review_id=expected, decision=decision, reason='Evidence reviewed')


def accept(conn, actor, source=1):
    return review_eligibility(conn, source, actor_id=actor, request=review_request())


def admit_request(review):
    return AdmissionRequest(request_id=uuid4(), expected_review_id=review['id'], reason='Admit after review')


def test_end_to_end_integrity_order_and_restrictions(client, database, inbox):
    with closing(db.connect(database)) as conn:
        before = snapshot(conn)
        source = dict(conn.execute('SELECT * FROM external_alert_inbox WHERE id=1').fetchone())
        review = accept(conn, inbox)
        result, replayed = admit_external(conn, 1, actor_id=inbox, request=admit_request(review))
        assert not replayed
        alert = read_projection(conn, result['operational_alert_id'])
        state = read_triage(conn, alert.id)
        assert alert.external_inbox_id == 1 and alert.detector_confidence is None
        assert alert.detector_evidence.model_dump(mode='json', by_alias=True) == json.loads(source['canonical_snapshot'])
        assert alert.native_severity == source['native_severity']
        assert alert.source_provenance.learning_eligible is False and alert.source_provenance.evaluation_eligible is False
        assert state.handling_route == 'tier1_review' and state.workflow_stage == 'triage'
        assert state.operational_priority == 65 and state.priority_band == 'P2'
        assert not state.tier2_recommended
        policy = conn.execute('SELECT * FROM operational_triage_policy_audit').fetchone()
        routing = conn.execute('SELECT * FROM operational_routing_audit').fetchone()
        assert all(value is None for value in json.loads(policy['context_snapshot']).values())
        dormant = json.loads(policy['before_state'])
        scored = json.loads(policy['after_state'])
        assert dormant['operationalPriority'] is None and dormant['handlingRoute'] == 'unassigned'
        assert scored['operationalPriority'] == 65 and scored['handlingRoute'] == 'unassigned'
        assert json.loads(routing['before_state']) == scored
        assert json.loads(routing['after_state']) == json.loads(result['resulting_state'])
        assert result['actor_id'] == routing['actor_id'] == policy['actor_id'] == inbox
        assert before == snapshot(conn)
        assert source == dict(conn.execute('SELECT * FROM external_alert_inbox WHERE id=1').fetchone())


@pytest.mark.parametrize('severity,priority,band', [(1,85,'P1'),(2,65,'P2'),(3,40,'P3'),(4,20,'P4')])
def test_all_no_context_mappings(client, database, inbox, tmp_path, severity, priority, band):
    events = json.loads(FIXTURE.read_text())
    events[0]['alert']['severity'] = severity
    path = tmp_path / 'severity.json'
    path.write_text(json.dumps(events[:1]))
    with closing(db.connect(database)) as conn:
        stage_file(conn, path, 'severity')
        source = conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='severity'").fetchone()[0]
        review = accept(conn, inbox, source)
        result, _ = admit_external(conn, source, actor_id=inbox, request=admit_request(review))
        state = read_triage(conn, result['operational_alert_id'])
        assert (state.operational_priority, state.priority_band) == (priority, band)
        assert not state.tier2_recommended and read_projection(conn, state.operational_alert_id).detector_confidence is None


def test_held_stale_and_explicit_release(client, database, inbox):
    with closing(db.connect(database)) as conn:
        with pytest.raises(AdmissionConflict, match='accepted'):
            admit_external(conn, 1, actor_id=inbox, request=AdmissionRequest(
                request_id=uuid4(), expected_review_id=None, reason='cannot bypass review'))
        held = review_eligibility(conn, 1, actor_id=inbox, request=review_request('held'))
        with pytest.raises(AdmissionConflict):
            admit_external(conn, 1, actor_id=inbox, request=admit_request(held))
        with pytest.raises(AdmissionConflict, match='changed'):
            accept(conn, inbox)
        released = review_eligibility(conn, 1, actor_id=inbox, request=review_request('accepted', held['id']))
        result, _ = admit_external(conn, 1, actor_id=inbox, request=admit_request(released))
        assert result['review_id'] == released['id']
        assert conn.execute('SELECT count(*) FROM external_eligibility_review').fetchone()[0] == 2
        with pytest.raises(AdmissionConflict):
            review_eligibility(conn, 1, actor_id=inbox, request=review_request('held', released['id']))


@pytest.mark.parametrize('table', ['operational_alerts_v2', 'operational_triage_policy_audit',
                                  'operational_routing_audit', 'external_operational_admission'])
def test_partial_failure_rolls_back_every_step_and_retry_recovers(client, database, inbox, table):
    with closing(db.connect(database)) as conn:
        review = accept(conn, inbox)
        req = admit_request(review)
        conn.execute(f"CREATE TRIGGER fail_admission BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match='injected'):
            admit_external(conn, 1, actor_id=inbox, request=req)
        for name in ('operational_alerts_v2','operational_triage_state_v2','operational_triage_policy_audit',
                     'operational_routing_audit','external_operational_admission'):
            assert conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM external_eligibility_review').fetchone()[0] == 1
        conn.execute('DROP TRIGGER fail_admission')
        conn.commit()
        assert admit_external(conn, 1, actor_id=inbox, request=req)[1] is False


def test_idempotency_concurrency_and_audit_immutability(client, database, inbox):
    with closing(db.connect(database)) as conn:
        req = review_request()
        reviewed = review_eligibility(conn, 1, actor_id=inbox, request=req)
        assert review_eligibility(conn, 1, actor_id=inbox, request=req) == reviewed
    def run(index):
        with closing(db.connect(database)) as conn:
            return admit_external(conn, 1, actor_id=inbox, request=admit_request(reviewed))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(item[1] for item in results) == [False, True]
    assert results[0][0] == results[1][0]
    with closing(db.connect(database)) as conn:
        for table in ('operational_alerts_v2','operational_triage_policy_audit','operational_routing_audit',
                      'external_operational_admission','external_eligibility_review'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 1
        for table in ('external_operational_admission','external_eligibility_review'):
            for statement in (f"UPDATE {table} SET reason='changed'", f'DELETE FROM {table}',
                              f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
                with pytest.raises(sqlite3.IntegrityError, match='append-only'):
                    conn.execute(statement)
                conn.rollback()


@pytest.mark.parametrize('change', [
    {'confidence': .9}, {'learning_eligible': 1}, {'evaluation_eligible': 1}, {'sensor_id': ''},
    {'raw_reference': 'wrong'}, {'native_severity': 1}, {'policy_snapshot': '{}'},
    {'canonical_snapshot': '{}'}, {'admission_decision': 'rejected'}, {'proposed_operational_priority': 99},
])
def test_inconsistent_source_rejected(client, database, inbox, change):
    with closing(db.connect(database)) as conn:
        row = dict(conn.execute('SELECT * FROM external_alert_inbox WHERE id=1').fetchone())
    row.update(change)
    with pytest.raises(AdmissionConflict):
        validate_source(row)


def test_nullable_ports_and_timestamp_exact(client, database, inbox):
    with closing(db.connect(database)) as conn:
        review = accept(conn, inbox, 2)
        result, _ = admit_external(conn, 2, actor_id=inbox, request=admit_request(review))
        alert = read_projection(conn, result['operational_alert_id'])
        assert alert.source_port is None and alert.destination_port is None
        assert alert.occurred_at == '2026-09-18T14:13:42+0800'
        assert alert.occurred_at_timezone_offset == '+08:00'


def test_http_rbac_review_admit_and_existing_routing(client, database, inbox):
    root = '/api/v2/external-alerts/1'
    assert client.get(root).json()['status'] == 'staged'
    review_body = review_request().model_dump(mode='json', by_alias=True)
    for token, expected in [('',401),(client.tokens['evaluator'],403)]:
        assert client.post(root+'/eligibility', json=review_body, headers={'Authorization': 'Bearer '+token}).status_code == expected
    assert client.post(root+'/eligibility', json={**review_body,'detector': {}}).status_code == 400
    review = client.post(root+'/eligibility', json=review_body).json()
    assert review['status'] == 'eligible'
    body = AdmissionRequest(request_id=uuid4(), expected_review_id=review['reviewId'], reason='Admit').model_dump(mode='json',by_alias=True)
    assert client.post(root+'/admit', json={**body, 'trustedContext': {'confirmedMalicious': True}}).status_code == 400
    assert client.post(root+'/admit', json=body, headers={'Authorization': 'Bearer '+client.tokens['evaluator']}).status_code == 403
    result = client.post(root+'/admit', json=body).json()
    assert result['view']['status'] == 'admitted' and not result['replayed']
    assert client.post(root+'/admit', json=body).json()['replayed']
    ref = result['view']['operationalAlertRef']
    state = client.get(f'/api/v2/alerts/{ref}/triage-state').json()
    assert state['state']['handlingRoute'] == 'tier1_review'
    response = client.post(f'/api/v2/alerts/{ref}/tier2/escalate', json={
        'requestId': str(uuid4()), 'expectedStateVersion': state['stateVersion'], 'reason': 'Human escalation'})
    assert response.status_code == 200 and response.json()['view']['state']['handlingRoute'] == 'tier2_candidate'
    assert client.post(root+'/admit',json=body).json()['replayed']
    assert client.get(f'/api/v2/alerts/{ref}/triage-state').json()['state']['handlingRoute'] == 'tier2_candidate'


def test_trusted_context_recommends_only_and_existing_approval(client, database, inbox):
    with closing(db.connect(database)) as conn:
        review = accept(conn, inbox)
        result, _ = admit_external(conn, 1, actor_id=inbox, request=admit_request(review),
                                   trusted_context=TriageContext(unresolved_by_tier1=True))
        alert = read_projection(conn, result['operational_alert_id'])
    state = client.get(f'/api/v2/alerts/{alert.operational_alert_ref}/triage-state').json()
    assert state['state']['tier2Recommended'] and state['state']['handlingRoute'] == 'tier1_review'
    for action in ('reject','approve'):
        response = client.post(f'/api/v2/alerts/{alert.operational_alert_ref}/tier2/{action}',json={
            'requestId': str(uuid4()), 'expectedStateVersion': state['stateVersion'], 'reason': 'Analyst judgement'})
        assert response.status_code == 200
        state = response.json()['view']
    assert state['state']['handlingRoute'] == 'tier2_candidate'


def test_preexisting_projection_is_not_silently_adopted(client, database, inbox):
    with closing(db.connect(database)) as conn:
        materialize_source(conn, 'external_nids_alert', 1)
        with pytest.raises(AdmissionConflict, match='materialized'):
            accept(conn, inbox)
    assert client.get('/api/v2/external-alerts/1').json()['status'] == 'held'


def test_review_retry_collision_and_service_authorization(client, database, inbox):
    with closing(db.connect(database)) as conn:
        req = review_request()
        for actor in (99999, conn.execute("SELECT id FROM users WHERE username='evaluator'").fetchone()[0]):
            with pytest.raises(PermissionError):
                review_eligibility(conn, 1, actor_id=actor, request=req)
        review = review_eligibility(conn, 1, actor_id=inbox, request=req)
        with pytest.raises(AdmissionConflict, match='requestId'):
            review_eligibility(conn, 2, actor_id=inbox, request=req)
        with pytest.raises(PermissionError):
            admit_external(conn, 1, actor_id=99999, request=admit_request(review))
        request = admit_request(review)
        admit_external(conn, 1, actor_id=inbox, request=request)
        with pytest.raises(AdmissionConflict, match='requestId'):
            admit_external(conn, 1, actor_id=inbox, request=request.model_copy(update={'reason': 'changed'}))


def test_migration_seven_preserves_existing_rows(tmp_path, monkeypatch):
    migrations = db.MIGRATIONS
    with closing(db.connect(tmp_path / 'before.db')) as conn:
        monkeypatch.setattr(db, 'MIGRATIONS', migrations[:6])
        db.create_schema(conn)
        stage_file(conn, FIXTURE, 'migration-test')
        before = snapshot(conn)
        monkeypatch.setattr(db, 'MIGRATIONS', migrations[:7])
        trace = []
        conn.set_trace_callback(trace.append)
        assert db.migrate(conn) == [7] and db.migrate(conn) == []
        assert before == snapshot(conn)
        assert not any(sql.lstrip().upper().startswith(('DROP ', 'ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
