"""Correlated evidence, deterministic classification and atomic system routing boundaries."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record, bundle_for
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.attack_classification import classify, load_classification_policy
from packages.detection.context_store import collect_fact, FactRequest
from packages.detection.external_admission import review_eligibility, admit_external, EligibilityRequest, AdmissionRequest
from packages.detection.system_routing import evaluate_system_route
from packages.detection.triage_policy import TriageContext
from packages.detection.routing import state_version
from packages.detection.tier2_cases import read_case
from packages.detection.tier2_escalation import EscalateCaseRequest, escalate_case

FIXTURE = Path(__file__).parent / 'fixtures/suricata-correlated.json'


@pytest.fixture
def conn():
    connection = db.connect(':memory:')
    db.create_schema(connection)
    db.insert(connection, m.User(username='analyst', password_hash='fixture', display_name='Analyst',
        email='analyst@example.test', role='security_analyst'))
    connection.commit()
    yield connection
    connection.close()


def records():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def stage(conn, tmp_path, events, sensor='sensor-a'):
    path = tmp_path / 'eve.json'
    path.write_text(json.dumps(events), encoding='utf-8')
    return stage_file(conn, path, sensor, capture_scope="correlation-test")


def admission(conn, source=1):
    review = review_eligibility(conn,source,actor_id=1,request=EligibilityRequest(
        request_id=uuid4(),expected_review_id=None,decision='accepted',reason='Synthetic evidence reviewed'))
    request = AdmissionRequest(request_id=uuid4(),expected_review_id=review['id'],reason='Synthetic admission')
    return request


def admit(conn, source=1):
    request = admission(conn,source)
    result,_ = admit_external(conn,source,actor_id=1,request=request)
    return result,request


def test_all_eve_types_flow_transactions_and_no_detection_without_alert(conn,tmp_path):
    events = records()[:3]
    for tx,kind in enumerate(('http','dns','tls','fileinfo','anomaly')):
        events.append({**events[0], 'event_type':kind, kind:{'detail':'synthetic'},'tx_id':tx})
        events[-1].pop('alert')
    result=stage(conn,tmp_path,events)
    assert result.staged==1 and result.preserved==8
    canonical=json.loads(conn.execute('SELECT canonical_snapshot FROM external_alert_inbox').fetchone()[0])
    bundle=canonical['structuredEvidence']['suricataBundle']
    assert set(bundle['evidenceTypes'])=={'alert','flow','ssh','http','dns','tls','fileinfo','anomaly'}
    assert len(bundle['transactionRecords'])==5
    assert all(len(refs)==1 for refs in bundle['transactionRecords'].values())
    assert canonical['originalDetectorFields']['events']==[r['raw'] for r in bundle['records']]
    assert all(r['timestamp']==events[0]['timestamp'] and r['sensorId']=='sensor-a' for r in bundle['records'])
    assert canonical['confidence'] is None
    assert stage(conn,tmp_path,[{**events[1],'flow_id':123}]).staged==0
    assert stage(conn,tmp_path,[{'event_type':'stats','stats':{}}]).skipped==1


def test_identity_order_sensor_separation_missing_flow_and_native_priorities(conn,tmp_path):
    events=records()[3:6]
    stage(conn,tmp_path,events)
    assert stage(conn,tmp_path,list(reversed(events))).duplicate==1
    assert stage(conn,tmp_path,events,'sensor-b').staged==1
    noflow=[{k:v for k,v in e.items() if k!='flow_id'} for e in events]
    assert stage(conn,tmp_path,noflow).staged==2
    canonical=build_bundle([parse_record(e,'sensor-a') for e in events])
    bundle=bundle_for(canonical)
    assert canonical.detector_severity==1 and len(bundle.related_signatures)==2
    assert {s.native_severity for s in bundle.related_signatures}=={1,3}
    assert canonical==build_bundle([parse_record(e,'sensor-a') for e in reversed(events)])
    with pytest.raises(ValueError,match='one safe'):
        build_bundle([parse_record(events[0],'a'),parse_record(events[1],'b')])
    assert conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0]==4


def test_prior_evidence_can_join_before_seal_and_late_changes_fail_atomically(conn,tmp_path):
    events=records()[:3]
    assert stage(conn,tmp_path,events[1:]).staged==0
    assert stage(conn,tmp_path,events[:1]).staged==1
    before=[tuple(r) for r in conn.execute('SELECT * FROM suricata_eve_records')]
    late={**events[1],'flow':{'pkts_toserver':100}}
    with pytest.raises(ValueError,match='sealed'):
        stage(conn,tmp_path,[late])
    assert [tuple(r) for r in conn.execute('SELECT * FROM suricata_eve_records')]==before


@pytest.mark.parametrize('kind',['alert','flow','http','dns','tls','ssh','fileinfo','anomaly'])
def test_ground_truth_rejected_recursively_for_every_supported_type(conn,tmp_path,kind):
    raw=records()[0]
    raw['event_type']=kind
    if kind!='alert':raw[kind]={'nested':[{'groundTruthLabel':'attack'}]}
    else:raw['alert']['metadata']={'nested':[{'attack_type':'attack'}]}
    assert stage(conn,tmp_path,[raw]).invalid==1
    assert conn.execute('SELECT count(*) FROM suricata_eve_records').fetchone()[0]==0


@pytest.mark.parametrize('table',['suricata_eve_records','external_alert_inbox','operational_system_routing','operational_routing_audit','tier2_cases','tier2_case_events'])
def test_immutable_records_even_without_recursive_triggers(conn,tmp_path,table):
    stage(conn,tmp_path,records()[6:8]); admit(conn)
    conn.execute('PRAGMA recursive_triggers=OFF')
    rows=[tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]
    for sql in (f'DELETE FROM {table}', f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
        with pytest.raises(sqlite3.IntegrityError): conn.execute(sql)
        conn.rollback()
    column='classification' if table=='operational_system_routing' else 'raw_snapshot' if table=='suricata_eve_records' else 'created_at' if table!='external_alert_inbox' else 'imported_at'
    with pytest.raises(sqlite3.IntegrityError):conn.execute(f'UPDATE {table} SET {column}={column}')
    conn.rollback()
    assert rows==[tuple(r) for r in conn.execute(f'SELECT * FROM {table}')]


@pytest.mark.parametrize('name,category', [('SSH brute force','brute_force'),('botnet command and control','botnet_c2'),
    ('denial of service','dos'),('distributed denial of service','ddos'),('SQL injection','web_attack'),
    ('data exfiltration','infiltration'),('port scan','reconnaissance_port_scan'),('malware exploit','malware_exploit'),
    ('credential theft','other_known_attack'),('unresolved pattern','unknown_needs_expert')])
def test_explicit_classification(name,category):
    raw=records()[0];raw['alert']['signature']=name
    bundle=bundle_for(build_bundle([parse_record(raw,'sensor')]))
    result=classify(bundle)
    assert result.attack_category==category and result.reasons
    assert result.policy_version==load_classification_policy().version
    assert 'confidence' not in result.model_dump()
    assert bundle.related_signatures[0].native_category=='Attempted Information Leak'


def test_conflicting_related_signatures_require_expert():
    events=records()[3:5];events[0]['alert']['signature']='Possible SSH scan'
    result=classify(bundle_for(build_bundle([parse_record(e,'s') for e in events])))
    assert result.status=='conflict' and result.attack_category=='unknown_needs_expert'
    assert 'Conflicting' in result.reasons[-1]


def test_routine_system_route_same_flow_signatures_not_campaign_and_severity_alone(conn,tmp_path):
    stage(conn,tmp_path,records()[3:6]);result,request=admit(conn)
    state=read_triage(conn,result['operational_alert_id'])
    assert state.handling_route=='tier1_review' and state.operational_priority==85 and state.priority_band=='P1'
    assert not state.tier2_recommended
    audit=conn.execute('SELECT * FROM operational_routing_audit').fetchone()
    assert audit['actor_id'] is None and audit['decision_source']=='system_policy'
    assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]==0
    assert admit_external(conn,1,actor_id=1,request=request)[1]
    assert conn.execute('SELECT count(*) FROM operational_routing_audit').fetchone()[0]==1


def test_unknown_auto_case_system_attribution_no_candidate_and_manual_override(conn,tmp_path):
    stage(conn,tmp_path,records()[6:8]); result,_=admit(conn)
    state=read_triage(conn,result['operational_alert_id'])
    assert (state.handling_route,state.workflow_stage)==('tier2_case','investigation')
    system=conn.execute('SELECT * FROM operational_system_routing').fetchone()
    assert json.loads(system['routing_decision'])['routeClass']=='EXPERT_REVIEW_REQUIRED'
    case=read_case(conn,system['case_ref'])
    assert case.owner_actor_id is None and case.created_by_actor_id is None and case.decision_source=='system_policy'
    assert case.snapshot.routing_decision.actor_id is None
    assert case.snapshot.routing_decision.after_state==state
    assert 'tier2_candidate' not in conn.execute('SELECT before_state || after_state FROM operational_routing_audit').fetchone()[0]
    stage(conn,tmp_path,records()[-1:]);manual,_=admit(conn,2)
    alert=read_projection(conn,manual['operational_alert_id']); before=read_triage(conn,alert.id)
    command=EscalateCaseRequest(request_id=uuid4(),action='manual_escalate',expected_state_version=state_version(before),reason='Analyst investigation requires Tier 2')
    escalated=escalate_case(conn,alert.operational_alert_ref,actor_id=1,request=command)
    assert escalated.case.created_by_actor_id==1 and escalated.case.decision_source=='analyst'
    assert escalated.case.snapshot.routing_decision.actor_id==1


def test_trusted_critical_context_routes_atomically(conn,tmp_path):
    now=m.utc_now()
    collect_fact(conn,actor_id=1,request=FactRequest(request_id=uuid4(),expected_revision=0,
        subject_type='ip',subject_value='198.51.100.99',context_key='assetCriticality',value='critical',
        observed_at=now-timedelta(seconds=1),valid_from=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1),
        reason='Synthetic critical asset',source_reference='synthetic:asset-register'))
    stage(conn,tmp_path,records()[8:10]);result,_=admit(conn)
    assert read_triage(conn,result['operational_alert_id']).handling_route=='tier2_case'
    decision=json.loads(conn.execute('SELECT routing_decision FROM operational_system_routing').fetchone()[0])
    assert decision['routeClass']=='CRITICAL_ESCALATION'


@pytest.mark.parametrize('table',['operational_triage_policy_audit','operational_routing_audit','tier2_cases','tier2_case_state','tier2_case_events','operational_system_routing','external_operational_admission'])
def test_auto_case_every_failure_rolls_back_and_retry_recovers(conn,tmp_path,table):
    stage(conn,tmp_path,records()[6:8]);request=admission(conn)
    conn.execute(f"CREATE TRIGGER inject_failure BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError,match='injected'):
        admit_external(conn,1,actor_id=1,request=request)
    for name in ('operational_alerts_v2','operational_triage_state_v2','operational_triage_policy_audit','operational_routing_audit','tier2_cases','tier2_case_state','tier2_case_events','operational_system_routing','external_operational_admission'):
        assert conn.execute(f'SELECT count(*) FROM {name}').fetchone()[0]==0
    conn.execute('DROP TRIGGER inject_failure');conn.commit()
    admit_external(conn,1,actor_id=1,request=request)
    assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]==1


@pytest.mark.parametrize('context,expected',[(TriageContext(),'ROUTINE_REVIEW'),
    (TriageContext(confirmed_malicious=True),'ROUTINE_REVIEW'),(TriageContext(response_required=True),'ROUTINE_REVIEW'),
    (TriageContext(confirmed_malicious=True,response_required=True),'CRITICAL_ESCALATION'),
    (TriageContext(repeated_campaign=True,correlated_alert_count=2),'ROUTINE_REVIEW'),
    (TriageContext(repeated_campaign=True,correlated_alert_count=3),'CRITICAL_ESCALATION'),
    (TriageContext(unresolved_by_tier1=True),'EXPERT_REVIEW_REQUIRED')])
def test_guarded_rules_unknown_is_not_true(context,expected):
    classification=classify(bundle_for(build_bundle([parse_record(records()[0],'s')])))
    assert evaluate_system_route(classification,85,context).route_class==expected


def test_migration_fourteen_preserves_populated_history_and_constraints(tmp_path,monkeypatch):
    from legacy_suricata_fixture import stage_file as historical_stage
    migrations=db.MIGRATIONS[:14]
    monkeypatch.setattr(db,'MIGRATIONS',migrations)
    connection=db.connect(tmp_path/'historical.db')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(db,'MIGRATIONS',migrations[:13])
            db.create_schema(connection)
        db.insert(connection,m.User(username='analyst',password_hash='fixture',display_name='Analyst',
            email='analyst@example.test',role='security_analyst'));connection.commit()
        historical_stage(connection,Path(__file__).parent/'fixtures/suricata-alerts.json','historic')
        result,_=admit(connection)
        alert=read_projection(connection,result['operational_alert_id']);state=read_triage(connection,alert.id)
        # Schema 13 predates the system classification table. Reproduce that historical
        # projection while constructing the fixture; use the real reader after upgrade.
        with monkeypatch.context() as patch:
            patch.setattr('packages.detection.tier2_cases.system_classification',lambda *args:None)
            created=escalate_case(connection,alert.operational_alert_ref,actor_id=1,request=EscalateCaseRequest(
                request_id=uuid4(),expected_state_version=state_version(state),reason='Historical manual escalation'))
        tables=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'")]
        before={table:([r[1] for r in connection.execute(f'PRAGMA table_info({table})')],
            [tuple(r) for r in connection.execute(f'SELECT * FROM {table}')]) for table in tables}
        assert db.migrate(connection)==[14] and db.migrate(connection)==[]
        for table,(columns,rows) in before.items():
            assert [tuple(r) for r in connection.execute(f"SELECT {','.join(columns)} FROM {table}")]==rows
        assert read_case(connection,created.case.case_ref)==created.case
        assert connection.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for table in ('tier2_cases','tier2_case_events','operational_routing_audit','operational_triage_policy_audit'):
            assert connection.execute(f'SELECT decision_source FROM {table}').fetchone()[0]=='analyst'
            with pytest.raises(sqlite3.IntegrityError):connection.execute(f'DELETE FROM {table}')
            connection.rollback()
    finally: connection.close()


def test_failed_rebuild_restores_foreign_keys_schema_and_data(tmp_path,monkeypatch):
    migrations=db.MIGRATIONS[:14]
    monkeypatch.setattr(db,'MIGRATIONS',migrations)
    connection=db.connect(tmp_path/'rollback.db')
    try:
        monkeypatch.setattr(db,'MIGRATIONS',migrations[:13]);db.create_schema(connection)
        before='\n'.join(connection.iterdump())
        broken=migrations[:13]+((14,'injected failure',migrations[-1][2]+'\nSELECT * FROM nonexistent_migration_table;\n'),)
        monkeypatch.setattr(db,'MIGRATIONS',broken)
        with pytest.raises(sqlite3.OperationalError):db.migrate(connection)
        assert connection.execute('PRAGMA user_version').fetchone()[0]==13
        assert connection.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert '\n'.join(connection.iterdump())==before
    finally:connection.close()


def test_context_cannot_be_injected_and_config_version_cannot_drift(conn,tmp_path,monkeypatch):
    from packages.detection import system_routing
    from packages.detection.external_admission import AdmissionConflict
    stage(conn,tmp_path,records()[:3]);request=admission(conn)
    with pytest.raises(AdmissionConflict,match='persisted trusted facts'):
        admit_external(conn,1,actor_id=1,request=request,trusted_context=TriageContext(confirmed_malicious=True,response_required=True))
    assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]==0
    admit_external(conn,1,actor_id=1,request=request)
    stage(conn,tmp_path,records()[-1:]);request=admission(conn,2)
    changed=system_routing.load_system_routing_policy().model_copy(update={'high_priority_threshold':99})
    monkeypatch.setattr(system_routing,'load_system_routing_policy',lambda:changed)
    with pytest.raises(ValueError,match='new policy version'):
        admit_external(conn,2,actor_id=1,request=request)
    assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]==1
