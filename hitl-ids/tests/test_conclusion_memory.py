"""Canonical expert learning, one-alert-one-vote, precedence and immediate safety withdrawal."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import sqlite3
import pytest
from test_pre_freeze_review_fixes import conn,api
from test_investigation_assistance import admit,automatic_case,escalate,dump
from test_tier2_human_reclassification import command,conclude
from test_verdict_memory import alerts,verdict,contribute as contribute_tier1
from pre_freeze_fixture import event,review_scenario
from packages.contracts import db,models as m
from packages.detection import triage_memory as memory
from packages.detection.selective_review import read_review
from packages.detection.tier2_cases import read_case,mutate_case,CaseCommand


def request(case,scope='exact'):
    return memory.ConclusionMemoryRequest(request_id=uuid4(),expected_case_revision=case.revision,
        conclusion_event_id=case.latest_conclusion.event_id,scope=scope)


def contribute(conn,case,scope='exact',actor=1):
    return memory.contribute_conclusion(conn,case.case_ref,actor_id=actor,request=request(case,scope))


@pytest.mark.parametrize('finding,category', [('confirmed_malicious','web_attack'),('suspicious','infiltration'),('expected_activity',None)])
def test_auto_expert_mapping_provenance_and_complete_source_isolation(conn,api,finding,category):
    alert=admit(conn);case=automatic_case(conn,alert)
    case=conclude(conn,case,command(finding,category)).case
    assert conn.execute('SELECT count(*) FROM triage_memory_lessons').fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM analyst_verdict_events').fetchone()[0]==0
    uid=db.insert(conn,m.User(username='contributor',password_hash='synthetic',display_name='Memory Contributor',email='c@example.test',role='security_analyst'));conn.commit()
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'triage_memory_%' AND name NOT LIKE 'conclusion_memory_%'")]
    before={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}
    result=contribute(conn,case,actor=uid).memory
    assert result.support_count==1 and result.status=='candidate' and result.decision is None
    history=memory.memory_history(conn,result.lesson.lesson_ref,50,0)[0]
    evidence=history[0].evidence
    assert evidence.source_kind=='tier2_conclusion' and evidence.source_verdict_ref is None
    assert evidence.source_conclusion==case.latest_conclusion
    assert evidence.source_conclusion.final_attack_category==category
    assert evidence.source_operational_alert_ref==alert.operational_alert_ref and evidence.source_case_ref==case.case_ref
    assert evidence.actor_id is None and evidence.contribution_actor_name is None and evidence.decision_source=='system_policy'
    assert evidence.source_conclusion.actor_id==1 and evidence.conclusion_author_name=='Reviewer'
    assert evidence.human_reason==case.latest_conclusion.reason and evidence.outcome==finding
    assert evidence.context_snapshot==memory.context_for(alert) and evidence.detector_snapshot==alert
    assert evidence.contribution_scope=='exact' and history[0].evidence_current is True
    assert {t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}==before
    before=dump(conn)
    state=api.get(f'/api/v2/tier2/cases/{case.case_ref}/triage-memory/conclusion-state')
    assert state.status_code==200 and state.json()['contributionStatus']=='contributed'
    assert dump(conn)==before


@pytest.mark.parametrize('finding,category',[('confirmed_malicious','infiltration'),('inconclusive',None)])
def test_tier1_superseded_immediately_even_without_expert_contribution(conn,finding,category):
    alert=alerts(conn,1)[0];v=verdict(conn,alert)
    lesson=contribute_tier1(conn,alert,v).memory
    case=escalate(conn,alert);case=conclude(conn,case,command(finding,category)).case
    assert memory.read_memory(conn,lesson.lesson.lesson_ref).support_count==0
    assert memory.verdict_memory_state(conn,alert.operational_alert_ref).contribution_status=='superseded'
    state=memory.conclusion_memory_state(conn,case.case_ref)
    assert state.tier1_evidence_superseded and state.contribution_status==('not_contributed' if finding=='inconclusive' else 'contributed')
    assert conn.execute('SELECT count(*) FROM conclusion_memory_contributions').fetchone()[0]==int(finding!='inconclusive')
    history=memory.memory_history(conn,lesson.lesson.lesson_ref,200,0)[0]
    assert all(e.evidence_current is False for e in history if e.evidence and e.evidence.source_kind=='analyst_verdict')
    assert any(e.event_type=='V2_TRIAGE_MEMORY_EXPERT_SUPERSEDED' for e in history)
    if finding=='inconclusive':
        assert state.eligible is False
        with pytest.raises(memory.MemoryConflict):contribute(conn,case)
        assert memory.read_memory(conn,lesson.lesson.lesson_ref).support_count==0
    else:
        result=contribute(conn,case).memory
        assert result.support_count==0 and result.conflict_count==1
        effective,_=memory.effective_evidence(conn,conn.execute('SELECT id FROM triage_memory_lessons WHERE lesson_ref=?',(str(result.lesson.lesson_ref),)).fetchone()[0])
        assert len(effective)==1 and effective[0].source_kind=='tier2_conclusion'
    with pytest.raises(memory.MemoryConflict):contribute_tier1(conn,alert,v)


def test_correction_replay_dedup_and_conflicting_identity(conn):
    case=automatic_case(conn,admit(conn));case=conclude(conn,case,command('suspicious','web_attack')).case
    req=request(case);first=memory.contribute_conclusion(conn,case.case_ref,actor_id=1,request=req).memory
    assert memory.contribute_conclusion(conn,case.case_ref,actor_id=1,request=req).replayed
    assert contribute(conn,case).replayed
    narrow=contribute(conn,case,'narrow')
    assert narrow.memory.support_count==1 and narrow.memory.decision is None
    uid=db.insert(conn,m.User(username='other',display_name='Other',password_hash='synthetic',email='o@example.test',role='security_analyst'));conn.commit()
    assert memory.contribute_conclusion(conn,case.case_ref,actor_id=uid,request=req).replayed
    newer=conclude(conn,case,command('confirmed_malicious','infiltration',case.revision)).case
    assert memory.read_memory(conn,first.lesson.lesson_ref).support_count==0
    state=memory.conclusion_memory_state(conn,newer.case_ref)
    assert state.previous_expert_evidence_superseded and state.contribution_status=='contributed'
    with pytest.raises(memory.MemoryConflict):memory.contribute_conclusion(conn,case.case_ref,actor_id=1,request=req.model_copy(update={'request_id':uuid4(),'expected_case_revision':newer.revision}))
    with pytest.raises(memory.MemoryConflict):memory.contribute_conclusion(conn,case.case_ref,actor_id=1,request=req)
    current=contribute(conn,newer).memory
    assert current.support_count==0 and current.conflict_count==1
    events=memory.memory_history(conn,current.lesson.lesson_ref,200,0)[0]
    assert any(e.evidence and e.evidence.source_conclusion.event_id==case.latest_conclusion.event_id and e.evidence_current is False for e in events)
    assert any(e.evidence and e.evidence.source_conclusion.event_id==newer.latest_conclusion.event_id and e.evidence_current is True for e in events)


def test_three_distinct_cases_support_activation_and_cross_scope_conflict(conn):
    cases=[automatic_case(conn,admit(conn,event(i+1,'Unresolved suspicious same pattern','Misc activity',4))) for i in range(4)]
    for index,case in enumerate(cases[:3],1):
        current=conclude(conn,case,command(category=['web_attack','infiltration','other_known_attack'][index-1])).case
        lesson=contribute(conn,current).memory
        assert lesson.support_count==index
        assert lesson.decision is None
    assert lesson.status=='eligible_for_activation'
    active=memory.decide_memory(conn,lesson.lesson.lesson_ref,actor_id=1,action='activate',request=memory.MemoryDecisionRequest(
        request_id=uuid4(),expected_revision=lesson.revision,reason='SYNTHETIC reviewed three independent expert sources')).memory
    assert active.status=='active'
    conflicting=conclude(conn,cases[3],command('expected_activity',None)).case
    contribute(conn,conflicting,'narrow')
    old=memory.read_memory(conn,active.lesson.lesson_ref)
    assert old.status=='conflict_review' and old.conflict_count==1
    assert not memory.explain_match(old,memory.context_for(cases[0].snapshot.detector)).guidance_active


def test_active_memory_withdraws_selective_review_queue_and_kpis_before_contribution(conn,api):
    aa=review_scenario(conn);old=memory.verdict_memory_state(conn,aa[0].operational_alert_ref)
    assert read_review(conn,aa[3].operational_alert_ref).disposition=='no_immediate_review'
    revision=memory.read_memory(conn,old.lesson_ref).revision
    case=escalate(conn,aa[0]);conclude(conn,case,command('inconclusive',None))
    before=dump(conn);conn.execute('PRAGMA query_only=ON')
    lesson=memory.read_memory(conn,old.lesson_ref)
    assert lesson.support_count==2 and lesson.status=='candidate' and lesson.revision>revision
    assert read_review(conn,aa[3].operational_alert_ref).disposition=='must_review'
    assert dump(conn)==before;conn.execute('PRAGMA query_only=OFF')
    assert api.get('/api/v2/alerts/summary').json()['noImmediateReview']==0
    assert api.get('/api/v2/alerts',params={'reviewDisposition':'no_immediate_review'}).json()['page']['total']==0
    assert dump(conn)==before


@pytest.mark.parametrize('extra',[{'outcome':'false_positive'},{'reason':'tampered'},{'finalAttackCategory':'dos'},{'actorId':999}])
def test_api_rejects_caller_provenance_overrides(conn,api,extra):
    case=conclude(conn,automatic_case(conn,admit(conn))).case;before=dump(conn)
    response=api.post(f'/api/v2/tier2/cases/{case.case_ref}/triage-memory/from-conclusion',json={**request(case).model_dump(mode='json',by_alias=True),**extra})
    assert response.status_code==400 and dump(conn)==before


def test_no_conclusion_inconclusive_stale_revision_missing_case_roles_and_auth(conn,api):
    from apps.api import auth
    case=automatic_case(conn,admit(conn));url=f'/api/v2/tier2/cases/{case.case_ref}/triage-memory/from-conclusion'
    body={'requestId':str(uuid4()),'expectedCaseRevision':1,'conclusionEventId':999,'scope':'exact'}
    assert api.post(url,json=body).status_code==409
    case=conclude(conn,case,command('inconclusive',None)).case
    assert api.post(url,json=request(case).model_dump(mode='json',by_alias=True)).status_code==409
    case=conclude(conn,case,command('expected_activity',None,case.revision)).case
    body=request(case).model_dump(mode='json',by_alias=True)
    assert api.post(url,json={**body,'expectedCaseRevision':1}).status_code==409
    assert api.post(url.replace(str(case.case_ref),str(uuid4())),json=body).status_code==404
    uid=db.insert(conn,m.User(username='evaluator',display_name='Evaluator',password_hash='x',email='e@example.test',role='evaluator'));conn.commit()
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,uid));before=dump(conn)
    assert api.get(url.replace('from-conclusion','conclusion-state')).status_code==200
    assert api.post(url,json=body).status_code==403 and dump(conn)==before
    api.headers.pop('Authorization');assert api.post(url,json=body).status_code==401
    with pytest.raises(PermissionError):contribute(conn,case,actor=None)


def test_contribution_rollback_and_immutable_evidence(conn):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    conn.execute("CREATE TRIGGER fail_expert BEFORE INSERT ON conclusion_memory_evidence BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    before=dump(conn)
    with pytest.raises(sqlite3.IntegrityError):contribute(conn,case,'narrow')
    assert dump(conn)==before
    conn.execute('DROP TRIGGER fail_expert');conn.commit();contribute(conn,case)
    for table in ('conclusion_memory_contributions','conclusion_memory_evidence'):
        with pytest.raises(sqlite3.IntegrityError):conn.execute(f'DELETE FROM {table}')
        conn.rollback()


def test_concurrent_same_conclusion_cannot_add_support_twice(conn):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    path=conn.execute('PRAGMA database_list').fetchone()[2];req=request(case)
    def write(_):
        with closing(db.connect(path)) as c:return memory.contribute_conclusion(c,case.case_ref,actor_id=1,request=req)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,range(2)))
    assert sorted(r.replayed for r in results)==[True,True]
    assert results[0].memory.support_count==1 and conn.execute('SELECT count(*) FROM conclusion_memory_contributions').fetchone()[0]==1


def test_exact_positive_does_not_broaden_narrow_support_but_conflict_fans_out(conn):
    cases=[automatic_case(conn,admit(conn,event(i+1,'Unresolved suspicious scope test','Misc activity',4))) for i in range(3)]
    narrow=contribute(conn,conclude(conn,cases[0],command('expected_activity',None)).case,'narrow').memory
    exact=contribute(conn,conclude(conn,cases[1],command('expected_activity',None)).case).memory
    assert memory.read_memory(conn,narrow.lesson.lesson_ref).support_count==1
    assert exact.support_count==2
    contribute(conn,conclude(conn,cases[2],command()).case)
    assert memory.read_memory(conn,narrow.lesson.lesson_ref).conflict_count==1
    assert memory.read_memory(conn,exact.lesson.lesson_ref).conflict_count==1


def test_critical_automatic_case_needs_no_tier1_and_admin_can_contribute(conn):
    from datetime import timedelta
    from packages.detection.context_store import collect_fact,FactRequest
    now=m.utc_now();raw=event(1,'SQL injection',severity=1)
    collect_fact(conn,actor_id=1,request=FactRequest(request_id=uuid4(),expected_revision=0,subject_type='ip',
        subject_value=raw['dest_ip'],context_key='assetCriticality',value='critical',observed_at=now-timedelta(seconds=1),
        valid_from=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1),source_reference='synthetic:critical-expert',reason='SYNTHETIC critical asset'))
    case=automatic_case(conn,admit(conn,raw));case=conclude(conn,case,command()).case
    uid=db.insert(conn,m.User(username='admin',display_name='Admin',password_hash='synthetic',email='a@example.test',role='system_admin'));conn.commit()
    assert contribute(conn,case,actor=uid).memory.support_count==1
    assert conn.execute('SELECT count(*) FROM analyst_verdict_events').fetchone()[0]==0
    assert read_case(conn,case.case_ref).system_attack_classification.attack_category=='web_attack'
