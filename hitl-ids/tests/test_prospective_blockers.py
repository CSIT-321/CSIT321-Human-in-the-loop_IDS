"""Operational safety, read-only HTTP and complete recorded archives; disposable data only."""
from contextlib import closing
from datetime import timedelta
from hashlib import sha256
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from apps.api import auth, deps
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection import prospective_collection as c
from packages.detection.selective_review import read_review, decide_review, ReviewCommand
from packages.evaluation.prospective_recorded import export_connection, evaluate_recorded, ArchiveIntegrityError
from test_api import client, database
from test_selective_review import alerts
from test_prospective_collection import collection, apply, finish


def ledger(conn):
    return {name:list(map(tuple,conn.execute('SELECT * FROM '+name+' ORDER BY id')))
        for name in ('prospective_runs','prospective_run_events','prospective_decisions','prospective_observations')}


@pytest.mark.parametrize('state',['after_end','closed','stale','missing','in_window'])
def test_override_independent_of_collection_eligibility(collection,state):
    path,items,admin,run,clock=collection
    actor,alerts=items;ref=alerts[3].operational_alert_ref
    with closing(db.connect(path)) as conn:
        apply(conn,items,run)
        if state=='after_end': clock[0]=run.protocol.registration.holdout_end+timedelta(seconds=1)
        if state=='closed': finish(conn,admin,run,clock)
        assert read_review(conn,ref).disposition=='no_immediate_review'
        before=ledger(conn);route=tuple(conn.execute('SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?',(alerts[3].id,)).fetchone())
        count=conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]
        request=ReviewCommand(request_id=uuid4(),expected_version=read_review(conn,ref).version,reason='Safety override must not depend on collection',
            collection_run_ref=uuid4() if state=='missing' else run.run_ref,expected_run_revision=1 if state=='stale' else c.read_run(conn,run.run_ref).revision)
        result=decide_review(conn,ref,actor_id=actor,action='require_review',request=request)
        assert result.view.human_override and result.view.disposition=='must_review'
        receipt=result.view.last_decision.collection_recording
        assert receipt.status==('recorded' if state=='in_window' else 'not_recorded')
        assert conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]==count+1
        assert tuple(conn.execute('SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?',(alerts[3].id,)).fetchone())==route
        if state!='in_window': assert ledger(conn)==before
        else: assert len(c.decisions(conn,run.run_ref))==2
        assert decide_review(conn,ref,actor_id=actor,action='require_review',request=request).replayed
        assert read_review(conn,ref).last_decision.collection_recording==receipt
        if state=='after_end':
            finish(conn,admin,run,clock)
            report=evaluate_recorded(export_connection(conn,run.run_ref),now=clock[0])
            assert report['persistedDecisionCount']==1 and report['recalls']==1


def test_closed_run_report_stable_after_operational_override(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
        before=c.canonical(evaluate_recorded(export_connection(conn,run.run_ref),now=clock[0]))
        ref=items[1][3].operational_alert_ref
        decide_review(conn,ref,actor_id=items[0],action='require_review',request=ReviewCommand(request_id=uuid4(),
            expected_version=read_review(conn,ref).version,reason='Post-closure human control',collection_run_ref=run.run_ref,
            expected_run_revision=c.read_run(conn,run.run_ref).revision))
        assert c.canonical(evaluate_recorded(export_connection(conn,run.run_ref),now=clock[0]))==before


def test_evaluator_cannot_override_closed_run(collection,client):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
        ref=items[1][3].operational_alert_ref
        request=ReviewCommand(request_id=uuid4(),expected_version=read_review(conn,ref).version,reason='Read-only actor',
            collection_run_ref=run.run_ref,expected_run_revision=c.read_run(conn,run.run_ref).revision)
        before=conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]
    response=client.post(f'/api/v2/alerts/{ref}/selective-review/require-human',json=request.model_dump(mode='json',by_alias=True),
        headers={'Authorization':'Bearer '+client.tokens['evaluator']})
    assert response.status_code==403
    with closing(db.connect(path)) as conn: assert conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]==before


