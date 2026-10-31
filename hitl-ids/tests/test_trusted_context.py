"""Safety facts require explicit scope, source, availability and validity; unknown never means false."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
import sqlite3
from uuid import uuid4

import pytest

from packages.contracts import db, models as m
from packages.detection.context_store import FactRequest, FactConflict, collect_fact, read_facts, revision
from packages.detection.trusted_context import TrustedContextFact, resolve_context, effective_expiry, load_context_policy
from packages.evaluation.temporal_fixture import synthetic_archive
from packages.evaluation.temporal_review import evaluate_temporal, timestamp
from test_api import client, database
from test_selective_review import alerts, teach, snapshot


def case():
    archive=synthetic_archive('safe_learning',with_provenance=True)
    alert=archive.alerts[3]
    at=timestamp(alert.occurred_at)
    facts=[f for f in archive.context_facts if f.subject_value==str(alert.operational_alert_ref)]
    return archive,alert,at,facts


def change(fact,**values):
    return TrustedContextFact.model_validate({**fact.model_dump(),**values})


def field(result,key='knownMaliciousIndicator'):
    return next(f for f in result.fields if f.context_key==key)


def test_unknown_false_are_distinct_and_no_free_text_extraction():
    _,alert,at,facts=case()
    known=resolve_context(alert,facts,at)
    assert field(known).value is False and field(known).status=='trusted' and known.complete
    unknown=resolve_context(alert,[],at)
    assert field(unknown).value is None and not unknown.complete
    f=next(f for f in facts if f.context_key=='knownMaliciousIndicator')
    unknown=resolve_context(alert,[change(f,value=None,reason='This looks harmless; no known indicator')],at)
    assert field(unknown).value is None and field(unknown).status=='unknown'


@pytest.mark.parametrize('value',['false','true',0,1,0.0,[],{}])
def test_boolean_values_are_not_coerced(value):
    *_,facts=case()
    f=next(f for f in facts if f.context_key=='knownMaliciousIndicator')
    with pytest.raises(ValueError): change(f,value=value)


@pytest.mark.parametrize('updates',[
    {'source_reference':' '},{'reason':' '},{'source_snapshot':{}},{'subject_value':' '},
    {'source_type':'analyst_assessment','created_by_actor_id':None},
    {'source_type':'analyst_assessment','created_by_actor_id':1,'expires_at':None},
])
def test_provenance_scope_and_assessment_fields_required(updates):
    *_,facts=case()
    with pytest.raises(ValueError): change(facts[0],**updates)


@pytest.mark.parametrize('axis',['available','valid','expired','freshness'])
def test_temporal_validity_and_freshness(axis):
    _,alert,at,facts=case()
    if axis=='available': changed=[change(f,available_at=at+timedelta(seconds=1),recorded_at=at+timedelta(seconds=1)) for f in facts]
    elif axis=='valid': changed=[change(f,valid_from=at+timedelta(seconds=1)) for f in facts]
    elif axis=='expired': changed=[change(f,valid_from=at-timedelta(hours=1),expires_at=at) for f in facts]
    else: changed=[change(f,observed_at=at-timedelta(days=8)) for f in facts]
    resolved=resolve_context(alert,changed,at)
    assert not resolved.complete and all(f.value is None for f in resolved.fields)
    if axis in ('expired','freshness'): assert all(f.status=='expired' for f in resolved.fields)


def test_history_replacement_conflict_withdrawal_and_no_old_value_revival():
    _,alert,at,facts=case()
    old=facts[0]
    later=at+timedelta(minutes=1)
    new=change(old,fact_ref=uuid4(),value='critical',observed_at=later,available_at=later,recorded_at=later,valid_from=later)
    assert field(resolve_context(alert,[old,new],at),'assetCriticality').value=='low'
    assert field(resolve_context(alert,[old,new],later),'assetCriticality').value=='critical'
    assert old.value=='low'
    competing=change(new,fact_ref=uuid4(),source_reference='another-independent-source',value='low')
    assert field(resolve_context(alert,[old,new,competing],later),'assetCriticality').status=='conflict'
    withdrawn=change(new,status='withdrawn')
    assert field(resolve_context(alert,[old,withdrawn],later),'assetCriticality').status=='unknown'
    expired=change(new,expires_at=later+timedelta(seconds=1))
    assert field(resolve_context(alert,[old,expired],later+timedelta(seconds=1)),'assetCriticality').status=='expired'


def test_only_explicit_subjects_resolve_and_no_host_identity_inference():
    _,alert,at,facts=case()
    asset=change(facts[0],subject_type='asset',subject_value='server-01')
    assert field(resolve_context(alert,[asset],at),'assetCriticality').status=='not_applicable'
    ip=change(facts[0],subject_type='ip',subject_value=alert.destination_ip)
    assert field(resolve_context(alert,[ip],at),'assetCriticality').status=='trusted'
    unsafe_scope=change(facts[1],subject_type='ip',subject_value=alert.source_ip)
    assert field(resolve_context(alert,[unsafe_scope],at)).value is None


@pytest.mark.parametrize('mode',['safe','risky','unknown','expired','conflict','future'])
def test_temporal_provenance_and_existing_review_policy(mode):
    archive,alert,at,facts=case()
    all_facts=archive.context_facts
    target=next(f for f in facts if f.context_key=='knownMaliciousIndicator')
    if mode=='risky': replacement=change(target,value=True)
    elif mode=='unknown': replacement=change(target,value=None)
    elif mode=='expired': replacement=change(target,valid_from=at-timedelta(seconds=1),expires_at=at)
    elif mode=='future': replacement=change(target,available_at=at+timedelta(seconds=1),recorded_at=at+timedelta(seconds=1))
    else: replacement=target
    all_facts=[replacement if f.fact_ref==target.fact_ref else f for f in all_facts]
    if mode=='conflict': all_facts.append(change(target,fact_ref=uuid4(),source_reference='conflicting-source',value=True))
    updated=archive.model_copy(update={'context_facts':all_facts})
    report=evaluate_temporal(updated)
    first=report['decisions'][0]
    assert (first['disposition']=='no_immediate_review')==(mode=='safe')
    assert first['contextProvenance']['fields'][0]['facts'][0]['sourceType']=='synthetic_fixture'
    assert report['contextCoverage']['eligibleAlerts']==3
    assert report['contextCoverage']['completeTrustedSafetyContext']==(3 if mode in ('safe','risky') else 2)
    if mode=='expired': assert report['contextCoverage']['blockedByExpiredContext']==1
    if mode=='conflict': assert report['contextCoverage']['blockedByConflictingContext']==1
    if mode in ('unknown','future'): assert report['contextCoverage']['blockedByUnknownContext']==1


def test_determinism_and_configuration_specific_lifetimes():
    _,alert,at,facts=case()
    assert resolve_context(alert,facts,at)==resolve_context(alert,list(reversed(facts)),at)
    policy=load_context_policy()
    assert policy.maximum_age_hours['assetCriticality']>policy.maximum_age_hours['knownMaliciousIndicator']
    no_expiry=change(facts[0],expires_at=None)
    assert effective_expiry(no_expiry)==at+timedelta(hours=168)


def request(conn,alert,**updates):
    now=m.utc_now()
    return FactRequest(request_id=uuid4(),expected_revision=revision(conn),subject_type='operational_alert',
        subject_value=str(alert.operational_alert_ref),context_key='knownMaliciousIndicator',value=False,
        observed_at=now-timedelta(seconds=1),valid_from=now-timedelta(seconds=1),expires_at=now+timedelta(hours=1),
        reason='Explicit human structured assessment for this alert',source_reference='analyst-investigation').model_copy(update=updates)


def test_collection_server_timestamps_idempotency_stale_and_append_only(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        req=request(conn,items[3]); before=snapshot(conn)
        result=collect_fact(conn,actor_id=actor,request=req)
        assert result.fact.available_at==result.fact.recorded_at and result.fact.available_at>=req.observed_at
        assert result.fact.source_type=='analyst_assessment' and result.fact.created_by_actor_id==actor
        assert collect_fact(conn,actor_id=actor,request=req).replayed
        with pytest.raises(FactConflict): collect_fact(conn,actor_id=actor,request=req.model_copy(update={'request_id':uuid4()}))
        with pytest.raises(FactConflict): collect_fact(conn,actor_id=actor,request=req.model_copy(update={'reason':'changed retry'}))
        after=snapshot(conn)
        assert {k:v for k,v in before.items() if k!='trusted_context_facts'}=={k:v for k,v in after.items() if k!='trusted_context_facts'}
        for table in ('trusted_context_facts','triage_context_provenance'):
            for sql in (f'DELETE FROM {table}',f'UPDATE {table} SET snapshot=snapshot',f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
                with pytest.raises(sqlite3.IntegrityError): conn.execute(sql)
                conn.rollback()


def test_concurrent_requests_and_transaction_rollback(database,alerts):
    actor,items=alerts
    with closing(db.connect(database)) as conn: req=request(conn,items[0])
    def collect(_):
        with closing(db.connect(database)) as conn: return collect_fact(conn,actor_id=actor,request=req)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(r.replayed for r in pool.map(collect,range(2)))==1
    with closing(db.connect(database)) as conn:
        count=revision(conn)
        conn.execute("CREATE TRIGGER test_fail_context BEFORE INSERT ON trusted_context_facts BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError): collect_fact(conn,actor_id=actor,request=request(conn,items[0]))
        assert revision(conn)==count and not conn.in_transaction


@pytest.mark.parametrize('role,expected',[('evaluator',403),('',401)])
def test_authentication_and_evaluator_read_only(client,database,alerts,role,expected):
    with closing(db.connect(database)) as conn: body=request(conn,alerts[1][0]).model_dump(mode='json',by_alias=True)
    headers={'Authorization':'Bearer '+client.tokens[role] if role else ''}
    assert client.post('/api/v2/context/facts',json=body,headers=headers).status_code==expected
    assert client.get('/api/v2/context/facts',headers=headers).status_code==(200 if role else 401)


def test_api_cannot_spoof_provenance_or_extract_text(client,database,alerts):
    with closing(db.connect(database)) as conn: body=request(conn,alerts[1][0]).model_dump(mode='json',by_alias=True)
    for extra in ({'sourceType':'asset_inventory'},{'availableAt':'2000-01-01T00:00:00Z'},
                  {'createdByActorId':999},{'reason':' '},{'value':'looks safe'}):
        assert client.post('/api/v2/context/facts',json={**body,**extra}).status_code==400
    response=client.post('/api/v2/context/facts',json=body)
    assert response.status_code==200,response.text
    assert response.json()['fact']['sourceType']=='analyst_assessment'
    ref=alerts[1][0].operational_alert_ref
    detail=client.get(f'/api/v2/alerts/{ref}/context')
    assert detail.status_code==200 and detail.json()['complete']


def test_new_fact_invalidates_deferral_without_rewriting_history(database,alerts):
    from packages.detection.selective_review import read_review,decide_review
    from test_selective_review import command
    actor,items=alerts; ref=items[3].operational_alert_ref
    with closing(db.connect(database)) as conn:
        teach(conn,alerts)
        initial=read_review(conn,ref)
        deferred=decide_review(conn,ref,actor_id=actor,action='apply',request=command(initial)).view
        assert deferred.disposition=='no_immediate_review'
        original=conn.execute('SELECT decision_snapshot FROM selective_review_events').fetchone()[0]
        collect_fact(conn,actor_id=actor,request=request(conn,items[3],value=True))
        current=read_review(conn,ref)
        assert current.disposition=='must_review' and current.recalled
        assert field(current.policy_evaluation.context_provenance).status=='conflict'
        assert conn.execute('SELECT decision_snapshot FROM selective_review_events').fetchone()[0]==original


def test_migration_twelve_is_additive_idempotent_and_preserves_rows(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    with closing(db.connect(tmp_path/'history.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:11]); db.create_schema(conn)
        before={name:list(conn.execute(f'SELECT * FROM "{name}"')) for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence','schema_migrations')").fetchall()}
        monkeypatch.setattr(db,'MIGRATIONS',migrations)
        trace=[]; conn.set_trace_callback(trace.append)
        assert db.migrate(conn)==[12] and db.migrate(conn)==[]
        assert all(list(conn.execute(f'SELECT * FROM "{name}"'))==rows for name,rows in before.items())
        assert not any(sql.lstrip().upper().startswith(('DROP ','ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_late_risky_fact_cannot_rewrite_historical_decision():
    archive,alert,at,facts=case()
    late=at+timedelta(minutes=1)
    risk=change(facts[0],fact_ref=uuid4(),value='critical',observed_at=late,available_at=late,recorded_at=late,valid_from=at)
    before=evaluate_temporal(archive)['decisions'][0]
    after=evaluate_temporal(archive.model_copy(update={'context_facts':[*archive.context_facts,risk]}))['decisions'][0]
    assert before['inputs']==after['inputs'] and before['contextProvenance']==after['contextProvenance']
    assert before['disposition']==after['disposition']=='no_immediate_review'


def test_protocol_refuses_open_holdout_and_reports_incomplete_targets():
    from packages.evaluation.context_protocol import ProspectiveProtocol,evaluate_prospective
    archive=synthetic_archive('safe_learning',with_provenance=True)
    protocol=ProspectiveProtocol(version='test-protocol',registered_at=archive.holdout_start-timedelta(days=1),
        holdout_start=archive.holdout_start,holdout_end=archive.holdout_end,minimum_eligible_alerts=100,
        minimum_outcome_completeness=.95,selective_policy_version='selective-review-v1',context_policy_version='context-provenance-v1',
        selective_policy=archive.policies[0].configuration,context_policy=load_context_policy())
    with pytest.raises(ValueError,match='not closed'): evaluate_prospective(archive,protocol,now=archive.holdout_start)
    report=evaluate_prospective(archive,protocol,now=archive.holdout_end)
    assert report['outcomeCompleteness']['labelledAlerts']==3 and not report['outcomeCompleteness']['targetMet']
    with pytest.raises(ValueError,match='window'): evaluate_prospective(archive.model_copy(update={'holdout_end':archive.holdout_end+timedelta(seconds=1)}),protocol,now=archive.holdout_end)
    with pytest.raises(ValueError,match='fact history'): evaluate_prospective(archive.model_copy(update={'context_facts':None}),protocol,now=archive.holdout_end)
    period=archive.policies[0].model_copy(update={'configuration':archive.policies[0].configuration.model_copy(update={'minimum_support':4})})
    with pytest.raises(ValueError,match='policy version'): evaluate_prospective(archive.model_copy(update={'policies':[period]}),protocol,now=archive.holdout_end)
