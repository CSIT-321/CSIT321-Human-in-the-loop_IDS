"""Disposable, forward-moving clocks only. No source database or registered run is used."""
from contextlib import closing
from datetime import timedelta
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

import pytest
from packages.contracts import db,models as m
from packages.detection import prospective_collection as c
from packages.detection.context_store import collect_fact,FactRequest,revision
from packages.detection.selective_review import decide_review,read_review,ReviewCommand
from packages.evaluation.prospective_recorded import load_recorded_database,evaluate_recorded,export_connection
from packages.evaluation.temporal_fixture import synthetic_archive
from packages.evaluation.temporal_review import evaluate_temporal
from test_api import client,database
from test_selective_review import alerts,teach


@pytest.fixture
def collection(database,client,alerts,monkeypatch):
    clock=[m.utc_now()+timedelta(seconds=1)]
    monkeypatch.setattr(m,'utc_now',lambda:clock[0])
    with closing(db.connect(database)) as conn:
        admin=conn.execute("SELECT id FROM users WHERE role='system_admin'").fetchone()[0]
        teach(conn,alerts)
        request=c.RunCreate(request_id=uuid4(),protocol_version='synthetic-closed-v1',evidence_basis='synthetic/demo',
            participant_class='proxy_student_analyst',holdout_start=clock[0]+timedelta(seconds=10),
            holdout_end=clock[0]+timedelta(seconds=100),outcome_cutoff=clock[0]+timedelta(seconds=200),
            readiness_review_reference='SYNTHETIC isolated automated exercise, not real registration',minimum_eligible_alerts=1)
        run=c.create_run(conn,admin,request)
        run=c.change_run(conn,run.run_ref,admin,'open',c.RunCommand(request_id=uuid4(),expected_revision=run.revision))
    clock[0]+=timedelta(seconds=11)
    return database,alerts,admin,run,clock


def apply(conn,items,run,action='apply'):
    actor,alerts=items; ref=alerts[3].operational_alert_ref
    current=read_review(conn,ref)
    request=ReviewCommand(request_id=uuid4(),reason='Synthetic actual UI/API policy application',expected_version=current.version,
        collection_run_ref=run.run_ref,expected_run_revision=c.read_run(conn,run.run_ref).revision)
    result=decide_review(conn,ref,actor_id=actor,action=action,request=request)
    return request,result


def finish(conn,admin,run,clock):
    clock[0]=run.protocol.registration.outcome_cutoff+timedelta(seconds=1)
    return c.change_run(conn,run.run_ref,admin,'close',c.RunCommand(request_id=uuid4(),expected_revision=c.read_run(conn,run.run_ref).revision))