@pytest.mark.parametrize('damage',['missing_decision','missing_raw','duplicate_decision','duplicate_raw','wrong_receipt','wrong_raw_snapshot','hidden_count'])
def test_incomplete_archive_rejected(collection,damage):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock);archive=export_connection(conn,run.run_ref)
    assert evaluate_recorded(archive,now=clock[0])['persistedDecisionCount']==1
    raw=archive.model_dump(mode='json',by_alias=True)
    if damage=='missing_decision': raw['decisions']=[]
    if damage=='missing_raw': raw['reviewEvents']=[]
    if damage=='duplicate_decision': raw['decisions']*=2;raw['run']['decisionCount']=2
    if damage=='duplicate_raw': raw['reviewEvents']*=2
    if damage=='hidden_count': raw['decisions']=[];raw['run']['decisionCount']=0
    if damage=='wrong_receipt':
        payload=json.loads(raw['reviewEvents'][0]['request_payload']);payload['collectionRecording']['decisionRef']=str(uuid4())
        raw['reviewEvents'][0]['request_payload']=json.dumps(payload)
    if damage=='wrong_raw_snapshot': raw['reviewEvents'][0]['decision_snapshot']='{}'
    broken=type(archive).model_validate(raw)
    with pytest.raises(ArchiveIntegrityError,match='archive-integrity'): evaluate_recorded(broken,now=clock[0])


def test_unrelated_post_window_events_and_legacy_receipts(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock);archive=export_connection(conn,run.run_ref)
    before=c.canonical(evaluate_recorded(archive,now=clock[0]))
    unrelated={**archive.review_events[0],'id':9999,'created_at':clock[0].isoformat(),
        'request_payload':json.dumps({'request':{'collection_run_ref':str(uuid4())}})}
    changed=archive.model_copy(update={'review_events':[*archive.review_events,unrelated]})
    assert c.canonical(evaluate_recorded(changed,now=clock[0]))==before
    legacy=dict(archive.review_events[0]);payload=json.loads(legacy['request_payload']);payload.pop('collectionRecording')
    legacy['request_payload']=json.dumps(payload)
    assert c.canonical(evaluate_recorded(archive.model_copy(update={'review_events':[legacy]}),now=clock[0]))==before


def test_repeated_evaluations_and_override_reconcile_all_events_not_unique_alerts(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run)
        clock[0]+=timedelta(seconds=1)
        apply(conn,items,run)
        clock[0]+=timedelta(seconds=1)
        apply(conn,items,run,'require_review')
        finish(conn,admin,run,clock);archive=export_connection(conn,run.run_ref)
    report=evaluate_recorded(archive,now=clock[0])
    assert archive.run.decision_count==report['persistedDecisionCount']==3
    assert report['eligibleAlerts']==1 and report['recalls']==1
    with pytest.raises(ArchiveIntegrityError,match='archive-integrity'):
        evaluate_recorded(archive.model_copy(update={'decisions':archive.decisions[:1]}),now=clock[0])


def test_report_http_exposes_archive_integrity_error(collection,client,monkeypatch):
    from apps.api import collection_routes
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock);archive=export_connection(conn,run.run_ref)
    broken=archive.model_copy(update={'decisions':[]})
    monkeypatch.setattr(collection_routes,'export_connection',lambda conn,ref:broken)
    before=sha256(path.read_bytes()).hexdigest();mtime=path.stat().st_mtime_ns
    response=client.get(f'/api/v2/collection/runs/{run.run_ref}/report',headers={'Authorization':'Bearer '+client.tokens['evaluator']})
    assert response.status_code==400 and response.json()['error']['code']=='ARCHIVE_INTEGRITY'
    assert 'archive-integrity' in response.json()['error']['message']
    assert sha256(path.read_bytes()).hexdigest()==before and path.stat().st_mtime_ns==mtime


