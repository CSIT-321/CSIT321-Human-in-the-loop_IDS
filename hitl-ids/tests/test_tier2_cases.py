"""Explicit candidate-to-case transition and append-only investigation, with no response side effects."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
from uuid import uuid4
import pytest
from packages.contracts import db
from packages.detection.adapters.operational_v2 import read_projection,read_triage,materialize_source
from packages.detection.external_admission import admit_external
from packages.detection.routing import route_alert,RoutingRequest,state_version
from packages.detection.tier2_cases import (
    create_case,mutate_case,read_case,CaseConflict,CreateCaseRequest,CaseCommand,LinkCaseRequest,FindingRequest,
)
from test_api import client,database
from test_external_operational_admission import inbox,accept,admit_request
from test_operational_v2 import snapshot


@pytest.fixture
def candidate(client,database,inbox):
    with closing(db.connect(database)) as conn:
        accepted = accept(conn,inbox)
        admitted,_ = admit_external(conn,1,actor_id=inbox,request=admit_request(accepted))
        alert = read_projection(conn,admitted['operational_alert_id'])
        route_alert(conn,alert.id,actor_id=inbox,action='manual_escalate',request=RoutingRequest(
            request_id=uuid4(),expected_state_version=state_version(read_triage(conn,alert.id)),reason='Tier 1 needs deeper analysis'))
        return alert,inbox


def creation(conn,candidate):
    return CreateCaseRequest(request_id=uuid4(),expected_state_version=state_version(read_triage(conn,candidate[0].id)),
        title='Investigate suspicious connection',tier1_handoff_summary='Source host needs investigation',reason='Open formal case')


def command(revision=1):
    return CaseCommand(request_id=uuid4(),expected_revision=revision,reason='Additional host observed')


def test_case_creation_snapshot_atomic_route_and_isolation(client,database,candidate):
    alert,actor = candidate
    with closing(db.connect(database)) as conn:
        unchanged = snapshot(conn)
        evidence = read_projection(conn,alert.id)
        old = read_triage(conn,alert.id)
        result = create_case(conn,alert.operational_alert_ref,actor_id=actor,request=creation(conn,candidate))
        case = result.case
        assert case.owner_actor_id == case.created_by_actor_id == actor
        assert case.status == 'open' and case.revision == 1
        assert case.snapshot.detector == evidence
        assert case.snapshot.triage == old
        assert case.snapshot.escalation_reason == 'Tier 1 needs deeper analysis'
        assert case.snapshot.tier1_handoff_summary == 'Source host needs investigation'
        assert case.snapshot.triage.priority_band == 'P2' and case.snapshot.triage.operational_priority == 65
        assert case.snapshot.triage.triage_policy_version == 'operational-triage-v1'
        state = read_triage(conn,alert.id)
        assert state.handling_route == 'tier2_case' and state.workflow_stage == 'investigation'
        assert state.review_required and state.decision_source == 'analyst'
        assert read_projection(conn,alert.id) == evidence and snapshot(conn) == unchanged
        event = conn.execute('SELECT * FROM tier2_case_events').fetchone()
        assert event['event_type'] == 'V2_TIER2_CASE_CREATED'
        assert json.loads(event['before_state']) == old.model_dump(mode='json',by_alias=True)
        assert json.loads(event['after_state']) == state.model_dump(mode='json',by_alias=True)


@pytest.mark.parametrize('stage', ['staged','tier1','recommended'])
def test_no_automatic_or_direct_case(client,database,inbox,stage):
    with closing(db.connect(database)) as conn:
        if stage == 'staged':
            alert = materialize_source(conn,'external_nids_alert',1)
        else:
            review = accept(conn,inbox)
            from packages.detection.triage_policy import TriageContext
            result,_ = admit_external(conn,1,actor_id=inbox,request=admit_request(review),
                trusted_context=TriageContext(unresolved_by_tier1=True) if stage == 'recommended' else None)
            alert = read_projection(conn,result['operational_alert_id'])
        with pytest.raises(CaseConflict,match='candidate'):
            create_case(conn,alert.operational_alert_ref,actor_id=inbox,request=creation(conn,(alert,inbox)))
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 0


def test_case_stale_duplicate_retry_and_no_rewind(client,database,candidate):
    alert,actor = candidate
    with closing(db.connect(database)) as conn:
        req = creation(conn,candidate)
        with pytest.raises(CaseConflict,match='changed'):
            create_case(conn,alert.operational_alert_ref,actor_id=actor,request=req.model_copy(update={'expected_state_version':'0'*64}))
        created = create_case(conn,alert.operational_alert_ref,actor_id=actor,request=req)
        mutate_case(conn,created.case.case_ref,actor_id=actor,action='start',request=command())
        replay = create_case(conn,alert.operational_alert_ref,actor_id=actor,request=req)
        assert replay.replayed and replay.event_id == created.event_id and replay.case.status == 'investigating'
        with pytest.raises(CaseConflict):
            create_case(conn,alert.operational_alert_ref,actor_id=actor,request=creation(conn,candidate))
        with pytest.raises(CaseConflict,match='requestId'):
            create_case(conn,alert.operational_alert_ref,actor_id=actor,request=req.model_copy(update={'title':'Changed'}))


@pytest.mark.parametrize('table',['tier2_cases','tier2_case_state','tier2_case_events'])
def test_creation_failure_rolls_back(client,database,candidate,table):
    alert,actor = candidate
    with closing(db.connect(database)) as conn:
        before = read_triage(conn,alert.id)
        conn.execute(f"CREATE TRIGGER fail_case BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError,match='injected'):
            create_case(conn,alert.operational_alert_ref,actor_id=actor,request=creation(conn,candidate))
        assert read_triage(conn,alert.id) == before
        for name in ('tier2_cases','tier2_case_state','tier2_case_events'):
            assert conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0] == 0


def test_explicit_link_notes_findings_and_immutability(client,database,candidate):
    alert,actor = candidate
    with closing(db.connect(database)) as conn:
        created = create_case(conn,alert.operational_alert_ref,actor_id=actor,request=creation(conn,candidate)).case
        linked = materialize_source(conn,'external_nids_alert',2)
        linked_before = read_triage(conn,linked.id)
        result = mutate_case(conn,created.case_ref,actor_id=actor,action='link',request=LinkCaseRequest(
            **command().model_dump(),operational_alert_ref=linked.operational_alert_ref))
        assert read_triage(conn,linked.id) == linked_before
        for duplicate in (linked.operational_alert_ref,alert.operational_alert_ref):
            with pytest.raises(CaseConflict,match='already part'):
                mutate_case(conn,created.case_ref,actor_id=actor,action='link',request=LinkCaseRequest(
                    **command(result.case.revision).model_dump(),operational_alert_ref=duplicate))
        note = command(result.case.revision)
        result = mutate_case(conn,created.case_ref,actor_id=actor,action='note',request=note)
        assert mutate_case(conn,created.case_ref,actor_id=actor,action='note',request=note).replayed
        with pytest.raises(CaseConflict,match='changed'):
            mutate_case(conn,created.case_ref,actor_id=actor,action='note',request=command(1))
        for finding in ('suspicious','inconclusive','confirmed_malicious','expected_activity'):
            result = mutate_case(conn,created.case_ref,actor_id=actor,action='finding',request=FindingRequest(
                **command(result.case.revision).model_dump(),finding=finding))
        assert result.case.snapshot == created.snapshot
        assert read_triage(conn,alert.id).handling_route == 'tier2_case'
        assert conn.execute("SELECT count(*) FROM tier2_case_events WHERE action='finding'").fetchone()[0] == 4
        for sql in ("UPDATE tier2_case_events SET reason='overwritten'",'DELETE FROM tier2_case_events',
                    'INSERT OR REPLACE INTO tier2_case_events SELECT * FROM tier2_case_events',
                    "UPDATE tier2_cases SET title='overwritten'",'DELETE FROM tier2_cases',
                    'INSERT OR REPLACE INTO tier2_cases SELECT * FROM tier2_cases'):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql)
            conn.rollback()


def test_mutation_audit_failure_rolls_back_revision(client,database,candidate):
    with closing(db.connect(database)) as conn:
        case = create_case(conn,candidate[0].operational_alert_ref,actor_id=candidate[1],request=creation(conn,candidate)).case
        conn.execute("CREATE TRIGGER fail_note BEFORE INSERT ON tier2_case_events BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            mutate_case(conn,case.case_ref,actor_id=candidate[1],action='note',request=command())
        assert read_case(conn,case.case_ref) == case


@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_case_creation(client,database,candidate,same_request):
    with closing(db.connect(database)) as conn:
        req = creation(conn,candidate)
    def create(index):
        with closing(db.connect(database)) as conn:
            request = req if same_request or index == 0 else req.model_copy(update={'request_id':uuid4()})
            try:
                return create_case(conn,candidate[0].operational_alert_ref,actor_id=candidate[1],request=request)
            except CaseConflict:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create,range(2)))
    if same_request:
        assert sorted(result.replayed for result in results) == [False,True]
        assert results[0].case.case_ref == results[1].case.case_ref
    else:
        assert results.count(None) == 1
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 1


@pytest.mark.parametrize('role,status',[('evaluator',403),('',401)])
def test_http_auth_all_mutations(client,database,candidate,role,status):
    with closing(db.connect(database)) as conn:
        body = creation(conn,candidate).model_dump(mode='json',by_alias=True)
    path = f'/api/v2/alerts/{candidate[0].operational_alert_ref}/tier2/case'
    headers = {'Authorization':'Bearer '+client.tokens[role] if role else ''}
    assert client.post(path,json=body,headers=headers).status_code == status
    created = client.post(path,json=body).json()['case']
    ref = created['caseRef']
    for suffix,payload in [('notes',{}),('findings',{'finding':'suspicious'}),
        ('alerts',{'operationalAlertRef':str(candidate[0].operational_alert_ref)}),('start-investigation',{})]:
        assert client.post(f'/api/v2/tier2/cases/{ref}/{suffix}',json={
            **command().model_dump(mode='json',by_alias=True),**payload},headers=headers).status_code == status
    if role:
        assert client.get(f'/api/v2/tier2/cases/{ref}',headers=headers).status_code == 200
        assert client.get(f'/api/v2/tier2/cases/{ref}/events',headers=headers).status_code == 200


def test_http_admin_contract_history_and_validation(client,database,candidate):
    with closing(db.connect(database)) as conn:
        body = creation(conn,candidate).model_dump(mode='json',by_alias=True)
    path = f'/api/v2/alerts/{candidate[0].operational_alert_ref}/tier2/case'
    assert client.post(path,json={**body,'ownerActorId':999}).status_code == 400
    assert client.post(path,json={**body,'tier1HandoffSummary':'  '}).status_code == 400
    response = client.post(path,json=body,headers={'Authorization':'Bearer '+client.tokens['admin']})
    assert response.status_code == 200
    case = response.json()['case']
    root = '/api/v2/tier2/cases/'+case['caseRef']
    assert client.get('/api/v2/tier2/cases?limit=201').status_code == 400
    assert client.get('/api/v2/tier2/cases?limit=1').json()['page']['total'] == 1
    assert client.get(root+'/events?limit=1').json()['items'][0]['eventType'] == 'V2_TIER2_CASE_CREATED'
    assert client.get(root+'/events?action=note').json()['items'] == []
    assert client.post(root+'/notes',json={**command().model_dump(mode='json',by_alias=True),'reason':'  '}).status_code == 400
    assert client.post(root+'/findings',json={**command().model_dump(mode='json',by_alias=True),'finding':'blocked_ip'}).status_code == 400
    assert client.get('/api/v2/tier2/cases/'+str(uuid4())).status_code == 404


def test_legacy_candidate_case_does_not_change_legacy_tables(client,database,inbox):
    with closing(db.connect(database)) as conn:
        legacy_id = conn.execute('SELECT id FROM alerts ORDER BY id LIMIT 1').fetchone()[0]
        alert = materialize_source(conn,'legacy_flow_alert',legacy_id)
        for action in ('admit_tier1','manual_escalate'):
            route_alert(conn,alert.id,actor_id=inbox,action=action,request=RoutingRequest(
                request_id=uuid4(),expected_state_version=state_version(read_triage(conn,alert.id)),reason='Explicit analyst action'))
        before = snapshot(conn)
        create_case(conn,alert.operational_alert_ref,actor_id=inbox,request=creation(conn,(alert,inbox)))
        assert before == snapshot(conn)


def test_migration_eight_additive_and_idempotent(tmp_path,monkeypatch):
    migrations = db.MIGRATIONS
    with closing(db.connect(tmp_path/'migration.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:7])
        db.create_schema(conn)
        before = snapshot(conn)
        monkeypatch.setattr(db,'MIGRATIONS',migrations)
        trace=[]
        conn.set_trace_callback(trace.append)
        assert db.migrate(conn) == [8] and db.migrate(conn) == []
        assert before == snapshot(conn)
        assert not any(sql.lstrip().upper().startswith(('DROP ','ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


def test_unverified_candidate_and_service_actor_rejected(client,database,candidate):
    alert,actor = candidate
    with closing(db.connect(database)) as conn:
        req = creation(conn,candidate)
        for actor_id in (99999, conn.execute("SELECT id FROM users WHERE username='evaluator'").fetchone()[0]):
            with pytest.raises(PermissionError):
                create_case(conn,alert.operational_alert_ref,actor_id=actor_id,request=req)
        # A forged/mismatched mutable state is not proof of an authenticated escalation.
        conn.execute('UPDATE operational_triage_state_v2 SET review_reason=? WHERE operational_alert_id=?',
                     ('out-of-band change',alert.id))
        conn.commit()
        with pytest.raises(CaseConflict,match='matching authenticated'):
            create_case(conn,alert.operational_alert_ref,actor_id=actor,request=creation(conn,candidate))


def test_concurrent_notes_use_case_revision(client,database,candidate):
    with closing(db.connect(database)) as conn:
        case = create_case(conn,candidate[0].operational_alert_ref,actor_id=candidate[1],request=creation(conn,candidate)).case
    def append(index):
        with closing(db.connect(database)) as conn:
            try:
                return mutate_case(conn,case.case_ref,actor_id=candidate[1],action='note',request=command()).case.revision
            except CaseConflict:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append,range(2)))
    assert results.count(2) == 1 and results.count(None) == 1
