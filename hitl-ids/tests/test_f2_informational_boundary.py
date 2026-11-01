"""V3 positive allowlist, independent-review counterexamples and safe fallback."""
import json
import re
from pathlib import Path
import pytest
from test_pre_freeze_review_fixes import conn, classified
from pre_freeze_fixture import event, stage, admit_all
from packages.detection.attack_classification import load_classification_policy, classify
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record, bundle_for

UNKNOWN = [
    ('ET POLICY Possible ransomware communication','Misc activity'),
    ('ET POLICY Credential harvesting detected','Potential Corporate Privacy Violation'),
    ('ET POLICY Unauthorized remote access detected','Misc activity'),
    ('ET POLICY Opaque channel rendezvous','Misc activity'),
    ('ET POLICY Uncatalogued session marker','Misc activity'),
    ('ET POLICY Novel exchange observed','Misc activity'),
    ('Policy notice: opaque channel rendezvous','Misc activity'),
    ('Informational notice: opaque channel rendezvous','Misc activity'),
    ('Protocol notice: opaque channel rendezvous','Misc activity'),
]
POSITIVE = [
    ('Informational notice','Misc activity'),
    ('Informational notification: software version','Not Suspicious Traffic'),
    ('Policy event: application usage','Potential Corporate Privacy Violation'),
    ('Policy notice','Misc activity'),
    ('Protocol notice: negotiation','Generic Protocol Command Decode'),
    ('Protocol informational event','Misc activity'),
]

@pytest.mark.parametrize('pair',UNKNOWN)
def test_unrecognized_text_is_unknown_even_outside_veto(pair):
    assert not re.search(load_classification_policy().informational_attack_veto,pair[0],re.I)
    result=classified(pair)
    assert (result.attack_category,result.status)==('unknown_needs_expert','unmapped')

@pytest.mark.parametrize('pair',POSITIVE)
def test_explicit_positive_controls_all_severities(pair):
    for severity in range(1,5):
        raw=event(signature=pair[0],category=pair[1],severity=severity)
        result=classify(bundle_for(build_bundle([parse_record(raw,'sensor','capture')])))
        assert result.attack_category is None and result.status=='informational_policy_signal'
        assert result.matches and result.policy_version=='suricata-classification-v3'

@pytest.mark.parametrize('pairs,category,status',[
    ([POSITIVE[0],POSITIVE[2]],None,'informational_policy_signal'),
    ([POSITIVE[0],UNKNOWN[3]],'unknown_needs_expert','unmapped'),
    ([POSITIVE[0],('ET POLICY SQL injection','Misc activity')],'web_attack','mapped'),
    ([POSITIVE[0],('DDoS detected','Web Application Attack')],'unknown_needs_expert','conflict'),
])
def test_mixed_signature_bundles(pairs,category,status):
    result=classified(*pairs)
    assert (result.attack_category,result.status)==(category,status)

def test_v2_remains_loadable_and_history_is_not_reclassified(conn,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'config/suricata-classification-v2.json'
    old=load_classification_policy(path)
    raw=event(signature=UNKNOWN[0][0],category=UNKNOWN[0][1])
    bundle=bundle_for(build_bundle([parse_record(raw,'s','c')]))
    assert classify(bundle,old).status=='informational_policy_signal'
    assert classify(bundle).status=='unmapped'
    from packages.detection import system_routing
    stage(conn,[raw])
    with monkeypatch.context() as patch:
        patch.setattr(system_routing,'load_classification_policy',lambda:old)
        admit_all(conn)
    snapshot=conn.execute('SELECT classification FROM operational_system_routing').fetchone()[0]
    assert json.loads(snapshot)['policyVersion']=='suricata-classification-v2'
    assert json.loads(snapshot)['status']=='informational_policy_signal'
    stage(conn,[event(2,*UNKNOWN[0])]);admit_all(conn)
    assert conn.execute('SELECT classification FROM operational_system_routing').fetchone()[0]==snapshot
    current=json.loads(conn.execute('SELECT classification FROM operational_system_routing ORDER BY operational_alert_id DESC LIMIT 1').fetchone()[0])
    assert current['policyVersion']=='suricata-classification-v3' and current['status']=='unmapped'

def test_v3_positive_patterns_have_no_arbitrary_suffix():
    # A policy author changing this finite vocabulary must review this safety boundary.
    for rule in load_classification_policy().informational_rules:
        assert '.*' not in rule.signature_pattern and '.+' not in rule.signature_pattern

def test_bulk_approved_and_unknown_create_only_required_expert_cases(conn):
    positives=[event(i+1,*POSITIVE[i%len(POSITIVE)],severity=i%4+1) for i in range(54)]
    unknowns=[event(100+i,*pair,severity=4) for i,pair in enumerate(UNKNOWN)]
    stage(conn,positives+unknowns);alerts=admit_all(conn)
    cases=0
    for alert in alerts:
        row=conn.execute('SELECT * FROM operational_system_routing WHERE operational_alert_id=?',(alert.id,)).fetchone()
        classification=json.loads(row['classification']);route=json.loads(row['routing_decision'])
        if classification['attackCategory']=='unknown_needs_expert':
            cases+=1
            assert route['route']=='tier2_case' and route['routeClass']=='EXPERT_REVIEW_REQUIRED'
            case=conn.execute('SELECT * FROM tier2_cases WHERE case_ref=?',(row['case_ref'],)).fetchone()
            assert case and case['decision_source']=='system_policy'
            assert case['created_by_actor_id'] is None and case['owner_actor_id'] is None
        else:
            assert classification['status']=='informational_policy_signal'
            assert route['route']=='tier1_review' and row['case_ref'] is None
    assert cases==len(UNKNOWN)==9
    assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]==9
