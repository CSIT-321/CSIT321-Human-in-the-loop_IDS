"""Human-only contextual memory, never automatic routing/priority/response."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from pydantic import ValidationError
from packages.contracts import db
from packages.detection import triage_memory as memory
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_projection,read_triage,materialize_source
from packages.detection.external_admission import admit_external
from packages.detection.routing import state_version
from test_api import client,database
from test_external_operational_admission import accept,admit_request

TABLES=('triage_memory_lessons','triage_memory_support_events','triage_memory_decisions','triage_memory_audit')


@pytest.fixture
def alerts(client,database):
    with closing(db.connect(database)) as conn:
        actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        stage_file(conn,Path(__file__).parent/'fixtures/triage-memory-scans.json','memory-test')
        ids=[r[0] for r in conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='memory-test' ORDER BY id")]
        result=[]
        for source in ids:
            review=accept(conn,actor,source)
            receipt,_=admit_external(conn,source,actor_id=actor,request=admit_request(review))
            result.append(read_projection(conn,receipt['operational_alert_id']))
        return actor,result


def request(conn,alert,outcome='expected_activity',scope='exact'):
    return memory.MemoryReviewRequest(request_id=uuid4(),reason='Authorised internal vulnerability scanner',outcome=outcome,
        scope=scope,expected_state_version=state_version(read_triage(conn,alert.id)))


def decision(revision):
    return memory.MemoryDecisionRequest(request_id=uuid4(),expected_revision=revision,reason='Scope and human evidence reviewed')


def teach(conn,alerts,count=3,scope='exact'):
    actor,items=alerts
    for alert in items[:count]:
        result=memory.record_review(conn,alert.operational_alert_ref,actor_id=actor,request=request(conn,alert,scope=scope))
    return result.memory


def snapshot(conn):
    return {name:[tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if name not in (*TABLES,'sqlite_sequence','schema_migrations')}


def test_human_lesson_activation_future_guidance_and_full_isolation(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        before=snapshot(conn)
        assert read_triage(conn,items[0].id).operational_priority==85
        assert memory.list_memory(conn,50,0)==([],0)
        view=teach(conn,alerts,1)
        assert view.status=='candidate' and view.support_count==1 and view.conflict_count==0
        assert view.lesson.context_snapshot.known_scanner_identity is None
        assert view.lesson.context_snapshot.schedule_window is None
        assert view.lesson.context_snapshot.source_ip=='10.0.0.50'
        assert view.lesson.human_reason=='Authorised internal vulnerability scanner'
        with pytest.raises(memory.MemoryConflict,match='threshold'):
            memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(1))
        for alert in items[1:3]:
            view=memory.record_review(conn,alert.operational_alert_ref,actor_id=actor,request=request(conn,alert)).memory
        assert view.status=='eligible_for_activation' and view.support_count==3 and view.agreement_ratio==1
        match=memory.lookup_memory(conn,items[3].operational_alert_ref,50,0)[0][0]
        assert match.strength=='high' and not match.guidance_active
        req=decision(view.revision)
        active=memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=req).memory
        assert active.status=='active' and active.valid_from and active.expires_at
        assert active.expires_at-active.valid_from==timedelta(days=30)
        assert memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=req).replayed
        matches,total=memory.lookup_memory(conn,items[3].operational_alert_ref,50,0)
        assert total==1 and matches[0].guidance_active and matches[0].review_required
        assert 'sourceIp' in matches[0].matched_fields and 'scheduleWindow' in matches[0].unavailable_fields
        assert matches==memory.lookup_memory(conn,items[3].operational_alert_ref,50,0)[0]
        history,_=memory.memory_history(conn,view.lesson.lesson_ref,50,0)
        assert history[0].event_type=='V2_TRIAGE_MEMORY_ACTIVATED'
        assert history[0].lesson_snapshot.support_count==3
        assert history[-1].evidence.detector_snapshot==items[0]
        assert snapshot(conn)==before


def test_conflict_prevents_activation_and_ratio(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts,2)
        changed=memory.record_review(conn,items[2].operational_alert_ref,actor_id=actor,request=request(conn,items[2],'confirmed_malicious')).memory
        assert changed.lesson==view.lesson and changed.conflict_count==1 and changed.support_count==2
        assert changed.agreement_ratio==pytest.approx(2/3) and changed.status=='candidate'
        with pytest.raises(memory.MemoryConflict):
            memory.decide_memory(conn,changed.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(changed.revision))


def test_active_conflict_across_different_scope_is_not_silently_trusted(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts,scope='narrow')
        active=memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(view.revision)).memory
        memory.record_review(conn,items[3].operational_alert_ref,actor_id=actor,request=request(conn,items[3],'confirmed_malicious',scope='exact'))
        updated=memory.read_memory(conn,view.lesson.lesson_ref)
        assert updated.status=='conflict_review' and updated.conflict_count==1 and updated.lesson==active.lesson
        assert updated.decision==active.decision and updated.last_conflict_at
        assert all(not match.guidance_active for match in memory.lookup_memory(conn,items[4].operational_alert_ref,50,0)[0])
        events,_=memory.memory_history(conn,view.lesson.lesson_ref,50,0)
        assert events[0].event_type=='V2_TRIAGE_MEMORY_CONFLICT_REVIEW_REQUIRED'


def test_expiry_for_candidates_and_active_lessons(database,alerts,monkeypatch):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts)
        future=view.expires_at+timedelta(seconds=1)
        assert memory.read_memory(conn,view.lesson.lesson_ref,now=future).status=='expired'
        active=memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(view.revision)).memory
        monkeypatch.setattr(memory.m,'utc_now',lambda:active.expires_at)
        assert memory.read_memory(conn,view.lesson.lesson_ref).status=='expired'
        assert not memory.lookup_memory(conn,items[3].operational_alert_ref,50,0)[0][0].guidance_active
        replacement=memory.record_review(conn,items[3].operational_alert_ref,actor_id=actor,request=request(conn,items[3])).memory
        assert replacement.lesson.lesson_ref!=view.lesson.lesson_ref and replacement.support_count==1


def test_configuration_is_snapshotted_and_threshold_configurable(database,alerts,monkeypatch):
    actor,items=alerts
    config=memory.load_config().model_copy(update={'version':'test-min-four','minimum_support':4,'default_validity_days':7})
    monkeypatch.setattr(memory,'load_config',lambda:config)
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts)
        assert view.status=='candidate' and view.lesson.configuration.minimum_support==4
        view=memory.record_review(conn,items[3].operational_alert_ref,actor_id=actor,request=request(conn,items[3])).memory
        assert view.status=='eligible_for_activation'
        active=memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(view.revision)).memory
        assert active.expires_at-active.valid_from==timedelta(days=7)


@pytest.mark.parametrize('outcome',['expected_activity','false_positive','confirmed_malicious','suspicious'])
def test_explicit_supported_outcomes_only(database,alerts,outcome):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        view=memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=request(conn,items[0],outcome)).memory
        assert view.lesson.outcome==outcome


def test_match_explains_mismatch_unavailable_and_conservative_narrow_scope(database,alerts):
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts,1)
        context=view.lesson.context_snapshot.model_copy(update={'source_ip':'10.0.0.99','destination_port':None})
        result=memory.explain_match(view,context)
        assert result.strength=='partial' and 'sourceIp' in result.mismatched_fields
        assert 'destinationPort' in result.unavailable_fields and not result.guidance_active
        assert set(result.matched_fields+result.mismatched_fields+result.unavailable_fields)==set(context.model_dump(by_alias=True))


def test_retries_duplicate_votes_stale_and_terminal_rejection(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        req=request(conn,items[0])
        view=memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=req).memory
        assert memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=req).replayed
        with pytest.raises(memory.MemoryConflict):
            memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=request(conn,items[0]))
        with pytest.raises(memory.MemoryConflict,match='requestId'):
            memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=req.model_copy(update={'reason':'changed'}))
        with pytest.raises(memory.MemoryConflict,match='state changed'):
            memory.record_review(conn,items[1].operational_alert_ref,actor_id=actor,request=request(conn,items[1]).model_copy(update={'expected_state_version':'0'*64}))
        with pytest.raises(memory.MemoryConflict,match='lesson changed'):
            memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='reject',request=decision(99))
        rejected=memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='reject',request=decision(1)).memory
        assert rejected.status=='rejected'
        with pytest.raises(memory.MemoryConflict,match='already decided'):
            memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(rejected.revision))
        assert memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=req).memory.status=='rejected'


@pytest.mark.parametrize('table',TABLES)
def test_append_only_and_atomic_failure(database,alerts,table):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        view=teach(conn,alerts)
        memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=decision(view.revision))
        for sql in (f'UPDATE {table} SET created_at=created_at',f'DELETE FROM {table}',f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
            with pytest.raises(sqlite3.IntegrityError,match='append-only'):
                conn.execute(sql)
            conn.rollback()
        if table=='triage_memory_decisions':
            return
        counts={name:conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in TABLES}
        conn.execute(f"CREATE TRIGGER fail_memory BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError,match='injected'):
            memory.record_review(conn,items[3].operational_alert_ref,actor_id=actor,request=request(conn,items[3],scope='narrow'))
        assert counts=={name:conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in TABLES}


def test_concurrent_review_idempotency_and_activation(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        req=request(conn,items[0])
    def review(_):
        with closing(db.connect(database)) as conn:
            return memory.record_review(conn,items[0].operational_alert_ref,actor_id=actor,request=req)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(review,range(2)))
    assert sum(r.replayed for r in results)==1
    with closing(db.connect(database)) as conn:
        for item in items[1:3]:
            view=memory.record_review(conn,item.operational_alert_ref,actor_id=actor,request=request(conn,item)).memory
    def decide(index):
        with closing(db.connect(database)) as conn:
            try:
                return memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate' if index else 'reject',request=decision(view.revision))
            except memory.MemoryConflict:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(decide,range(2)))
    assert sum(r is not None for r in results)==1


@pytest.mark.parametrize('role,status',[('evaluator',403),('',401)])
def test_http_authorization_all_mutations(client,database,alerts,role,status):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        req=request(conn,items[0]).model_dump(mode='json',by_alias=True)
        view=teach(conn,alerts,1)
    headers={'Authorization':'Bearer '+client.tokens[role] if role else ''}
    assert client.post(f'/api/v2/alerts/{items[1].operational_alert_ref}/triage-memory/candidate',json=req,headers=headers).status_code==status
    for action in ('activate','reject'):
        assert client.post(f'/api/v2/triage-memory/{view.lesson.lesson_ref}/{action}',json=decision(1).model_dump(mode='json',by_alias=True),headers=headers).status_code==status
    assert client.get('/api/v2/triage-memory',headers=headers).status_code==(200 if role else 401)


def test_http_contract_validation_and_actor_binding(client,database,alerts):
    actor,items=alerts
    root=f'/api/v2/alerts/{items[0].operational_alert_ref}/triage-memory'
    with closing(db.connect(database)) as conn:
        body=request(conn,items[0]).model_dump(mode='json',by_alias=True)
    for extra in ({'reason':' '},{'actorId':999},{'outcome':'system_policy'},{'scope':'category_context'},
                  {'contextSnapshot':{'knownScannerIdentity':'from prose'}},{'nativeSeverity':1}):
        assert client.post(root+'/candidate',json={**body,**extra}).status_code==400
    result=client.post(root+'/candidate',json=body,headers={'Authorization':'Bearer '+client.tokens['admin']})
    assert result.status_code==200,result.text
    view=result.json()['memory']; ref=view['lesson']['lessonRef']
    assert view['lesson']['createdByActorId']!=actor
    assert client.post(root+'/candidate',json=body).status_code==409
    assert client.get('/api/v2/triage-memory/'+ref).json()==view
    assert client.get('/api/v2/triage-memory/'+ref+'/events').json()['page']['total']==1
    assert client.get(root+'/matches').json()['items'][0]['reviewRequired'] is True
    assert client.get('/api/v2/triage-memory?limit=201').status_code==400
    assert client.get('/api/v2/triage-memory/'+str(uuid4())).status_code==404
    assert client.get('/api/v2/triage-memory?offset=1').json()['items']==[]


def test_service_rejects_invalid_principal_and_unreviewed_alert(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        for who in (99999,conn.execute("SELECT id FROM users WHERE username='evaluator'").fetchone()[0]):
            with pytest.raises(PermissionError):
                memory.record_review(conn,items[0].operational_alert_ref,actor_id=who,request=request(conn,items[0]))
        legacy=materialize_source(conn,'legacy_flow_alert',1)
        with pytest.raises(memory.MemoryConflict,match='admitted'):
            memory.record_review(conn,legacy.operational_alert_ref,actor_id=actor,request=request(conn,legacy))


def test_migration_ten_additive_idempotent(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    with closing(db.connect(tmp_path/'migration.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:9]); db.create_schema(conn)
        before=snapshot(conn)
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:10])
        trace=[];conn.set_trace_callback(trace.append)
        assert db.migrate(conn)==[10] and db.migrate(conn)==[]
        assert snapshot(conn)==before
        assert not any(sql.lstrip().upper().startswith(('DROP ','ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
