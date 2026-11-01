"""Review remediation: real commands, boundary failures and read-only projections."""
from copy import deepcopy
from datetime import timedelta
import json
import sqlite3
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from apps.api import auth, operational_queue
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record, bundle_for
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.attack_classification import classify, ClassificationPolicy, load_classification_policy
from packages.detection.context_store import collect_fact, FactRequest, revision
from packages.detection import selective_review as review, triage_memory as memory
from packages.detection.routing import state_version
from pre_freeze_fixture import event, stage, admit_all, review_scenario, review_request


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path/'review.db')
    db.create_schema(connection)
    db.insert(connection, m.User(username='reviewer', password_hash='synthetic', display_name='Reviewer',
        email='reviewer@example.test', role='security_analyst'))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def api(conn):
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    with TestClient(create_app(path)) as client:
        client.headers['Authorization'] = 'Bearer ' + auth.encode_token(db.get(conn, m.User, 1))
        yield client


def classified(*pairs):
    records = []
    for i, (signature, category) in enumerate(pairs):
        raw = event(signature=signature, category=category);raw['alert']['signature_id'] += i
        records.append(parse_record(raw, 'sensor', 'capture'))
    return classify(bundle_for(build_bundle(records)))


@pytest.mark.parametrize('pairs,expected,status', [
    ([('SSH brute force','Misc activity')], 'brute_force','mapped'),
    ([('DDoS detected','Attempted Denial of Service')], 'ddos','mapped'),
    ([('C2 beacon detected','A Network Trojan was detected')], 'botnet_c2','mapped'),
    ([('DDoS detected','Attempted Denial of Service'),('Denial of service','Misc activity')], 'ddos','mapped'),
    ([('DDoS detected','Misc activity'),('Unmapped support','Misc activity')], 'ddos','mapped'),
    ([('DDoS detected','Misc activity'),('SQL injection','Web Application Attack')], 'unknown_needs_expert','conflict'),
    ([('Informational notice: software version','Misc activity')], None,'informational_policy_signal'),
    ([('Informational notification: software version','Not Suspicious Traffic')], None,'informational_policy_signal'),
    ([('Policy event: application usage','Potential Corporate Privacy Violation')], None,'informational_policy_signal'),
    ([('ET POLICY Application usage','Potential Corporate Privacy Violation')], 'unknown_needs_expert','unmapped'),
    ([('ET POLICY Suspicious application behavior','Potential Corporate Privacy Violation')], 'unknown_needs_expert','unmapped'),
    ([('Protocol notice: negotiation','Generic Protocol Command Decode')], None,'informational_policy_signal'),
    ([('Informational notice: suspicious unknown attack','Misc activity')], 'unknown_needs_expert','unmapped'),
    ([('Generic activity','Misc activity')], 'unknown_needs_expert','unmapped'),
    ([('Informational notice','Misc activity'),('Unresolved suspicious activity','Misc activity')], 'unknown_needs_expert','unmapped'),
])
def test_classification_rules(pairs, expected, status):
    result = classified(*pairs)
    assert (result.attack_category,result.status)==(expected,status)
    assert result.policy_version=='suricata-classification-v3'
    reverse = classified(*reversed(pairs))
    assert (result.attack_category, result.status) == (reverse.attack_category, reverse.status)
    if expected not in ('unknown_needs_expert', None): assert result.matches
    if status=='conflict': assert set(result.conflicting_categories)=={'ddos','web_attack'}


def test_specificity_is_configured_acyclic_and_preserves_matches():
    result=classified(('C2 beacon detected','A Network Trojan was detected'),('Malware detected','Misc activity'))
    assert result.attack_category=='botnet_c2'
    assert {match.category for match in result.matches}=={'botnet_c2','malware_exploit'}
    policy=load_classification_policy().model_dump()
    policy['compatibility']=(*policy['compatibility'],{'specific':'dos','broader':'ddos'})
    with pytest.raises(ValueError,match='acyclic'): ClassificationPolicy.model_validate(policy)


