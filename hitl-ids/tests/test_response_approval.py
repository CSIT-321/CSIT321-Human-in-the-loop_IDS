"""Response plans stop at human authorization; existing operational state is untouched."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
from uuid import uuid4
import pytest
from packages.contracts import db
from packages.detection.response_policy import ResponseFinding,recommend_response
from packages.detection.response_approval import (
    ResponseRequest,ManualResponseRequest,ResponseDecisionRequest,ResponseConflict,
    propose_response,decide_response,list_responses,
)
from packages.detection.tier2_cases import create_case,mutate_case,FindingRequest,LinkCaseRequest
from packages.detection.adapters.operational_v2 import materialize_source
from test_api import client,database
from test_external_operational_admission import inbox
from test_tier2_cases import candidate,creation,command


@pytest.fixture
def case(database,candidate):
    with closing(db.connect(database)) as conn:
        return create_case(conn,candidate[0].operational_alert_ref,actor_id=candidate[1],request=creation(conn,candidate)).case


def request(revision=1):
    return ResponseRequest(request_id=uuid4(),expected_case_revision=revision,reason='Investigated and reviewed evidence')


def decision(revision=1):
    return ResponseDecisionRequest(**request(revision).model_dump(),expected_revision=1)


def snapshot(conn):
    excluded={'response_recommendations','response_decisions','sqlite_sequence','schema_migrations'}
    return {name:[tuple(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if name not in excluded}


@pytest.mark.parametrize('finding,expected',[(None,'further_investigation'),('inconclusive','further_investigation'),
    ('suspicious','monitor'),('expected_activity','monitor'),('confirmed_malicious','block_source_ip')])
def test_policy_only_investigation_finding(finding,expected):
    value=ResponseFinding(event_id=1,finding=finding,actor_id=1,reason='Corroborated',created_at='2026-10-31T00:00:00Z') if finding else None
    result=recommend_response(value,uuid4(),'203.0.113.20')
    assert result.recommendation_type==expected and result.rationale
    if finding=='confirmed_malicious':
        for ip in (None,'not-an-ip',''):
            assert recommend_response(value,uuid4(),ip).recommendation_type=='further_investigation'


def test_formal_case_required_no_direct_tier1_or_candidate(database,candidate):
    with closing(db.connect(database)) as conn:
        for ref in (candidate[0].operational_alert_ref,uuid4()):
            with pytest.raises(LookupError,match='Formal Tier 2'):
                propose_response(conn,ref,actor_id=candidate[1],request=request())
        assert conn.execute('SELECT count(*) FROM response_recommendations').fetchone()[0]==0


@pytest.mark.parametrize('outcome',['approved','rejected'])
def test_terminal_decision_retry_audit_and_complete_isolation(database,candidate,case,outcome):
    with closing(db.connect(database)) as conn:
        actor=candidate[1]
        case=mutate_case(conn,case.case_ref,actor_id=actor,action='finding',request=FindingRequest(
            **command().model_dump(),finding='confirmed_malicious')).case
        before=snapshot(conn)
        req=request(case.revision)
        pending=propose_response(conn,case.case_ref,actor_id=actor,request=req)
        view=pending.response
        assert view.status=='pending' and view.decision is None and view.execution_status=='not_executed'
        assert view.proposal.recommendation_type=='block_source_ip'
        assert view.proposal.target_value==candidate[0].source_ip
        assert view.proposal.evidence_snapshot.target_alert==case.snapshot.detector
        assert view.proposal.evidence_snapshot.finding.finding=='confirmed_malicious'
        assert propose_response(conn,case.case_ref,actor_id=actor,request=req).replayed
        dec=decision(case.revision)
        result=decide_response(conn,case.case_ref,view.proposal.recommendation_ref,actor_id=actor,decision=outcome,request=dec)
        assert result.response.status==outcome and result.response.execution_status=='not_executed'
        assert result.response.decision.proposal_snapshot==view.proposal
        assert result.response.decision.actor_id==actor
        assert result.response.decision.event_type=='V2_RESPONSE_'+outcome.upper()
        assert decide_response(conn,case.case_ref,view.proposal.recommendation_ref,actor_id=actor,decision=outcome,request=dec).replayed
        assert propose_response(conn,case.case_ref,actor_id=actor,request=req).response.status==outcome
        for changed in (decision(case.revision),dec.model_copy(update={'reason':'different'})):
            with pytest.raises(ResponseConflict):
                decide_response(conn,case.case_ref,view.proposal.recommendation_ref,actor_id=actor,decision='approved',request=changed)
        with pytest.raises(ResponseConflict,match='requestId'):
            propose_response(conn,case.case_ref,actor_id=actor,request=req.model_copy(update={'reason':'changed'}))
        assert snapshot(conn)==before
        assert list_responses(conn,case.case_ref,50,0)[1:]==(1,case.revision)
        for table in ('response_recommendations','response_decisions'):
            for sql in (f'UPDATE {table} SET created_at=created_at',f'DELETE FROM {table}',f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
                with pytest.raises(sqlite3.IntegrityError,match='append-only'):
                    conn.execute(sql)
                conn.rollback()


@pytest.mark.parametrize('kind,target_type,value',[
    ('block_source_ip','ip','192.0.2.254'),('block_source_ip','ip','invalid'),('block_source_ip','case','case'),
    ('isolate_host','host','host-23'),('disable_account','account','user@example'),
    ('monitor','operational_alert','missing'),('notify_security_team','account','soc@example'),
])
def test_unsupported_targets_blocked(database,candidate,case,kind,target_type,value):
    with closing(db.connect(database)) as conn:
        with pytest.raises(ResponseConflict):
            propose_response(conn,case.case_ref,actor_id=candidate[1],manual=True,request=ManualResponseRequest(
                **request().model_dump(),recommendation_type=kind,target_type=target_type,target_value=value))
        assert conn.execute('SELECT count(*) FROM response_recommendations').fetchone()[0]==0


def test_manual_override_primary_linked_and_case_targets(database,candidate,case):
    with closing(db.connect(database)) as conn:
        linked=materialize_source(conn,'external_nids_alert',2)
        case=mutate_case(conn,case.case_ref,actor_id=candidate[1],action='link',request=LinkCaseRequest(
            **command().model_dump(),operational_alert_ref=linked.operational_alert_ref)).case
        for kind,typ,target in [('block_source_ip','ip',candidate[0].source_ip),('block_source_ip','ip',linked.source_ip),
            ('monitor','case',str(case.case_ref)),('monitor','operational_alert',str(linked.operational_alert_ref)),
            ('monitor','operational_alert',str(candidate[0].operational_alert_ref)),
            ('further_investigation','case',str(case.case_ref)),('notify_security_team','case',str(case.case_ref))]:
            result=propose_response(conn,case.case_ref,actor_id=candidate[1],manual=True,request=ManualResponseRequest(
                **request(case.revision).model_dump(),recommendation_type=kind,target_type=typ,target_value=target)).response
            assert result.proposal.proposal_source=='analyst' and result.proposal.policy_version is None
            assert result.proposal.event_type=='V2_RESPONSE_MANUAL_RECOMMENDATION' and result.status=='pending'
        assert list_responses(conn,case.case_ref,1,0)[1]==7


def test_stale_case_evidence_cannot_be_approved_but_can_be_rejected(database,candidate,case):
    with closing(db.connect(database)) as conn:
        proposal=propose_response(conn,case.case_ref,actor_id=candidate[1],request=request()).response.proposal
        mutate_case(conn,case.case_ref,actor_id=candidate[1],action='note',request=command())
        with pytest.raises(ResponseConflict,match='changed'):
            propose_response(conn,case.case_ref,actor_id=candidate[1],request=request())
        for rev in (1,2):
            with pytest.raises(ResponseConflict,match='changed'):
                decide_response(conn,case.case_ref,proposal.recommendation_ref,actor_id=candidate[1],decision='approved',request=decision(rev))
        result=decide_response(conn,case.case_ref,proposal.recommendation_ref,actor_id=candidate[1],decision='rejected',request=decision(2))
        assert result.response.status=='rejected'


@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_decisions_single_winner(database,candidate,case,same_request):
    with closing(db.connect(database)) as conn:
        proposal=propose_response(conn,case.case_ref,actor_id=candidate[1],request=request()).response.proposal
    req=decision()
    def decide(index):
        with closing(db.connect(database)) as conn:
            try:
                return decide_response(conn,case.case_ref,proposal.recommendation_ref,actor_id=candidate[1],
                    decision='approved' if same_request or index==0 else 'rejected',request=req if same_request else decision())
            except ResponseConflict:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(decide,range(2)))
    assert sum(r is not None and not r.replayed for r in results)==1
    assert sum(r is not None and r.replayed for r in results)==int(same_request)
    with closing(db.connect(database)) as conn:
        assert conn.execute('SELECT count(*) FROM response_decisions').fetchone()[0]==1


@pytest.mark.parametrize('table',['response_recommendations','response_decisions'])
def test_write_failure_rolls_back(database,candidate,case,table):
    with closing(db.connect(database)) as conn:
        if table=='response_decisions':
            proposal=propose_response(conn,case.case_ref,actor_id=candidate[1],request=request()).response.proposal
        before=snapshot(conn)
        conn.execute(f"CREATE TRIGGER fail_response BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError,match='injected'):
            if table=='response_recommendations':
                propose_response(conn,case.case_ref,actor_id=candidate[1],request=request())
            else:
                decide_response(conn,case.case_ref,proposal.recommendation_ref,actor_id=candidate[1],decision='approved',request=decision())
        assert not conn.in_transaction and snapshot(conn)==before
        assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0


@pytest.mark.parametrize('role,status',[('evaluator',403),('',401)])
def test_http_all_actions_authenticated(client,database,candidate,case,role,status):
    root=f'/api/v2/tier2/cases/{case.case_ref}/responses'
    headers={'Authorization':'Bearer '+client.tokens[role] if role else ''}
    payload=request().model_dump(mode='json',by_alias=True)
    for suffix,extra in [('recommend',{}),('manual',{'recommendationType':'monitor','targetType':'case','targetValue':str(case.case_ref)}),
        (str(uuid4())+'/approve',{'expectedRevision':1}),(str(uuid4())+'/reject',{'expectedRevision':1})]:
        assert client.post(root+'/'+suffix,json={**payload,**extra},headers=headers).status_code==status
    assert client.get(root,headers=headers).status_code==(200 if role else 401)


def test_http_contract_admin_actor_binding_validation_and_read_history(client,database,candidate,case):
    root=f'/api/v2/tier2/cases/{case.case_ref}/responses'
    req=request().model_dump(mode='json',by_alias=True)
    for extra in ({'actorId':999},{'reason':'  '},{'expectedCaseRevision':True},{'severity':1},{'operationalPriority':100}):
        assert client.post(root+'/recommend',json={**req,**extra}).status_code==400
    admin={'Authorization':'Bearer '+client.tokens['admin']}
    result=client.post(root+'/recommend',json=req,headers=admin)
    assert result.status_code==200,result.text
    view=result.json()['response']
    with closing(db.connect(database)) as conn:
        admin_id=conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    assert view['proposal']['proposedByActorId']==admin_id
    assert view['proposal']['recommendationType']=='further_investigation'
    assert client.post(root+'/recommend',json=req).status_code==409
    ref=view['proposal']['recommendationRef']
    approved=client.post(root+'/'+ref+'/approve',json=decision().model_dump(mode='json',by_alias=True)).json()['response']
    assert approved['decision']['actorId']==candidate[1] and approved['executionStatus']=='not_executed'
    assert client.get(root).json()['items']==[approved]
    assert client.get(root+'?limit=201').status_code==400
    assert client.get(root+'?offset=1').json()['items']==[]
    assert client.get(f'/api/v2/tier2/cases/{uuid4()}/responses').status_code==404


def test_service_rechecks_actor_and_replay_identity(database,candidate,case):
    with closing(db.connect(database)) as conn:
        req=request()
        proposal=propose_response(conn,case.case_ref,actor_id=candidate[1],request=req).response.proposal
        evaluator=conn.execute("SELECT id FROM users WHERE username='evaluator'").fetchone()[0]
        for actor in (999999,evaluator):
            with pytest.raises(PermissionError):
                propose_response(conn,case.case_ref,actor_id=actor,request=req)
            with pytest.raises(PermissionError):
                decide_response(conn,case.case_ref,proposal.recommendation_ref,actor_id=actor,decision='rejected',request=decision())
        assert not conn.in_transaction


def test_migration_nine_additive_idempotent(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS
    with closing(db.connect(tmp_path/'migration.db')) as conn:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:8])
        db.create_schema(conn)
        before=snapshot(conn)
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:9])
        trace=[]
        conn.set_trace_callback(trace.append)
        assert db.migrate(conn)==[9] and db.migrate(conn)==[]
        assert snapshot(conn)==before
        assert not any(sql.lstrip().upper().startswith(('DROP ','ALTER ')) for sql in trace)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
