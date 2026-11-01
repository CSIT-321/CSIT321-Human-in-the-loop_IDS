"""Expert conclusions never rewrite system evidence, routing or earlier human decisions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
from uuid import uuid4
import pytest
from test_investigation_assistance import conn, api, admit, automatic_case, escalate, dump
from pre_freeze_fixture import event
from packages.contracts import db, models as m
from packages.detection.tier2_cases import (
    InvestigationConclusionRequest, CaseConflict, FindingRequest, LinkCaseRequest,
    mutate_case, read_case, read_events,
)
from packages.detection.investigation_assistance import read_assistance
from packages.detection.analyst_verdict import read_verdict, record_verdict, VerdictCommand


def command(finding='confirmed_malicious', category='web_attack', revision=1, **kwargs):
    return InvestigationConclusionRequest(request_id=uuid4(), expected_revision=revision,
        finding=finding, final_attack_category=category, reason='SYNTHETIC expert investigation conclusion', **kwargs)


def conclude(conn,case,request=None,actor=1):
    return mutate_case(conn,case.case_ref,actor_id=actor,action='finding',request=request or command())


@pytest.mark.parametrize('finding,category',[
    ('confirmed_malicious','web_attack'),('confirmed_malicious','other_known_attack'),
    ('suspicious','infiltration'),('suspicious',None),('inconclusive',None),
    ('inconclusive','reconnaissance_port_scan'),('expected_activity',None),
])
def test_finding_category_rules_roundtrip_and_readonly(conn,api,finding,category):
    case=automatic_case(conn,admit(conn));request=command(finding,category)
    response=api.post(f'/api/v2/tier2/cases/{case.case_ref}/conclusions',json=request.model_dump(mode='json',by_alias=True))
    assert response.status_code==200,response.text
    result=response.json()['case'];latest=result['latestConclusion']
    assert latest['finding']==finding and latest['finalAttackCategory']==category
    assert latest['actorId']==1 and latest['caseRevision']==2
    assert latest['requestId']==str(request.request_id)
    assert latest['systemClassification']['attackCategory']=='unknown_needs_expert'
    assert result['systemAttackClassification']['attackCategory']=='unknown_needs_expert'
    assert result['snapshot']==case.snapshot.model_dump(mode='json',by_alias=True)
    assert result['status']=='open'  # neither starts nor closes investigation
    before=dump(conn)
    assert api.get(f'/api/v2/tier2/cases/{case.case_ref}').json()['latestConclusion']==latest
    history=api.get(f'/api/v2/tier2/cases/{case.case_ref}/events',params={'action':'finding'}).json()
    assert history['items'][0]['conclusion']==latest
    assert history['items'][0]['eventType']=='V2_TIER2_INVESTIGATION_CONCLUSION_RECORDED'
    assert dump(conn)==before


@pytest.mark.parametrize('finding,category',[
    ('confirmed_malicious',None),('confirmed_malicious','unknown_needs_expert'),
    ('confirmed_malicious','benign'),('suspicious','false_positive'),
    ('inconclusive','expected_activity'),('expected_activity','brute_force'),('false_positive',None),
])
def test_invalid_conclusions_never_write(conn,api,finding,category):
    case=automatic_case(conn,admit(conn));before=dump(conn)
    result=api.post(f'/api/v2/tier2/cases/{case.case_ref}/conclusions',json={
        'requestId':str(uuid4()),'expectedRevision':1,'finding':finding,'finalAttackCategory':category,'reason':'SYNTHETIC invalid'})
    assert result.status_code==400,result.text
    assert dump(conn)==before


@pytest.mark.parametrize('reason',['','   '])
def test_reason_required(conn,api,reason):
    case=automatic_case(conn,admit(conn));before=dump(conn)
    body=command().model_dump(mode='json',by_alias=True);body['reason']=reason
    assert api.post(f'/api/v2/tier2/cases/{case.case_ref}/conclusions',json=body).status_code==400
    assert dump(conn)==before


def test_correction_history_supersession_and_request_id_conflicts(conn,api):
    case=automatic_case(conn,admit(conn));first_request=command('suspicious','web_attack')
    first=conclude(conn,case,first_request)
    first_row=tuple(conn.execute('SELECT * FROM tier2_case_events WHERE id=?',(first.event_id,)).fetchone())
    second=conclude(conn,first.case,command('confirmed_malicious','infiltration',2))
    assert second.case.latest_conclusion.supersedes_event_id==first.event_id
    assert second.case.latest_conclusion.final_attack_category=='infiltration'
    assert second.case.system_attack_classification.attack_category=='unknown_needs_expert'
    assert tuple(conn.execute('SELECT * FROM tier2_case_events WHERE id=?',(first.event_id,)).fetchone())==first_row
    assert conclude(conn,case,first_request).replayed is True  # even after a later correction
    assert read_case(conn,case.case_ref).revision==3
    with pytest.raises(CaseConflict): conclude(conn,case,first_request.model_copy(update={'final_attack_category':'dos'}))
    with pytest.raises(CaseConflict): conclude(conn,case,command())
    actor=db.insert(conn,m.User(username='other',display_name='Other',password_hash='synthetic',email='other@example.test',role='security_analyst'));conn.commit()
    with pytest.raises(CaseConflict): conclude(conn,case,first_request,actor)
    events,total=read_events(conn,case.case_ref,50,0,'finding')
    assert total==2 and [e.conclusion.finding for e in events]==['confirmed_malicious','suspicious']
    assert all(e.conclusion.record_kind=='investigation_conclusion' for e in events)
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        conn.execute('UPDATE tier2_case_events SET reason=? WHERE id=?',('overwrite',first.event_id))
    conn.rollback()


def frozen_tables(conn):
    excluded={'tier2_case_state','tier2_case_events','sqlite_sequence'}
    return {row[0]:[tuple(r) for r in conn.execute(f'SELECT * FROM "{row[0]}" ORDER BY rowid')]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if row[0] not in excluded and not row[0].startswith(('triage_memory_','conclusion_memory_'))}


def test_known_category_correction_preserves_all_other_tables_and_tier1_verdict(conn):
    alert=admit(conn,event(1,'SSH brute force',severity=1))
    view=read_verdict(conn,alert.operational_alert_ref,1)
    record_verdict(conn,alert.operational_alert_ref,actor_id=1,request=VerdictCommand(
        request_id=uuid4(),expected_revision=0,expected_state_version=view.source_state_version,
        outcome='suspicious',reason='SYNTHETIC original Tier 1 Verdict'))
    case=escalate(conn,alert)
    other=admit(conn,event(2,'Port scan',severity=1))
    case=mutate_case(conn,case.case_ref,actor_id=1,action='link',request=LinkCaseRequest(
        request_id=uuid4(),expected_revision=1,reason='SYNTHETIC related alert',operational_alert_ref=other.operational_alert_ref)).case
    before=frozen_tables(conn);old_events=[tuple(r) for r in conn.execute('SELECT * FROM tier2_case_events')]
    assistance=read_assistance(conn,case.case_ref)
    result=conclude(conn,case,command('confirmed_malicious','infiltration',2))
    assert result.case.system_attack_classification.attack_category=='brute_force'
    assert result.case.latest_conclusion.final_attack_category=='infiltration'
    assert result.case.latest_conclusion.system_classification==case.system_attack_classification
    assert frozen_tables(conn)==before  # detector evidence, system V3, priority/route, Verdict, Review, collection
    assert [tuple(r) for r in conn.execute('SELECT * FROM tier2_case_events WHERE id<>?',(result.event_id,))]==old_events
    after=read_assistance(conn,case.case_ref)
    assert after.brief.at_case_creation==assistance.brief.at_case_creation
    assert after.brief.classification_at_admission==assistance.brief.classification_at_admission
    assert after.brief.current_tier1_verdict==assistance.brief.current_tier1_verdict
    assert after.related_alerts==assistance.related_alerts
    assert after.suggested_steps==assistance.suggested_steps


@pytest.mark.parametrize('finding,category,kind',[
    ('confirmed_malicious','infiltration','block_source_ip'),('suspicious','infiltration','monitor'),
    ('expected_activity',None,'monitor'),('inconclusive',None,'further_investigation')])
def test_response_policy_remains_finding_gated(conn,api,finding,category,kind):
    case=automatic_case(conn,admit(conn));case=conclude(conn,case,command(finding,category)).case
    response=api.post(f'/api/v2/tier2/cases/{case.case_ref}/responses/recommend',json={
        'requestId':str(uuid4()),'expectedCaseRevision':case.revision,'reason':'SYNTHETIC review response plan'})
    assert response.status_code==200,response.text
    view=response.json()['response']
    assert view['proposal']['recommendationType']==kind and view['status']=='pending'
    assert view['proposal']['evidenceSnapshot']['finding']['eventId']==case.latest_conclusion.event_id
    assert conn.execute('SELECT count(*) FROM response_decisions').fetchone()[0]==0


def test_legacy_finding_remains_readable_without_fabrication(conn):
    case=automatic_case(conn,admit(conn))
    legacy=mutate_case(conn,case.case_ref,actor_id=1,action='finding',request=FindingRequest(
        request_id=uuid4(),expected_revision=1,finding='confirmed_malicious',reason='SYNTHETIC historical Finding'))
    before=dump(conn);old=legacy.case.latest_conclusion
    assert old.record_kind=='legacy_finding' and old.final_attack_category is None and old.system_classification is None
    assert read_events(conn,case.case_ref,50,0,'finding')[0][0].conclusion==old
    assert dump(conn)==before
    corrected=conclude(conn,legacy.case,command(revision=2)).case
    assert corrected.latest_conclusion.supersedes_event_id==old.event_id


@pytest.mark.parametrize('role',['evaluator','system_admin','security_analyst'])
def test_authenticated_authorization_and_no_system_actor(conn,api,role):
    from apps.api import auth
    case=automatic_case(conn,admit(conn));user=db.insert(conn,m.User(username=role,password_hash='synthetic',
        display_name=role,email=role+'@example.test',role=role));conn.commit()
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,user))
    before=dump(conn);path=f'/api/v2/tier2/cases/{case.case_ref}/conclusions';body=command().model_dump(mode='json',by_alias=True)
    result=api.post(path,json=body)
    assert result.status_code==(403 if role=='evaluator' else 200),result.text
    if role=='evaluator': assert dump(conn)==before
    api.headers.pop('Authorization');assert api.post(path,json=body).status_code==401
    for actor in (None,0):
        with pytest.raises(PermissionError): conclude(conn,case,command(),actor)


@pytest.mark.parametrize('same_request',[False,True])
def test_concurrent_conclusions_are_serialized(conn,same_request):
    case=automatic_case(conn,admit(conn));path=conn.execute('PRAGMA database_list').fetchone()[2];request=command()
    def write(_):
        with closing(db.connect(path)) as connection:
            try: return conclude(connection,case,request if same_request else command())
            except CaseConflict: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,range(2)))
    if same_request: assert sorted(r.replayed for r in results)==[False,True]
    else: assert results.count(None)==1
    assert read_events(conn,case.case_ref,50,0,'finding')[1]==1


def test_final_taxonomy_matches_existing_normalized_taxonomy_except_system_unknown():
    from typing import get_args
    from packages.contracts.suricata_bundle import AttackCategory
    from packages.detection.tier2_cases import FinalAttackCategory
    assert set(get_args(FinalAttackCategory))==set(get_args(AttackCategory))-{'unknown_needs_expert'}
    for category in get_args(FinalAttackCategory):
        assert command(category=category).final_attack_category==category


def test_cannot_spoof_system_policy_or_actor_and_inactive_user_cannot_write(conn,api):
    from apps.api import auth
    case=automatic_case(conn,admit(conn));path=f'/api/v2/tier2/cases/{case.case_ref}/conclusions'
    body=command().model_dump(mode='json',by_alias=True);before=dump(conn)
    for extra in ({'decisionSource':'system_policy'},{'actorId':999}):
        assert api.post(path,json={**body,**extra}).status_code==400
    assert dump(conn)==before
    conn.execute("UPDATE users SET status='inactive' WHERE id=1");conn.commit()
    api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,1))
    before=dump(conn)
    assert api.post(path,json=body).status_code in (401,403)
    with pytest.raises(PermissionError): conclude(conn,case,command())
    assert dump(conn)==before