def test_bulk_informationals_and_mandatory_unknown_cases(conn):
    signals=[event(i+1, 'Informational notice: software version', 'Misc activity', (i%4)+1) for i in range(53)]
    signals += [event(100+i, 'Unresolved suspicious attack-like activity', 'Misc activity', 4) for i in range(4)]
    signals += [event(200,'DDoS detected','Web Application Attack',4)]
    stage(conn,signals);alerts=admit_all(conn)
    for alert in alerts:
        saved=conn.execute('SELECT * FROM operational_system_routing WHERE operational_alert_id=?',(alert.id,)).fetchone()
        classification=json.loads(saved['classification']);route=json.loads(saved['routing_decision']);state=read_triage(conn,alert.id)
        if classification['attackCategory']=='unknown_needs_expert':
            assert route['routeClass']=='EXPERT_REVIEW_REQUIRED' and state.handling_route=='tier2_case' and state.workflow_stage=='investigation'
            assert state.decision_source=='system_policy' and not state.tier2_recommended
            case=conn.execute('SELECT * FROM tier2_cases WHERE case_ref=?',(saved['case_ref'],)).fetchone()
            assert case and case['created_by_actor_id'] is None and case['owner_actor_id'] is None and case['decision_source']=='system_policy'
        else:
            assert classification['status']=='informational_policy_signal' and classification['attackCategory'] is None
            assert state.handling_route=='tier1_review' and saved['case_ref'] is None
    assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]==5
    assert not conn.execute("SELECT 1 FROM operational_triage_state_v2 WHERE handling_route='tier2_candidate'").fetchone()


def test_capture_identity_reimport_and_provenance(conn):
    raw=event()
    assert stage(conn,[raw,deepcopy(raw)]).staged==1
    assert stage(conn,[raw]).duplicate==1
    assert stage(conn,[raw],scope='capture-b').staged==1
    assert stage(conn,[raw],sensor='sensor-b').staged==1
    assert conn.execute('SELECT count(*) FROM suricata_eve_records').fetchone()[0]==3
    for sensor,scope in [('other','a'),('s','b')]:
        with pytest.raises(ValueError,match='one safe'):
            build_bundle([parse_record(raw,'s','a'),parse_record(raw,sensor,scope)])
    a=event(10);a.pop('flow_id');b=deepcopy(a);b['timestamp']='2026-10-03T00:00:00Z'
    assert stage(conn,[a,b],scope='no-flow').staged==2


@pytest.mark.parametrize('change',[{'dest_ip':'203.0.113.254'},{'dest_port':999},{'proto':'UDP'},{'flow':{'start':'2026-01-02T00:00:00Z'}}])
def test_flow_contradiction_fails_entire_import(conn,change):
    a=event();a['flow']={'start':'2026-01-01T00:00:00Z'};b=deepcopy(a);b.update(change)
    with pytest.raises(ValueError,match='contradictory'):stage(conn,[a,b])
    assert conn.execute('SELECT count(*) FROM suricata_eve_records').fetchone()[0]==0
    assert conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0]==0


def test_bidirectional_and_partial_evidence_remain_valid(conn):
    a=event();b=deepcopy(a);b.update(src_ip=a['dest_ip'],dest_ip=a['src_ip'],src_port=a['dest_port'],dest_port=a['src_port'])
    evidence={'event_type':'flow','flow_id':a['flow_id'],'timestamp':a['timestamp'],'flow':{'pkts_toserver':2}}
    assert stage(conn,[a,b,evidence]).staged==1


def test_partial_anchors_require_one_globally_consistent_flow(conn):
    records = [{'event_type':'flow','flow_id':123,'timestamp':'2026-10-01T00:00:00Z',
                'src_ip':ip,'flow':{}} for ip in ('192.0.2.1','192.0.2.2','192.0.2.3')]
    assert stage(conn,records[:2]).preserved==2
    # Every pair can be opposite directions; three distinct endpoints cannot be one flow.
    with pytest.raises(ValueError,match='contradictory'):stage(conn,records[2:])
    assert conn.execute('SELECT count(*) FROM suricata_eve_records').fetchone()[0]==2


