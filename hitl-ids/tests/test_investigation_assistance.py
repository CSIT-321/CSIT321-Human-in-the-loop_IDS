"""Assistance reads real operational cases; it never synthesizes decisions or evidence."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path
import pytest
from test_pre_freeze_review_fixes import conn, api
from test_inspection_readonly import fingerprint
from test_tier2_cases import candidate, client, database, inbox, creation
from pre_freeze_fixture import event, stage, admit_all
from packages.contracts import db, models as m
from packages.detection.investigation_assistance import read_assistance, load_policy, related_alerts
from packages.detection.tier2_cases import read_case, mutate_case, LinkCaseRequest, CaseCommand
from packages.detection.tier2_escalation import escalate_case, EscalateCaseRequest
from packages.detection.analyst_verdict import record_verdict, read_verdict, VerdictCommand
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.routing import state_version
from packages.detection.context_store import collect_fact, FactRequest, revision


def admit(conn, raw=None, *, sensor='review-sensor'):
    stage(conn, [raw or event(1, 'Unresolved suspicious activity', 'Misc activity', 4)],
          scope=str(uuid4()), sensor=sensor)
    return admit_all(conn)[0]


def automatic_case(conn, alert):
    ref = conn.execute('SELECT case_ref FROM tier2_cases WHERE primary_operational_alert_id=?', (alert.id,)).fetchone()[0]
    return read_case(conn, ref)


def escalate(conn, alert):
    return escalate_case(conn, alert.operational_alert_ref, actor_id=1, request=EscalateCaseRequest(
        request_id=uuid4(), reason='SYNTHETIC deeper review',
        expected_state_version=state_version(read_triage(conn, alert.id)))).case


def dump(conn):
    return '\n'.join(conn.iterdump())


def test_unknown_brief_read_only_full_database_and_optional_evidence(conn, api):
    alert = admit(conn); case = automatic_case(conn, alert)
    before = dump(conn)
    database_path=Path(conn.execute('PRAGMA database_list').fetchone()[2])
    original_fingerprint=fingerprint(database_path)
    path = f'/api/v2/tier2/cases/{case.case_ref}/assistance'
    for _ in range(2):
        result = api.get(path)
        assert result.status_code == 200, result.text
        brief = result.json()['brief']
        assert brief['atCaseCreation'] == case.snapshot.model_dump(mode='json', by_alias=True)
        assert brief['systemRoutingAtAdmission']['routeClass'] == 'EXPERT_REVIEW_REQUIRED'
        assert brief['classificationAtAdmission']['attackCategory'] == 'unknown_needs_expert'
        assert brief['currentTier1Verdict'] is None
        assert 'not required' in brief['tier1VerdictExplanation']
        assert brief['suricataEvidenceAtCreation']['evidenceTypes'] == ['alert']
        assert brief['atCaseCreation']['detector']['detectorConfidence'] is None
        assert any('Optional evidence not recorded' in text for text in brief['uncertainties'])
        assert all(field['value'] is None for field in brief['currentTrustedContext']['fields'])
    assert dump(conn) == before
    assert fingerprint(database_path)==original_fingerprint
    assert api.get(f'/api/v2/tier2/cases/{uuid4()}/assistance').status_code == 404
    assert dump(conn) == before


def test_current_context_and_case_changes_do_not_rewrite_snapshot(conn):
    alert = admit(conn); case = automatic_case(conn, alert)
    before = read_assistance(conn, case.case_ref)
    now = m.utc_now()
    collect_fact(conn, actor_id=1, request=FactRequest(request_id=uuid4(), expected_revision=revision(conn),
        subject_type='ip', subject_value=alert.destination_ip, context_key='assetCriticality', value='critical',
        observed_at=now-timedelta(seconds=1), valid_from=now-timedelta(minutes=1), expires_at=now+timedelta(hours=1),
        source_reference='SYNTHETIC asset registry', reason='SYNTHETIC critical asset evidence'))
    mutate_case(conn, case.case_ref, actor_id=1, action='start', request=CaseCommand(
        request_id=uuid4(), expected_revision=1, reason='SYNTHETIC start investigation'))
    after = read_assistance(conn, case.case_ref)
    assert after.brief.at_case_creation == before.brief.at_case_creation
    assert after.brief.current_case_status == 'investigating' and after.brief.current_case_revision == 2
    field = next(f for f in after.brief.current_trusted_context.fields if f.context_key == 'assetCriticality')
    assert field.value == 'critical' and field.status == 'trusted'
    assert field.facts[0].source_reference == 'SYNTHETIC asset registry'
    assert before.brief.current_trusted_context != after.brief.current_trusted_context


def test_critical_brief_uses_recorded_policy_not_native_severity_guess(conn):
    now=m.utc_now()
    raw=event(1, 'SQL injection', severity=1)
    collect_fact(conn, actor_id=1, request=FactRequest(request_id=uuid4(), expected_revision=0,
        subject_type='ip', subject_value=raw['dest_ip'], context_key='assetCriticality', value='critical',
        observed_at=now-timedelta(seconds=1), valid_from=now-timedelta(minutes=1), expires_at=now+timedelta(hours=1),
        source_reference='SYNTHETIC critical registry', reason='SYNTHETIC asset evidence'))
    alert=admit(conn,raw);case=automatic_case(conn,alert)
    brief=read_assistance(conn,case.case_ref).brief
    assert brief.system_routing_at_admission.route_class=='CRITICAL_ESCALATION'
    assert brief.classification_at_admission.attack_category=='web_attack'
    assert brief.at_case_creation.detector.native_severity==1
    assert brief.current_tier1_verdict is None
    assert any('Critical Escalation' in step for step in read_assistance(conn,case.case_ref).suggested_steps)


@pytest.mark.parametrize('has_verdict', [False, True])
def test_manual_escalation_current_verdict_is_explicit_not_snapshot_rewrite(conn,has_verdict):
    alert=admit(conn,event(1,'SSH brute force',severity=1))
    if has_verdict:
        view=read_verdict(conn,alert.operational_alert_ref,1)
        record_verdict(conn,alert.operational_alert_ref,actor_id=1,request=VerdictCommand(
            request_id=uuid4(),expected_revision=view.revision,expected_state_version=view.source_state_version,
            outcome='suspicious',reason='SYNTHETIC suspicious authentication evidence'))
    case=escalate(conn,alert);before=dump(conn)
    brief=read_assistance(conn,case.case_ref).brief
    assert brief.at_case_creation==case.snapshot
    assert brief.at_case_creation.routing_decision.decision_source=='analyst'
    assert brief.system_routing_at_admission.route_class=='ROUTINE_REVIEW'
    if has_verdict:
        assert brief.current_tier1_verdict.outcome=='suspicious'
        assert brief.current_tier1_verdict.reason=='SYNTHETIC suspicious authentication evidence'
    else:
        assert brief.current_tier1_verdict is None and 'does not imply' in brief.tier1_verdict_explanation
    assert dump(conn)==before


def test_related_bounds_exclusions_offset_time_and_manual_link_replay(conn,api):
    primary=admit(conn);case=automatic_case(conn,primary)
    stamp=datetime.fromisoformat(primary.occurred_at.replace('Z','+00:00'))
    compact_offset_alert=admit(conn,event(99,'SSH brute force',severity=1))
    # More candidates than the configured result bound; tie by timestamp/ref is reproducible.
    for i in range(24):
        raw=event(100+i,'SSH brute force',severity=1)
        raw['timestamp']=(stamp+timedelta(minutes=i)).isoformat()
        admit(conn,raw)
    outside=event(200,'SSH brute force');outside['timestamp']=(stamp+timedelta(hours=24,seconds=1)).isoformat()
    out=admit(conn,outside)
    unrelated=event(201,'SQL injection','Web Application Attack');unrelated.update(src_ip='203.0.113.88',dest_ip='203.0.113.99')
    unrelated['alert']['signature_id']+=9
    no=admit(conn,unrelated,sensor='different-sensor')
    edge=event(202,'SSH brute force');edge['timestamp']=(stamp-timedelta(hours=24)).astimezone(timezone(timedelta(hours=-5))).isoformat()
    admitted_edge=admit(conn,edge)
    all_related=related_alerts(conn,case,read_assistance(conn,case.case_ref).brief.classification_at_admission,
        load_policy().model_copy(update={'maximum_related':100}))
    assert admitted_edge.operational_alert_ref in {a.operational_alert_ref for a in all_related}
    assert compact_offset_alert.operational_alert_ref in {a.operational_alert_ref for a in all_related}
    assert out.operational_alert_ref not in {a.operational_alert_ref for a in all_related}
    assert no.operational_alert_ref not in {a.operational_alert_ref for a in all_related}
    first=read_assistance(conn,case.case_ref);second=read_assistance(conn,case.case_ref)
    assert first.related_alerts==second.related_alerts and len(first.related_alerts)==20
    refs=[a.operational_alert_ref for a in first.related_alerts]
    assert primary.operational_alert_ref not in refs and len(refs)==len(set(refs))
    assert first.related_alerts[0].occurred_at>first.related_alerts[-1].occurred_at
    assert 'Same source/destination pair' in first.related_alerts[0].relationship_reasons
    body={'requestId':str(uuid4()),'expectedRevision':1,'reason':'SYNTHETIC manually reviewed relationship','operationalAlertRef':str(refs[0])}
    path=f'/api/v2/tier2/cases/{case.case_ref}/alerts'
    linked=api.post(path,json=body);assert linked.status_code==200,linked.text
    assert linked.json()['case']['revision']==2
    assert api.post(path,json=body).json()['replayed'] is True
    after=read_assistance(conn,case.case_ref)
    assert refs[0] not in {a.operational_alert_ref for a in after.related_alerts}
    audit=api.get(f'/api/v2/tier2/cases/{case.case_ref}/events',params={'action':'link'}).json()
    assert audit['page']['total']==1 and audit['items'][0]['eventType']=='V2_TIER2_ALERT_LINKED'
    assert audit['items'][0]['reason']==body['reason']
    stale={**body,'requestId':str(uuid4()),'operationalAlertRef':str(refs[1])}
    assert api.post(path,json=stale).status_code==409


@pytest.mark.parametrize('signature,category,expected', [
    ('Unresolved suspicious activity','Misc activity','Unknown / Needs Expert'),
    ('SSH brute force','Misc activity','authentication'),
    ('SQL injection','Web Application Attack','HTTP'),
    ('Port scan','Misc activity','target ports'),
    ('DDoS detected','Attempted Denial of Service','normalized attack category'),
    ('Informational notice: software version','Misc activity','informational or policy signal'),
])
def test_template_selection_missing_evidence_no_automatic_decisions(conn,signature,category,expected):
    alert=admit(conn,event(1,signature,category,1))
    row=conn.execute('SELECT case_ref FROM tier2_cases WHERE primary_operational_alert_id=?',(alert.id,)).fetchone()
    case=read_case(conn,row[0]) if row else escalate(conn,alert)
    before=dump(conn);result=read_assistance(conn,case.case_ref)
    assert any(expected in text for text in result.suggested_steps)
    assert any('missing' in text for text in result.suggested_steps)
    assert result.assistance_policy_version=='tier2-assistance-v1'
    assert result.suggested_steps==read_assistance(conn,case.case_ref).suggested_steps
    assert dump(conn)==before


@pytest.mark.parametrize('role',['evaluator','system_admin'])
def test_assistance_roles_and_evaluator_cannot_link(conn,api,role):
    from apps.api import auth
    alert=admit(conn);case=automatic_case(conn,alert)
    user=db.insert(conn,m.User(username=role,password_hash='synthetic',display_name=role,email=role+'@example.test',role=role))
    conn.commit();api.headers['Authorization']='Bearer '+auth.encode_token(db.get(conn,m.User,user))
    before=dump(conn)
    assert api.get(f'/api/v2/tier2/cases/{case.case_ref}/assistance').status_code==200
    assert dump(conn)==before
    if role=='evaluator':
        assert api.post(f'/api/v2/tier2/cases/{case.case_ref}/alerts',json={
            'requestId':str(uuid4()),'expectedRevision':1,'reason':'SYNTHETIC forbidden mutation',
            'operationalAlertRef':str(alert.operational_alert_ref)}).status_code==403
        assert dump(conn)==before


@pytest.mark.parametrize('rule,expected', [
    ('source','Same source IP'), ('destination','Same destination IP'),
    ('pair','Same source/destination pair'), ('category','Same normalized attack category: brute_force'),
    ('signature','Shared Suricata signature ID'), ('sensor','Same sensor: review-sensor'),
])
def test_each_configured_relationship_is_independently_explainable(conn,rule,expected):
    primary=admit(conn,event(1,'SSH brute force',severity=1));case=escalate(conn,primary)
    raw=event(2,'SSH brute force',severity=1)
    if rule not in ('source','pair'): raw['src_ip']='203.0.113.1'
    if rule not in ('destination','pair'): raw['dest_ip']='203.0.113.2'
    other=admit(conn,raw,sensor='review-sensor' if rule=='sensor' else 'other-sensor')
    policy=load_policy().model_copy(update={'relationships':(rule,)})
    classification=read_assistance(conn,case.case_ref).brief.classification_at_admission
    result=related_alerts(conn,case,classification,policy)
    assert [r.operational_alert_ref for r in result]==[other.operational_alert_ref]
    assert result[0].relationship_reasons==[expected,'Within ±24 hours of primary alert']


def test_order_relationship_count_then_priority_then_time_then_reference(conn):
    primary=admit(conn);case=automatic_case(conn,primary)
    stamp=datetime.fromisoformat(primary.occurred_at)
    candidates=[]
    # The best relationship must beat the higher urgency, then priority must beat recency.
    for flow,severity,both,minutes in [(2,4,True,0),(3,1,False,0),(4,4,False,10),(5,4,False,10)]:
        raw=event(flow,'SSH brute force',severity=severity)
        if not both: raw['dest_ip']='203.0.113.2'
        raw['timestamp']=(stamp+timedelta(minutes=minutes)).isoformat()
        candidates.append(admit(conn,raw))
    policy=load_policy().model_copy(update={'relationships':('source','destination')})
    result=related_alerts(conn,case,None,policy)
    assert [r.operational_alert_ref for r in result[:2]]==[a.operational_alert_ref for a in candidates[:2]]
    assert [str(r.operational_alert_ref) for r in result[2:]]==sorted(str(a.operational_alert_ref) for a in candidates[2:])
    assert result[0].operational_priority < result[1].operational_priority


def test_no_suggestion_from_time_only_or_shared_unknown_classification(conn):
    primary=admit(conn);case=automatic_case(conn,primary)
    raw=event(2,'Other unresolved suspicious activity','Misc activity',4)
    raw.update(src_ip='203.0.113.1',dest_ip='203.0.113.2');raw['alert']['signature_id']+=1
    admit(conn,raw,sensor='different-sensor')
    result=read_assistance(conn,case.case_ref)
    assert result.related_alerts==[]
    assert not any('potential related alerts' in step for step in result.suggested_steps)


def test_conflicting_classification_evidence_is_preserved_without_a_human_finding(conn):
    alert=admit(conn,event(1,'DDoS detected','Web Application Attack',2))
    case=automatic_case(conn,alert);before=dump(conn)
    result=read_assistance(conn,case.case_ref)
    classification=result.brief.classification_at_admission
    assert classification.status=='conflict'
    assert set(classification.conflicting_categories)=={'ddos','web_attack'}
    assert classification.matches and classification.reasons
    assert conn.execute("SELECT count(*) FROM tier2_case_events WHERE action='finding'").fetchone()[0]==0
    assert dump(conn)==before


def test_historical_case_without_system_classification_and_unadmitted_alerts_are_safe(database,candidate):
    from contextlib import closing
    from packages.detection.tier2_cases import create_case
    from packages.detection.adapters.operational_v2 import materialize_source
    with closing(db.connect(database)) as connection:
        alert,actor=candidate
        case=create_case(connection,alert.operational_alert_ref,actor_id=actor,
            request=creation(connection,candidate)).case
        materialize_source(connection,'external_nids_alert',2)  # staged, never admitted/routed
        before=dump(connection)
        result=read_assistance(connection,case.case_ref)
        assert result.brief.classification_at_admission is None
        assert result.brief.system_routing_at_admission is None
        assert result.related_alerts==[]
        assert any('historical case' in message for message in result.brief.uncertainties)
        assert dump(connection)==before