def test_real_times_snapshot_retry_and_export(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        alert=items[1][3]
        collect_fact(conn,actor_id=items[0],request=FactRequest(request_id=uuid4(),expected_revision=revision(conn),subject_type='operational_alert',
            subject_value=str(alert.operational_alert_ref),context_key='knownMaliciousIndicator',value=False,
            observed_at=clock[0],valid_from=clock[0],expires_at=clock[0]+timedelta(hours=1),reason='Independent explicit human assessment',source_reference='real-api-path'))
        clock[0]+=timedelta(seconds=1)
        request,result=apply(conn,items,run)
        assert result.view.disposition=='no_immediate_review'
        assert decide_review(conn,alert.operational_alert_ref,actor_id=items[0],action='apply',request=request).replayed
        decision=c.decisions(conn,run.run_ref)[0]
        assert decision.alert_occurred_at<decision.operational_admitted_at<=decision.review_eligible_at<decision.decision_at==clock[0]
        assert decision.review_eligible_at==max(decision.availability_boundary.values())
        assert decision.snapshot.context_provenance.evaluated_at==clock[0]
        assert decision.snapshot.inputs.matches[0].memory.support_count==3
        assert decision.actor_id==items[0] and decision.policy_hash==run.protocol.selective_policy_hash
        assert c.read_run(conn,run.run_ref).decision_count==1
        finish(conn,admin,run,clock)
    before=sha256(path.read_bytes()).hexdigest()
    archive=load_recorded_database(path,run.run_ref)
    assert archive.decisions==[decision]
    report=evaluate_recorded(archive,now=clock[0])
    assert report['deferredAlerts']==1 and report['eligibleAlerts']==1
    assert report['reviewVolumeReductionRate']==1 and report['unsafeDeferralRate'] is None
    assert report['workload']['measuredAnalystTimeReduction'] is None
    assert before==sha256(path.read_bytes()).hexdigest()


def test_future_unrelated_history_is_byte_identical_and_used_config_checked(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
    archive=load_recorded_database(path,run.run_ref)
    before=c.canonical(evaluate_recorded(archive,now=clock[0]))
    from packages.detection.trusted_context import TrustedContextFact
    future=dict(archive.unrelated_history['contextFacts'][0])
    future.update(factRef=str(uuid4()),id=None,sourceType='synthetic_fixture',createdByActorId=None,sourceSnapshot={'synthetic':True},
        observedAt=clock[0].isoformat(),availableAt=clock[0].isoformat(),recordedAt=clock[0].isoformat(),validFrom=clock[0].isoformat(),expiresAt=(clock[0]+timedelta(hours=1)).isoformat(),
        freshnessPolicy={**future['freshnessPolicy'],'version':'post-window-v2'})
    future=TrustedContextFact.model_validate(future).model_dump(mode='json',by_alias=True)
    changed=archive.model_copy(update={'unrelated_history':{**archive.unrelated_history,'contextFacts':[*archive.unrelated_history['contextFacts'],future],
        'policies':[{'effectiveAt':clock[0].isoformat(),'availableAt':clock[0].isoformat(),'configuration':{**run.protocol.selective_policy.model_dump(mode='json',by_alias=True),'version':'future-v2'}}]}})
    assert c.canonical(evaluate_recorded(changed,now=clock[0]))==before
    d=archive.decisions[0]
    bad=d.model_copy(update={'policy_hash':'0'*64})
    with pytest.raises(ValueError,match='policy'): evaluate_recorded(archive.model_copy(update={'decisions':[bad]}),now=clock[0])
    bad=d.model_copy(update={'snapshot':d.snapshot.model_copy(update={'input_version':'0'*64})})
    with pytest.raises(ValueError,match='fingerprint'): evaluate_recorded(archive.model_copy(update={'decisions':[bad]}),now=clock[0])


def test_later_outcome_measurement_override_and_receipt_do_not_rewrite(collection):
    path,items,admin,run,clock=collection
    from packages.detection.triage_memory import record_review
    with closing(db.connect(path)) as conn:
        apply(conn,items,run)
        original=c.decisions(conn,run.run_ref)[0]
        clock[0]+=timedelta(seconds=2)
        apply(conn,items,run,'require_review')
        observation=c.ObservationRequest(request_id=uuid4(),expected_revision=c.read_run(conn,run.run_ref).revision,
            operational_alert_ref=items[1][3].operational_alert_ref,analyst_review_seconds=12,total_task_seconds=20,errors=1,rework=1,notes='Human stopwatch observation')
        c.observe(conn,run.run_ref,items[0],observation)
        c.observe(conn,run.run_ref,items[0],observation)
        # Use the same real human-review service as the UI, not a fabricated evaluation label.
        from test_triage_memory import request as review_request
        record_review(conn,items[1][3].operational_alert_ref,actor_id=items[0],request=review_request(conn,items[1][3],outcome='confirmed_malicious'))
        assert c.decisions(conn,run.run_ref)[0]==original
        finish(conn,admin,run,clock)
        archive=export_connection(conn,run.run_ref)
        report=evaluate_recorded(archive,now=clock[0])
        assert report['unsafeDeferrals']==1 and report['recalls']==1 and report['outcomeCompleteness']==1
        assert report['workload']['analystReviewSeconds']==12 and report['workload']['totalTaskSeconds']==20
        old=c.canonical(report)
        c.change_run(conn,run.run_ref,admin,'evaluated',c.RunCommand(request_id=uuid4(),expected_revision=c.read_run(conn,run.run_ref).revision))
        assert c.read_run(conn,run.run_ref).status=='evaluated'
        assert c.canonical(evaluate_recorded(export_connection(conn,run.run_ref),now=clock[0]))==old


def test_closure_stale_future_window_and_atomic_rollback(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        with pytest.raises(c.CollectionConflict,match='cutoff'): c.change_run(conn,run.run_ref,admin,'close',c.RunCommand(request_id=uuid4(),expected_revision=run.revision))
        with pytest.raises(ValueError,match='closed'): evaluate_recorded(export_connection(conn,run.run_ref))
        current=read_review(conn,items[1][3].operational_alert_ref)
        stale=ReviewCommand(request_id=uuid4(),reason='stale run guard',expected_version=current.version,collection_run_ref=run.run_ref,expected_run_revision=1)
        before=conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]
        with pytest.raises(c.CollectionConflict): decide_review(conn,items[1][3].operational_alert_ref,actor_id=items[0],action='apply',request=stale)
        assert conn.execute('SELECT count(*) FROM selective_review_events').fetchone()[0]==before
        clock[0]=run.protocol.registration.holdout_end
        with pytest.raises(c.CollectionConflict,match='window'): apply(conn,items,run)
        assert not conn.in_transaction


@pytest.mark.parametrize('field,value',[('decisionAt','2000-01-01T00:00:00Z'),('actorId',999),('policyHash','bad')])
def test_caller_cannot_spoof_decision_metadata(collection,client,field,value):
    _,items,_,run,_=collection
    ref=str(items[1][3].operational_alert_ref)
    current=client.get(f'/api/v2/alerts/{ref}/selective-review').json()
    response=client.post(f'/api/v2/alerts/{ref}/selective-review/evaluate',json={'requestId':str(uuid4()),'reason':'spoof rejection','expectedVersion':current['version'],field:value})
    assert response.status_code==400


@pytest.mark.parametrize('route',['/runs','/runs/{ref}/open','/runs/{ref}/close','/runs/{ref}/evaluated','/runs/{ref}/observations'])
def test_evaluator_cannot_mutate(collection,client,route):
    run=collection[3]
    response=client.post('/api/v2/collection'+route.format(ref=run.run_ref),headers={'Authorization':'Bearer '+client.tokens['evaluator']},json={})
    assert response.status_code in (400,403)
    # With a valid payload, authorization must be 403 rather than merely schema rejection.
    payload=run.protocol.registration.model_dump(mode='json',by_alias=True) if route=='/runs' else {'requestId':str(uuid4()),'expectedRevision':run.revision}
    if route.endswith('observations'): payload.update(operationalAlertRef=str(collection[1][1][3].operational_alert_ref),notes='read only')
    assert client.post('/api/v2/collection'+route.format(ref=run.run_ref),headers={'Authorization':'Bearer '+client.tokens['evaluator']},json=payload).status_code==403


@pytest.mark.parametrize('table',['prospective_runs','prospective_run_events','prospective_decisions','prospective_observations'])
def test_append_only(collection,table):
    path,items,_,run,_=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run)
        c.observe(conn,run.run_ref,items[0],c.ObservationRequest(request_id=uuid4(),expected_revision=c.read_run(conn,run.run_ref).revision,operational_alert_ref=items[1][3].operational_alert_ref,notes='test observation'))
        for sql in (f'UPDATE {table} SET id=id',f'DELETE FROM {table}',f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
            with pytest.raises(sqlite3.IntegrityError): conn.execute(sql)
            conn.rollback()


def test_modes_are_distinct_and_missing_database_not_created(tmp_path):
    archive=synthetic_archive('safe_learning',with_provenance=True)
    assert evaluate_temporal(archive)['evaluationMode']=='retrospective_reconstruction'
    with pytest.raises(ValueError,match='reconstructed-only'): evaluate_recorded(archive)
    missing=tmp_path/'absent.db'
    with pytest.raises(sqlite3.OperationalError): load_recorded_database(missing,uuid4())
    assert not missing.exists()


def test_v2_remains_undated_draft():
    from pathlib import Path
    draft=json.loads(Path('config/prospective-context-protocol-v2-draft.json').read_text())
    assert draft['status']=='draft' and not draft['collectionOpened']
    assert all(draft[k] is None for k in ('registeredAt','holdoutStart','holdoutEnd','outcomeCutoff','codeCommitSha'))


def test_migration_thirteen_preserves_populated_prior_schema(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    with closing(db.connect(tmp_path/'prior.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:12]);db.create_schema(conn)
        from apps.api.auth import ensure_demo_accounts
        ensure_demo_accounts(conn)
        before={r[0]:list(map(tuple,conn.execute(f'SELECT * FROM "{r[0]}"'))) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('schema_migrations','sqlite_sequence')").fetchall()}
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:13])
        trace=[];conn.set_trace_callback(trace.append)
        assert db.migrate(conn)==[13] and db.migrate(conn)==[]
        assert all(list(map(tuple,conn.execute(f'SELECT * FROM "{name}"')))==rows for name,rows in before.items())
        assert not any(s.lstrip().upper().startswith(('ALTER ','DROP ')) for s in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_registration_is_future_only_undated_draft_cannot_open(collection):
    path,_,admin,_,clock=collection
    with closing(db.connect(path)) as conn:
        request=c.RunCreate(request_id=uuid4(),protocol_version='undated-draft',evidence_basis='synthetic/demo',participant_class='proxy_student_analyst')
        draft=c.create_run(conn,admin,request)
        assert draft.status=='draft' and draft.opened_at is None
        assert c.create_run(conn,admin,request).run_ref==draft.run_ref
        with pytest.raises(c.CollectionConflict): c.change_run(conn,draft.run_ref,admin,'open',c.RunCommand(request_id=uuid4(),expected_revision=1))
        past=request.model_copy(update={'request_id':uuid4(),'holdout_start':clock[0]-timedelta(seconds=1),'holdout_end':clock[0]+timedelta(seconds=3),'outcome_cutoff':clock[0]+timedelta(seconds=4)})
        with pytest.raises(ValueError,match='backdating'): c.create_run(conn,admin,past)


def test_duplicate_concurrent_recording_is_atomic(collection):
    from concurrent.futures import ThreadPoolExecutor
    path,items,_,run,_=collection
    ref=items[1][3].operational_alert_ref
    with closing(db.connect(path)) as conn:
        request=ReviewCommand(request_id=uuid4(),reason='Concurrent identical synthetic request',expected_version=read_review(conn,ref).version,
            collection_run_ref=run.run_ref,expected_run_revision=run.revision)
    def submit(_):
        with closing(db.connect(path)) as conn: return decide_review(conn,ref,actor_id=items[0],action='apply',request=request)
    with ThreadPoolExecutor(max_workers=2) as pool: assert sum(r.replayed for r in pool.map(submit,range(2)))==1
    with closing(db.connect(path)) as conn: assert len(c.decisions(conn,run.run_ref))==1


def test_export_enforces_sqlite_read_only(collection,monkeypatch):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
    original=sqlite3.connect
    def connect(source_uri,**kwargs):
        assert source_uri.endswith('?mode=ro') and kwargs['uri']
        conn=original(source_uri,**kwargs)
        with pytest.raises(sqlite3.OperationalError): conn.execute('CREATE TABLE forbidden_write (id INTEGER)')
        return conn
    monkeypatch.setattr('packages.evaluation.prospective_recorded.sqlite3.connect',connect)
    before=sha256(path.read_bytes()).hexdigest()
    evaluate_recorded(load_recorded_database(path,run.run_ref),now=clock[0])
    assert sha256(path.read_bytes()).hexdigest()==before


def test_referenced_fact_policy_and_future_availability_rejected(collection):
    path,items,admin,run,clock=collection
    with closing(db.connect(path)) as conn:
        apply(conn,items,run);finish(conn,admin,run,clock)
    archive=load_recorded_database(path,run.run_ref);decision=archive.decisions[0]
    for mode in ('policy','future'):
        raw=decision.model_dump(mode='json',by_alias=True)
        fact=raw['snapshot']['contextProvenance']['fields'][0]['facts'][0]
        if mode=='policy': fact['freshnessPolicy']['version']='unapproved-v2'
        else: fact['availableAt']=clock[0].isoformat()
        mutated=c.RecordedDecision.model_validate(raw)
        mutated=mutated.model_copy(update={'input_fingerprint':c.digest(mutated.snapshot.model_dump(mode='json',by_alias=True))})
        with pytest.raises(ValueError,match='context policy|future fact'):
            evaluate_recorded(archive.model_copy(update={'decisions':[mutated]}),now=clock[0])


def test_non_synthetic_runs_reject_dirty_code(collection,monkeypatch):
    path,_,admin,run,_=collection
    monkeypatch.setattr(c,'clean_code_tree',lambda:False)
    request=run.protocol.registration.model_copy(update={'request_id':uuid4(),'evidence_basis':'historical-inputs-unverified','holdout_start':None,'holdout_end':None,'outcome_cutoff':None})
    with closing(db.connect(path)) as conn:
        with pytest.raises(c.CollectionConflict,match='clean committed'): c.create_run(conn,admin,request)