READ_PATHS=['/api/v2/collection/runs','/api/v2/collection/runs/{ref}','/api/v2/collection/runs/{ref}/export',
    '/api/v2/collection/runs/{ref}/report','/api/v2/context/facts','/api/v2/alerts/{ref}/context',
    '/api/v2/selective-review','/api/v2/selective-review/metrics','/api/v2/alerts/{ref}/selective-review',
    '/api/v2/alerts/{ref}/selective-review/events','/api/auth/me','/api/evaluation/scenarios','/api/evaluation/runs',
    '/api/evaluation/runs/example','/api/evaluation/runs/example/detection']


def old_database(path,monkeypatch):
    with closing(db.connect(path)) as conn:
        with monkeypatch.context() as old:
            old.setattr(db,'MIGRATIONS',db.MIGRATIONS[:12]);db.create_schema(conn)
        auth.ensure_demo_accounts(conn)
        user=db.from_row(m.User,conn.execute("SELECT * FROM users WHERE role='evaluator'").fetchone())
        token=auth.encode_token(user)
    return token


@pytest.mark.parametrize('route',READ_PATHS)
def test_http_reads_never_migrate_schema_twelve(tmp_path,monkeypatch,route):
    path=tmp_path/'schema12.db';token=old_database(path,monkeypatch)
    before=sha256(path.read_bytes()).hexdigest();mtime=path.stat().st_mtime_ns
    def forbidden(*args,**kwargs): raise AssertionError('writable dependency reached by read-only HTTP')
    monkeypatch.setattr(db,'migrate',forbidden);monkeypatch.setattr(db,'connect',forbidden)
    with TestClient(create_app(path)) as client:
        response=client.get(route.format(ref=uuid4()),headers={'Authorization':'Bearer '+token})
    assert response.status_code==503 and response.json()['error']['code']=='DATABASE_SCHEMA_UNSUPPORTED'
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==12
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'prospective_%'").fetchall()
    assert sha256(path.read_bytes()).hexdigest()==before and path.stat().st_mtime_ns==mtime


def test_readonly_connection_enforces_uri_query_only_and_missing_path(database,monkeypatch,tmp_path):
    original=sqlite3.connect;trace=[]
    def connect(source_uri,**kwargs):
        assert source_uri.endswith('?mode=ro') and kwargs.get('uri') is True
        conn=original(source_uri,**kwargs);conn.set_trace_callback(trace.append);return conn
    monkeypatch.setattr(sqlite3,'connect',connect)
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_path=database)))
    reader=deps.get_readonly_connection(request);conn=next(reader)
    assert trace[0]=='PRAGMA query_only=ON'
    with pytest.raises(sqlite3.OperationalError): conn.execute('CREATE TABLE forbidden (id INTEGER)')
    reader.close()
    path=tmp_path/'missing.db'
    with TestClient(create_app(path)) as client:
        assert client.get('/api/v2/collection/runs').status_code==503
    assert not path.exists()


def test_mutable_login_still_uses_migrating_dependency(tmp_path,monkeypatch):
    path=tmp_path/'mutable.db';old_database(path,monkeypatch)
    with TestClient(create_app(path)) as client:
        assert client.post('/api/auth/login',json={'username':'admin','password':'admin-demo'}).status_code==200
    with closing(db.connect(path)) as conn: assert conn.execute('PRAGMA user_version').fetchone()[0]==13


def test_current_schema_export_authentication_is_read_only(collection,client,monkeypatch):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
    before=sha256(path.read_bytes()).hexdigest();mtime=path.stat().st_mtime_ns
    def forbidden(*args,**kwargs): raise AssertionError('writable connection or migration attempted')
    monkeypatch.setattr(db,'connect',forbidden);monkeypatch.setattr(db,'migrate',forbidden)
    for suffix in ('export','report'):
        response=client.get(f'/api/v2/collection/runs/{run.run_ref}/{suffix}',headers={'Authorization':'Bearer '+client.tokens['evaluator']})
        assert response.status_code==200,response.text
    assert sha256(path.read_bytes()).hexdigest()==before and path.stat().st_mtime_ns==mtime
