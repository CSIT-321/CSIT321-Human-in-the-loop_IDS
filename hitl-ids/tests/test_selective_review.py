"""Review reduction is earned by current evidence and never changes the underlying workflow."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from packages.contracts import db,models as m
from packages.detection import selective_review as service
from packages.detection.selective_review_policy import evaluate_review,load_policy
from packages.detection.triage_policy import TriageContext
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.external_admission import admit_external
from packages.detection import triage_memory as memory
from packages.evaluation.selective_review import evaluate_counterfactual
from test_api import client,database
from test_external_operational_admission import accept,admit_request
from test_triage_memory import request as memory_request,decision as memory_decision


def safe_context():
    return TriageContext(asset_criticality='low',repeated_campaign=False,correlated_alert_count=1,response_required=False,
        known_malicious_indicator=False,analyst_escalated=False,unresolved_by_tier1=False,evidence_conflict=False,confirmed_malicious=False)


@pytest.fixture
def alerts(client,database):
    with closing(db.connect(database)) as conn:
        actor=conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        stage_file(conn,Path(__file__).parent/'fixtures/selective-review-demo.json','selective-demo')
        items=[]
        for (source,) in conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='selective-demo' ORDER BY id").fetchall():
            receipt,_=admit_external(conn,source,actor_id=actor,request=admit_request(accept(conn,actor,source)),trusted_context=safe_context())
            items.append(read_projection(conn,receipt['operational_alert_id']))
            seed_synthetic_facts(conn,items[-1],safe_context(),m.utc_now())
        return actor,items


def teach(conn,alerts):
    actor,items=alerts
    for alert in items[:3]:
        view=memory.record_review(conn,alert.operational_alert_ref,actor_id=actor,request=memory_request(conn,alert)).memory
    return memory.decide_memory(conn,view.lesson.lesson_ref,actor_id=actor,action='activate',request=memory_decision(view.revision)).memory


def command(view):
    return service.ReviewCommand(request_id=uuid4(),expected_version=view.version,reason='Evaluate current evidence and trusted safety context')


def snapshot(conn):
    return {name:[tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if name not in ('selective_review_events','sqlite_sequence','schema_migrations')}


@pytest.fixture
def inputs(database,alerts):
    with closing(db.connect(database)) as conn:
        teach(conn,alerts)
        return service.current_snapshot(conn,alerts[1][3].operational_alert_ref).inputs


def policy():
    return load_policy().model_copy(update={'audit_sample_percent':0})


def test_default_no_memory_and_unknown_context(database,alerts):
    with closing(db.connect(database)) as conn:
        view=service.read_review(conn,alerts[1][3].operational_alert_ref)
        assert view.disposition=='must_review' and 'NO_QUALIFIED_ACTIVE_EXACT_MEMORY' in view.reason_codes
    assert evaluate_review(view.policy_evaluation.inputs.model_copy(update={'context':TriageContext()}),policy(),m.utc_now()).disposition=='must_review'


@pytest.mark.parametrize('status',['candidate','eligible_for_activation','rejected','expired','conflict_review'])
def test_inactive_memory_never_reduces(inputs,status):
    match=inputs.matches[0]
    altered=match.model_copy(update={'memory':match.memory.model_copy(update={'status':status})})
    assert evaluate_review(inputs.model_copy(update={'matches':[altered]}),policy(),m.utc_now()).disposition=='must_review'


@pytest.mark.parametrize('change',[{'strength':'partial'},{'guidance_active':False},{'matched_fields':[]},{'mismatched_fields':['destinationIp']}])
def test_match_safety(inputs,change):
    assert evaluate_review(inputs.model_copy(update={'matches':[inputs.matches[0].model_copy(update=change)]}),policy(),m.utc_now()).disposition=='must_review'


@pytest.mark.parametrize('change',[{'support_count':2},{'agreement_ratio':0.66},{'conflict_count':1}])
def test_support_agreement_and_conflict_gates(inputs,change):
    match=inputs.matches[0]
    updated=match.model_copy(update={'memory':match.memory.model_copy(update=change)})
    assert evaluate_review(inputs.model_copy(update={'matches':[updated]}),policy(),m.utc_now()).disposition=='must_review'


@pytest.mark.parametrize('outcome',['confirmed_malicious','suspicious','false_positive'])
def test_outcome_safety_and_stricter_false_positive(inputs,outcome):
    match=inputs.matches[0]
    updated=match.model_copy(update={'memory':match.memory.model_copy(update={'lesson':match.memory.lesson.model_copy(update={'outcome':outcome})})})
    value=inputs.model_copy(update={'matches':[updated]})
    assert evaluate_review(value,policy(),m.utc_now()).disposition=='must_review'
    if outcome=='false_positive':
        updated=updated.model_copy(update={'memory':updated.memory.model_copy(update={'support_count':5})})
        assert evaluate_review(value.model_copy(update={'matches':[updated]}),policy(),m.utc_now()).disposition=='no_immediate_review'


@pytest.mark.parametrize('field,value',[
    ('asset_criticality','critical'),('known_malicious_indicator',True),('evidence_conflict',True),
    ('confirmed_malicious',True),('response_required',True),('repeated_campaign',True),
    ('correlated_alert_count',5),('analyst_escalated',True),('unresolved_by_tier1',True),
    ('known_malicious_indicator',None),
])
def test_current_alert_guardrails(inputs,field,value):
    changed=inputs.model_copy(update={'context':inputs.context.model_copy(update={field:value})})
    assert evaluate_review(changed,policy(),m.utc_now()).disposition=='must_review'


def test_tier2_expiry_context_age_and_sampling(inputs):
    now=m.utc_now()
    assert evaluate_review(inputs,policy(),now).disposition=='no_immediate_review'
    assert evaluate_review(inputs.model_copy(update={'triage':inputs.triage.model_copy(update={'tier2_recommended':True,'tier2_recommendation_reasons':('Needs investigation',)})}),policy(),now).disposition=='must_review'
    assert evaluate_review(inputs,policy(),now+timedelta(hours=25)).disposition=='must_review'
    match=inputs.matches[0]
    expired=match.model_copy(update={'memory':match.memory.model_copy(update={'expires_at':now})})
    assert evaluate_review(inputs.model_copy(update={'matches':[expired]}),policy(),now).disposition=='must_review'
    sampled=policy().model_copy(update={'audit_sample_percent':100})
    assert evaluate_review(inputs,sampled,now).disposition=='recommended_review'
    assert evaluate_review(inputs,load_policy(),now)==evaluate_review(inputs,load_policy(),now)


def test_persisted_deferral_override_idempotency_and_complete_isolation(database,alerts,monkeypatch):
    monkeypatch.setattr(service,'load_policy',policy)
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        teach(conn,alerts);before=snapshot(conn)
        view=service.read_review(conn,items[3].operational_alert_ref)
        assert view.disposition=='must_review'
        req=command(view)
        result=service.decide_review(conn,view.operational_alert_ref,actor_id=actor,action='apply',request=req)
        assert result.view.disposition=='no_immediate_review' and result.view.priority==85 and result.view.route=='tier1_review'
        assert service.decide_review(conn,view.operational_alert_ref,actor_id=actor,action='apply',request=req).replayed
        assert service.review_metrics(conn).no_immediate_review_count==1
        assert service.review_metrics(conn).immediate_review_reduction_rate==pytest.approx(1/6)
        with pytest.raises(service.ReviewConflict):
            service.decide_review(conn,view.operational_alert_ref,actor_id=actor,action='apply',request=command(view))
        overridden=service.decide_review(conn,view.operational_alert_ref,actor_id=actor,action='require_review',request=command(result.view)).view
        assert overridden.disposition=='must_review' and overridden.human_override and overridden.route=='tier1_review'
        again=service.decide_review(conn,view.operational_alert_ref,actor_id=actor,action='apply',request=command(overridden)).view
        assert again.disposition=='must_review' and 'HUMAN_REVIEW_OVERRIDE' in again.reason_codes
        history,total=service.review_history(conn,view.operational_alert_ref,50,0)
        assert total==3 and history[1].event_type=='V2_HUMAN_REVIEW_REQUIRED' and history[1].actor_id==actor
        assert history[1].snapshot.result.decision_source=='human_override'
        assert snapshot(conn)==before


def test_conflict_recall_subsequent_alert_and_unsafe_suppression_metric(database,alerts,monkeypatch):
    monkeypatch.setattr(service,'load_policy',policy)
    actor,items=alerts
    with closing(db.connect(database)) as conn:
        teach(conn,alerts)
        for item in items[3:5]:
            view=service.read_review(conn,item.operational_alert_ref)
            service.decide_review(conn,item.operational_alert_ref,actor_id=actor,action='apply',request=command(view))
        memory.record_review(conn,items[4].operational_alert_ref,actor_id=actor,request=memory_request(conn,items[4],'confirmed_malicious'))
        recalled=service.read_review(conn,items[3].operational_alert_ref)
        assert recalled.recalled and recalled.disposition=='must_review' and 'MEMORY_CONFLICT' in recalled.reason_codes
        next_view=service.read_review(conn,items[5].operational_alert_ref)
        assert service.decide_review(conn,items[5].operational_alert_ref,actor_id=actor,action='apply',request=command(next_view)).view.disposition=='must_review'
        metrics=service.review_metrics(conn)
        assert metrics.conflict_triggered_recall_count==2 and metrics.unsafe_suppression_count==1
        assert metrics.no_immediate_review_count==0


def test_counterfactual_is_read_only_and_labels_never_affect_policy(database,alerts,monkeypatch):
    monkeypatch.setattr(service,'load_policy',policy)
    with closing(db.connect(database)) as conn:
        teach(conn,alerts);before=list(conn.iterdump())
        labels={str(alerts[1][3].operational_alert_ref):'confirmed_malicious',str(alerts[1][4].operational_alert_ref):'expected_activity'}
        result=evaluate_counterfactual(conn,labels)
        assert result['baselineImmediateReview']==6 and result['selectiveImmediateReview']==3
        assert result['maliciousIncorrectlyDeferred']==1 and result['expectedOrFalsePositiveSafelyDeferred']==1
        without=evaluate_counterfactual(conn)
        assert without['noImmediateReview']==result['noImmediateReview'] and without['labelledAlerts']==0
        assert list(conn.iterdump())==before


def test_append_only_rollback_concurrency_and_config_version(database,alerts,monkeypatch):
    monkeypatch.setattr(service,'load_policy',policy)
    actor,items=alerts;ref=items[3].operational_alert_ref
    with closing(db.connect(database)) as conn:
        teach(conn,alerts);req=command(service.read_review(conn,ref))
    def apply(_):
        with closing(db.connect(database)) as conn:
            return service.decide_review(conn,ref,actor_id=actor,action='apply',request=req)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(apply,range(2)))
    assert sum(r.replayed for r in results)==1
    with closing(db.connect(database)) as conn:
        for sql in ('UPDATE selective_review_events SET reason=reason','DELETE FROM selective_review_events','INSERT OR REPLACE INTO selective_review_events SELECT * FROM selective_review_events'):
            with pytest.raises(sqlite3.IntegrityError):conn.execute(sql)
            conn.rollback()
        conn.execute("CREATE TRIGGER fail_review BEFORE INSERT ON selective_review_events BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            service.decide_review(conn,ref,actor_id=actor,action='require_review',request=command(service.read_review(conn,ref)))
        assert not conn.in_transaction and service.read_review(conn,ref).disposition=='no_immediate_review'
        monkeypatch.setattr(service,'load_policy',lambda:policy().model_copy(update={'minimum_support':4}))
        with pytest.raises(service.ReviewConflict,match='policy version'):
            service.decide_review(conn,ref,actor_id=actor,action='apply',request=command(service.read_review(conn,ref)))


@pytest.mark.parametrize('role,status',[('evaluator',403),('',401)])
def test_http_rbac(client,database,alerts,role,status):
    ref=alerts[1][3].operational_alert_ref;root=f'/api/v2/alerts/{ref}/selective-review'
    with closing(db.connect(database)) as conn:body=command(service.read_review(conn,ref)).model_dump(mode='json',by_alias=True)
    headers={'Authorization':'Bearer '+client.tokens[role] if role else ''}
    for action in ('evaluate','require-human'):
        assert client.post(root+'/'+action,json=body,headers=headers).status_code==status
    assert client.get(root,headers=headers).status_code==(200 if role else 401)


def test_http_contract_caller_cannot_invent_safe_context(client,database,alerts):
    ref=alerts[1][3].operational_alert_ref;root=f'/api/v2/alerts/{ref}/selective-review'
    with closing(db.connect(database)) as conn:body=command(service.read_review(conn,ref)).model_dump(mode='json',by_alias=True)
    for extra in ({'context':safe_context().model_dump()},{'actorId':999},{'reason':' '},{'disposition':'no_immediate_review'}):
        assert client.post(root+'/evaluate',json={**body,**extra}).status_code==400
    result=client.post(root+'/evaluate',json=body)
    assert result.status_code==200,result.text
    assert result.json()['view']['disposition']=='must_review'
    assert client.get('/api/v2/selective-review?disposition=no_immediate_review').json()['items']==[]
    assert client.get('/api/v2/selective-review/metrics').json()['totalAlerts']==6
    assert client.get(root+'/events').json()['page']['total']==1
    assert client.get('/api/v2/selective-review?limit=201').status_code==400


def test_migration_eleven_additive_idempotent(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    with closing(db.connect(tmp_path/'migration.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:10]);db.create_schema(conn)
        before=snapshot(conn)
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:11])
        trace=[];conn.set_trace_callback(trace.append)
        assert db.migrate(conn)==[11] and db.migrate(conn)==[] and snapshot(conn)==before
        assert not any(sql.lstrip().upper().startswith(('DROP ','ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