def assert_attention(conn,api,alerts,deferred):
    summary=api.get('/api/v2/alerts/summary').json()
    assert (summary['totalAlerts'],summary['noImmediateReview'],summary['reviewRequired'])==(6,deferred,6-deferred)
    assert api.get('/api/v2/alerts',params={'reviewDisposition':'no_immediate_review','limit':1}).json()['page']['total']==deferred
    assert api.get('/api/v2/alerts',params={'reviewRequired':True,'limit':1}).json()['page']['total']==6-deferred
    for alert in alerts:
        ref=alert.operational_alert_ref
        detail=api.get(f'/api/v2/alerts/{ref}/triage-state').json()
        selective=api.get(f'/api/v2/alerts/{ref}/selective-review').json()
        assert detail['effectiveReview']['disposition']==selective['disposition']
        assert detail['effectiveReview']['reviewRequired']==(selective['disposition']!='no_immediate_review')
        assert detail['state']['handlingRoute']=='tier1_review' and detail['state']['reviewRequired'] is True


@pytest.mark.parametrize('withdrawal',['override','context_conflict','context_expiry','memory_expiry','memory_conflict'])
def test_effective_attention_real_services_and_readonly(conn,api,monkeypatch,withdrawal):
    alerts=review_scenario(conn);assert_attention(conn,api,alerts,3)
    target=alerts[3];now=m.utc_now()
    if withdrawal=='override':
        current=review.read_review(conn,target.operational_alert_ref)
        review.decide_review(conn,target.operational_alert_ref,actor_id=1,action='require_review',request=review.ReviewCommand(
            request_id=uuid4(),expected_version=current.version,reason='SYNTHETIC recall'))
        expected=2
    elif withdrawal=='context_conflict':
        collect_fact(conn,actor_id=1,request=FactRequest(request_id=uuid4(),expected_revision=revision(conn),subject_type='operational_alert',
            subject_value=str(target.operational_alert_ref),context_key='responseRequired',value=True,observed_at=now-timedelta(seconds=1),
            valid_from=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1),reason='SYNTHETIC conflicting context',source_reference='review:conflict'))
        expected=2
    elif withdrawal=='memory_conflict':
        memory.record_review(conn,target.operational_alert_ref,actor_id=1,request=review_request(conn,target,'confirmed_malicious'));expected=0
    else:
        monkeypatch.setattr(m,'utc_now',lambda:now+timedelta(hours=5) if withdrawal=='context_expiry' else now+timedelta(days=31));expected=0
    before='\n'.join(conn.iterdump());assert_attention(conn,api,alerts,expected)
    assert '\n'.join(conn.iterdump())==before


def test_current_candidate_api_blocked_and_manual_override_atomic(conn,api):
    stage(conn,[event()]);alert=admit_all(conn)[0];ref=alert.operational_alert_ref
    view=api.get(f'/api/v2/alerts/{ref}/triage-state').json()
    body=dict(requestId=str(uuid4()),expectedStateVersion=view['stateVersion'],reason='SYNTHETIC manual investigation')
    before='\n'.join(conn.iterdump())
    assert api.post(f'/api/v2/alerts/{ref}/tier2/escalate',json=body).status_code==409
    assert '\n'.join(conn.iterdump())==before
    created=api.post(f'/api/v2/alerts/{ref}/tier2/escalate-case',json=body)
    assert created.status_code==200,created.text
    assert created.json()['view']['state']['handlingRoute']=='tier2_case'
    assert created.json()['case']['createdByActorId']==1 and created.json()['case']['decisionSource']=='analyst'
    assert api.post(f'/api/v2/alerts/{ref}/tier2/escalate-case',json=body).json()['replayed']


