"""Explicit terminal Case lifecycle, immutable resolution evidence and unchanged learning."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4
import sqlite3
import pytest
from test_pre_freeze_review_fixes import conn,api
from test_investigation_assistance import admit,automatic_case,dump
from test_tier2_human_reclassification import command,conclude
from test_conclusion_memory import contribute
from packages.contracts import db,models as m
from packages.detection.tier2_cases import CaseCommand,CaseConflict,FindingRequest,LinkCaseRequest,mutate_case,read_case,read_events
from packages.detection.response_approval import (
    ResponseRequest,ResponseDecisionRequest,ResponseConflict,propose_response,decide_response,list_responses,
)
from packages.detection import triage_memory as memory
from packages.detection.investigation_assistance import read_assistance


def request(case,reason='SYNTHETIC investigation complete; no execution performed'):
    return CaseCommand(request_id=uuid4(),expected_revision=case.revision,reason=reason)


def resolve(conn,case,req=None,actor=1):
    return mutate_case(conn,case.case_ref,actor_id=actor,action='resolve',request=req or request(case))


def proposal(conn,case):
    return propose_response(conn,case.case_ref,actor_id=1,request=ResponseRequest(
        request_id=uuid4(),expected_case_revision=case.revision,reason='SYNTHETIC propose human-reviewed plan')).response


def decide(conn,case,view,decision='approved'):
    req=ResponseDecisionRequest(request_id=uuid4(),expected_case_revision=case.revision,expected_revision=view.revision,
        reason='SYNTHETIC human plan decision only')
    return decide_response(conn,case.case_ref,view.proposal.recommendation_ref,actor_id=1,decision=decision,request=req),req


def unaffected(conn):
    return {r[0]:[tuple(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if r[0] not in ('tier2_case_state','tier2_case_events','sqlite_sequence')}


@pytest.mark.parametrize('finding,category',[
    ('confirmed_malicious','web_attack'),('suspicious','infiltration'),('inconclusive',None),('expected_activity',None)])
def test_all_findings_resolve_explicitly_preserve_all_other_tables_and_reads(conn,api,finding,category):
    case=automatic_case(conn,admit(conn))
    case=mutate_case(conn,case.case_ref,actor_id=1,action='start',request=request(case)).case
    case=conclude(conn,case,command(finding,category,case.revision)).case
    before=unaffected(conn);prior=[tuple(r) for r in conn.execute('SELECT * FROM tier2_case_events')]
    body=request(case);result=api.post(f'/api/v2/tier2/cases/{case.case_ref}/resolve',json=body.model_dump(mode='json',by_alias=True))
    assert result.status_code==200,result.text
    saved=result.json()['case'];resolution=saved['resolution']
    assert saved['status']=='resolved' and saved['revision']==case.revision+1
    assert resolution['previousStatus']=='investigating' and resolution['newStatus']=='resolved'
    assert resolution['actorId']==1 and resolution['actorName']=='Reviewer'
    assert resolution['requestId']==str(body.request_id) and resolution['conclusion']['eventId']==case.latest_conclusion.event_id
    assert resolution['conclusion']['finding']==finding and resolution['responses']==[]
    assert unaffected(conn)==before
    assert [tuple(r) for r in conn.execute('SELECT * FROM tier2_case_events WHERE action<>?',('resolve',))]==prior
    original=dump(conn)
    for suffix in ('','/events','/assistance','/responses','/triage-memory/conclusion-state'):
        assert api.get(f'/api/v2/tier2/cases/{case.case_ref}'+suffix).status_code==200
    assert dump(conn)==original
    event=api.get(f'/api/v2/tier2/cases/{case.case_ref}/events',params={'action':'resolve'}).json()['items'][0]
    assert event['eventType']=='V2_TIER2_CASE_RESOLVED' and event['resolution']==resolution
    assert saved['snapshot']==case.snapshot.model_dump(mode='json',by_alias=True)
    assert saved['latestConclusion']==case.latest_conclusion.model_dump(mode='json',by_alias=True)


def test_no_conclusion_no_resolution_and_no_automatic_close(conn,api):
    case=automatic_case(conn,admit(conn));before=dump(conn)
    assert api.post(f'/api/v2/tier2/cases/{case.case_ref}/resolve',json=request(case).model_dump(mode='json',by_alias=True)).status_code==409
    assert dump(conn)==before
    case=conclude(conn,case).case;assert case.status=='open'
    contribute(conn,case);assert read_case(conn,case.case_ref).status=='open'
    pending=proposal(conn,case);decide(conn,case,pending)
    assert read_case(conn,case.case_ref).status=='open'
    assert resolve(conn,case).case.status=='resolved'  # explicit Start is not an invented prerequisite


@pytest.mark.parametrize('extra',[{'reason':''},{'reason':'   '},{'finding':'confirmed_malicious'},
    {'finalAttackCategory':'infiltration'},{'actorId':999},{'decisionSource':'system_policy'}])
def test_invalid_reason_or_caller_supplied_derived_facts_never_write(conn,api,extra):
    case=conclude(conn,automatic_case(conn,admit(conn))).case;before=dump(conn)
    body={**request(case).model_dump(mode='json',by_alias=True),**extra}
    assert api.post(f'/api/v2/tier2/cases/{case.case_ref}/resolve',json=body).status_code==400
    assert dump(conn)==before


def test_replay_identity_and_closed_case_new_actions_rejected(conn,api):
    case=conclude(conn,automatic_case(conn,admit(conn))).case;req=request(case)
    closed=resolve(conn,case,req).case;before=dump(conn)
    assert resolve(conn,case,req).replayed is True
    assert read_events(conn,case.case_ref,50,0,'resolve')[1]==1
    with pytest.raises(CaseConflict):resolve(conn,closed,req.model_copy(update={'reason':'changed'}))
    with pytest.raises(CaseConflict):resolve(conn,closed)
    with pytest.raises(CaseConflict):mutate_case(conn,case.case_ref,actor_id=1,action='note',request=req)
    uid=db.insert(conn,m.User(username='other',display_name='Other',password_hash='x',email='o@example.test',role='security_analyst'));conn.commit()
    with pytest.raises(CaseConflict):resolve(conn,case,req,uid)
    before=dump(conn)
    for suffix,body in [
        ('notes',request(closed)),('start-investigation',request(closed)),
        ('findings',FindingRequest(**request(closed).model_dump(),finding='suspicious')),
        ('conclusions',command('suspicious','infiltration',closed.revision)),
        ('alerts',LinkCaseRequest(**request(closed).model_dump(),operational_alert_ref=closed.primary_operational_alert_ref))]:
        response=api.post(f'/api/v2/tier2/cases/{closed.case_ref}/{suffix}',json=body.model_dump(mode='json',by_alias=True))
        assert response.status_code==409,response.text
    assert dump(conn)==before
    with pytest.raises(sqlite3.IntegrityError,match='closed'):
        conn.execute("UPDATE tier2_case_state SET status='open' WHERE case_id=(SELECT id FROM tier2_cases WHERE case_ref=?)",(str(case.case_ref),))
    conn.rollback()


@pytest.mark.parametrize('decision',['approved','rejected'])
def test_pending_response_blocks_resolution_terminal_decisions_preserved(conn,decision):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    p=proposal(conn,case);before=dump(conn)
    with pytest.raises(CaseConflict,match='approval or rejection'):resolve(conn,case)
    assert dump(conn)==before
    decided,req=decide(conn,case,p,decision);before=unaffected(conn)
    closed=resolve(conn,case).case
    assert closed.resolution.responses[0].approval_status==decision
    assert closed.resolution.responses[0].execution_status=='not_executed'
    assert closed.resolution.responses[0].recommendation_ref==p.proposal.recommendation_ref
    assert unaffected(conn)==before
    assert list_responses(conn,case.case_ref,50,0)[0][0]==decided.response
    assert decide_response(conn,case.case_ref,p.proposal.recommendation_ref,actor_id=1,decision=decision,request=req).replayed
    with pytest.raises(ResponseConflict,match='resolved'):proposal(conn,closed)
    with pytest.raises(ResponseConflict,match='resolved'):decide(conn,closed,decided.response,'rejected')


def test_every_pending_response_including_stale_proposal_requires_decision(conn):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    first=proposal(conn,case);second=proposal(conn,case);decide(conn,case,second)
    with pytest.raises(CaseConflict):resolve(conn,case)
    case=conclude(conn,case,command('expected_activity',None,case.revision)).case
    # A stale proposal can be explicitly rejected under existing response semantics.
    decide(conn,case,first,'rejected')
    closed=resolve(conn,case).case
    assert len(closed.resolution.responses)==2


def test_current_learning_survives_resolution_without_memory_or_review_changes(conn):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    lesson=contribute(conn,case).memory;before=unaffected(conn)
    old=read_assistance(conn,case.case_ref)
    closed=resolve(conn,case).case
    state=memory.conclusion_memory_state(conn,case.case_ref)
    assert state.contribution_status=='contributed' and state.latest_conclusion==case.latest_conclusion
    assert memory.read_memory(conn,lesson.lesson.lesson_ref)==lesson
    assert all(e.evidence_current is True for e in memory.memory_history(conn,lesson.lesson.lesson_ref,50,0)[0] if e.evidence)
    assert unaffected(conn)==before
    new=read_assistance(conn,case.case_ref)
    assert new.brief.at_case_creation==old.brief.at_case_creation and new.brief.current_case_status=='resolved'
    assert closed.status=='resolved'


@pytest.mark.parametrize('role',['evaluator','system_admin','security_analyst'])
def test_resolution_auth_roles_and_no_system_actor(conn,api,role):
    from apps.api import auth
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    uid=db.insert(conn,m.User(username=role,display_name=role,password_hash='x',email=role+'@example.test',role=role));conn.commit()
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,uid))
    before=dump(conn);url=f'/api/v2/tier2/cases/{case.case_ref}/resolve'
    response=api.post(url,json=request(case).model_dump(mode='json',by_alias=True))
    assert response.status_code==(403 if role=='evaluator' else 200)
    if role=='evaluator':assert dump(conn)==before
    assert api.get(url.removesuffix('/resolve')).status_code==200
    api.headers.pop('Authorization');assert api.post(url,json=request(case).model_dump(mode='json',by_alias=True)).status_code==401
    with pytest.raises(PermissionError):resolve(conn,case,actor=None)


def test_resolution_rollback_on_audit_failure(conn):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    conn.execute("CREATE TRIGGER resolution_fail BEFORE INSERT ON tier2_case_events WHEN NEW.action='resolve' BEGIN SELECT RAISE(ABORT,'injected'); END");conn.commit()
    before=dump(conn)
    with pytest.raises(sqlite3.IntegrityError):resolve(conn,case)
    assert dump(conn)==before


@pytest.mark.parametrize('same_request',[False,True])
def test_concurrent_resolution_is_single_terminal_event(conn,same_request):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    path=conn.execute('PRAGMA database_list').fetchone()[2];req=request(case)
    def write(_):
        with closing(db.connect(path)) as c:
            try:return resolve(c,case,req if same_request else request(case))
            except CaseConflict:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,range(2)))
    if same_request:assert sorted(r.replayed for r in results)==[False,True]
    else:assert results.count(None)==1
    assert read_case(conn,case.case_ref).status=='resolved'
    assert read_events(conn,case.case_ref,50,0,'resolve')[1]==1


def test_migration_19_preserves_populated_event_ids_memory_and_response_foreign_keys(tmp_path,monkeypatch):
    path=tmp_path/'upgrade.db'
    with closing(db.connect(path)) as c:
        with monkeypatch.context() as patch:
            patch.setattr(db,'MIGRATIONS',tuple(m for m in db.MIGRATIONS if m[0]<19));db.create_schema(c)
        db.insert(c,m.User(username='reviewer',display_name='Reviewer',password_hash='x',email='r@example.test',role='security_analyst'));c.commit()
        case=conclude(c,automatic_case(c,admit(c))).case;contribute(c,case)
        p=proposal(c,case);decide(c,case,p)
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}
        assert db.migrate(c)==[19] and db.migrate(c)==[]
        assert {t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}==before
        assert c.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert resolve(c,read_case(c,case.case_ref)).case.status=='resolved'


def test_resolved_case_is_historical_tier2_but_not_counted_as_open(conn,api):
    case=conclude(conn,automatic_case(conn,admit(conn))).case
    before=api.get('/api/v2/alerts/summary').json();resolve(conn,case)
    after=api.get('/api/v2/alerts/summary').json()
    assert before['openTier2Cases']==1 and after['openTier2Cases']==0
    assert {k:v for k,v in after.items() if k!='openTier2Cases'}=={k:v for k,v in before.items() if k!='openTier2Cases'}
    listed=api.get('/api/v2/tier2/cases').json()
    assert listed['items'][0]['status']=='resolved' and listed['page']['total']==1


def test_expected_activity_monitor_response_does_not_imply_containment(conn):
    case=conclude(conn,automatic_case(conn,admit(conn)),command('expected_activity',None)).case
    p=proposal(conn,case);assert p.proposal.recommendation_type=='monitor'
    decide(conn,case,p);closed=resolve(conn,case).case
    assert closed.resolution.responses[0].recommendation_type=='monitor'
    assert closed.resolution.responses[0].execution_status=='not_executed'


def test_exact_old_case_command_retry_is_nonmutating_after_closure_and_legacy_finding_is_readable(conn):
    case=automatic_case(conn,admit(conn));note=request(case,'SYNTHETIC retained note')
    case=mutate_case(conn,case.case_ref,actor_id=1,action='note',request=note).case
    case=mutate_case(conn,case.case_ref,actor_id=1,action='finding',request=FindingRequest(
        **request(case).model_dump(),finding='expected_activity')).case
    assert case.latest_conclusion.record_kind=='legacy_finding'
    closed=resolve(conn,case).case;before=dump(conn)
    replay=mutate_case(conn,case.case_ref,actor_id=1,action='note',request=note)
    assert replay.replayed and replay.case.status=='resolved' and dump(conn)==before
    assert closed.resolution.conclusion.final_attack_category is None