def test_migration_fifteen_preserves_unscoped_history_and_rolls_back(tmp_path,monkeypatch):
    from packages.detection.adapters.staging import inbox_row
    from packages.detection.adapters.admission_policy import load_admission_policy
    from packages.detection.external_admission import validate_source
    migrations=db.MIGRATIONS[:15]
    conn=db.connect(tmp_path/'migration.db')
    try:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:14]);db.create_schema(conn)
        raw=event();canonical=build_bundle([parse_record(raw,'historical-sensor')])
        row=inbox_row(canonical,load_admission_policy().decide(canonical),'historical-sensor')
        with conn:
            conn.execute(f"INSERT INTO external_alert_inbox ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",list(row.values()))
            conn.execute('INSERT INTO suricata_eve_records(sensor_id,source_record_ref,event_type,flow_id,tx_id,timestamp,raw_snapshot,imported_at) VALUES (?,?,?,?,?,?,?,?)',
                ('historical-sensor',parse_record(raw,'historical-sensor').source_record_ref,'alert',str(raw['flow_id']),None,raw['timestamp'],json.dumps(raw),'2026-10-01T00:00:00Z'))
        before='\n'.join(conn.iterdump())
        from pre_freeze_fixture import Events
        from packages.detection.adapters.staging import stage_file
        assert stage_file(conn,Events([raw]),'historical-sensor',capture_scope='new-capture',dry_run=True).staged==1
        assert '\n'.join(conn.iterdump())==before
        broken=migrations[:14]+((15,'injected',migrations[14][2]+'\nSELECT * FROM missing_migration_table;\n'),)
        monkeypatch.setattr(db,'MIGRATIONS',broken)
        with pytest.raises(sqlite3.OperationalError):db.migrate(conn)
        assert '\n'.join(conn.iterdump())==before and conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
        snapshot=conn.execute('SELECT canonical_snapshot FROM external_alert_inbox').fetchone()[0]
        raw_before=tuple(conn.execute('SELECT * FROM suricata_eve_records').fetchone())
        monkeypatch.setattr(db,'MIGRATIONS',migrations)
        assert db.migrate(conn)==[15] and db.migrate(conn)==[]
        assert conn.execute('SELECT canonical_snapshot FROM external_alert_inbox').fetchone()[0]==snapshot
        raw_after=dict(conn.execute('SELECT * FROM suricata_eve_records').fetchone());assert raw_after.pop('capture_scope') is None
        assert tuple(raw_after.values())==raw_before
        validate_source(dict(conn.execute('SELECT * FROM external_alert_inbox').fetchone()))
        assert stage(conn,[raw],scope='new-capture',sensor='historical-sensor').staged==1
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not conn.execute('PRAGMA foreign_key_check').fetchall()
        for statement in ('DELETE FROM suricata_eve_records','UPDATE suricata_eve_records SET capture_scope=capture_scope','INSERT OR REPLACE INTO suricata_eve_records SELECT * FROM suricata_eve_records'):
            with pytest.raises(sqlite3.IntegrityError):conn.execute(statement)
            conn.rollback()
    finally:conn.close()


def test_capture_boundary_requires_stable_scope_and_rejects_truth(conn):
    for scope in ('','  ',' scope','scope ','x'*201):
        with pytest.raises(ValueError):stage(conn,[event()],scope=scope)
    raw=event();raw['capture_metadata']={'nested':[{'groundTruthLabel':'attack'}]}
    assert stage(conn,[raw],scope='valid-opaque-scope').invalid==1
    assert conn.execute('SELECT count(*) FROM suricata_eve_records').fetchone()[0]==0


def test_earlier_evidence_is_capture_scoped_and_guarded(conn):
    raw=event();flow={**raw,'event_type':'flow','flow':{'pkts_toserver':1}};flow.pop('alert')
    assert stage(conn,[flow],scope='capture-a').staged==0
    changed=deepcopy(raw);changed['dest_ip']='203.0.113.99'
    assert stage(conn,[changed],scope='capture-b').staged==1
    with pytest.raises(ValueError,match='contradictory'):stage(conn,[changed],scope='capture-a')
    assert stage(conn,[raw],scope='capture-a').staged==1
