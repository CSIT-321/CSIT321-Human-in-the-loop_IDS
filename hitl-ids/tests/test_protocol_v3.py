"""Protocol-only preflight. Never executes the final workload against a product database."""
import copy
import json
from pathlib import Path
import shutil
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from protocol_v3.common import BUNDLE, OUTCOMES, file_hash, read, write, digest
from protocol_v3.runner import reveal, run
from build_protocol_v3_workload import build
from validate_protocol_v3 import validate, validate_structure
from evaluate_protocol_v3 import metrics, rate

@pytest.fixture
def bundle(tmp_path):
    target=tmp_path/'bundle'; shutil.copytree(BUNDLE,target); return target

def test_reproducible_generator_and_current_contract(tmp_path):
    fresh=tmp_path/'fresh'; build(fresh)
    for p in ('workload/operational-workload.jsonl','workload/trusted-context.json','oracle/external-outcomes.json','expected/workload-structure.json'):
        assert file_hash(fresh/p)==file_hash(BUNDLE/p)
    assert validate_structure(fresh)['primary']==140

def test_frozen_generator_refuses_overwrite():
    with pytest.raises(ValueError,match='Frozen'):build(BUNDLE)

def test_frozen_manifest_and_no_runtime_dependency():
    assert validate()['alerts']==200

@pytest.mark.parametrize('field',['groundTruth','oracleOutcome','outcome','stratum'])
def test_operational_input_rejects_label_or_experiment_metadata(bundle,field):
    p=bundle/'workload/operational-workload.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
    rows[0][field]='expected_activity';p.write_text('\n'.join(json.dumps(x) for x in rows))
    with pytest.raises(ValueError,match='whitelist'):validate_structure(bundle)

def test_duplicate_alert_identity_rejected(bundle):
    p=bundle/'expected/workload-structure.json';s=read(p);s[1]['alertRef']=s[0]['alertRef'];write(p,s)
    with pytest.raises(ValueError,match='identity'):validate_structure(bundle)

def test_oracle_coverage_rejected(bundle):
    p=bundle/'oracle/external-outcomes.json';s=read(p);s.pop(next(iter(s)));write(p,s)
    with pytest.raises(ValueError,match='coverage'):validate_structure(bundle)

def test_phase_and_chronology_rejected(bundle):
    p=bundle/'expected/workload-structure.json';s=read(p);s[40]['phase']='learning';write(p,s)
    with pytest.raises(ValueError,match='split'):validate_structure(bundle)

def test_timestamp_reversal_rejected(bundle):
    p=bundle/'workload/operational-workload.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
    rows[1]['timestamp']=rows[0]['timestamp'];p.write_text('\n'.join(json.dumps(x) for x in rows))
    with pytest.raises(ValueError,match='chronology'):validate_structure(bundle)

def test_hash_tampering_is_detected():
    manifest=read(BUNDLE/'manifest.json')
    assert all(file_hash(Path(__file__).resolve().parents[2]/p)==sha for p,sha in manifest['hashes'].items())
    assert digest({'a':1,'b':2})==digest({'b':2,'a':1})
    assert digest({'a':2})!=digest({'a':1})

def test_outcome_cannot_be_revealed_without_matching_durable_decision(tmp_path):
    oracle=tmp_path/'oracle.json';write(oracle,{'ref':'expected_activity'})
    journal=tmp_path/'journal.jsonl';journal.write_text(json.dumps({'snapshotHash':'wrong','decision':{'alertRef':'ref'}})+'\n')
    with pytest.raises(ValueError,match='durably'):reveal(oracle,'ref',{'alertRef':'ref'},journal)
    decision={'alertRef':'ref','disposition':'must_review'}
    journal.write_text(json.dumps({'snapshotHash':digest(decision),'decision':decision})+'\n')
    assert reveal(oracle,'ref',decision,journal)=='expected_activity'

def test_final_bundle_cannot_be_development_run(tmp_path):
    with pytest.raises(ValueError,match='Development fixture'):run('adaptive',BUNDLE,tmp_path,tmp_path/'out',development=True)
    assert not (tmp_path/'out').exists()

def test_final_run_requires_opening_without_creating_database(tmp_path):
    with pytest.raises(ValueError,match='opening receipt'):run('baseline',BUNDLE,tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()

def row(b=True,a=False,outcome='expected_activity',kind='safe'):
    return dict(alertRef='ref',baselineReviewRequired=b,adaptiveReviewRequired=a,deferralClassification=kind,
        oracleOutcome=outcome,humanOverride=False,explicitAuditOverride=False,baselineHumanOverride=False,
        baselineReasonCodes=[],adaptiveReasonCodes=[])

def test_deferral_denominators_missing_outcome_audit_and_no_time_claims():
    records=[row(),row(outcome='confirmed_malicious',kind='unsafe'),row(False,False,kind='not-deferred'),
        row(outcome=None,kind='unassessed'),row(True,True,kind='not-deferred')]
    records[-1]['adaptiveReasonCodes']=['DETERMINISTIC_AUDIT_SAMPLE']
    result=metrics(records)
    assert result['totalDeferrals']==3
    assert result['unsafeDeferralRate']==rate(1,3)
    assert result['benignDeferralCoverage']==rate(1,2)
    assert result['outcomeCompleteness']==rate(4,5) and result['unassessedDeferrals']==1
    assert result['adaptiveAuditSamples']==1 and result['humanOverrides']==0

def test_zero_denominator_and_negative_reduction_not_hidden():
    assert rate(0,0)['value'] is None
    result=metrics([row(False,True,kind='not-deferred')])
    assert result['immediateReviewReductionCount']==-1
    assert result['immediateReviewReductionRate']==rate(-1,0)
    assert result['unsafeDeferralRate']==rate(0,0)


def test_changed_manifest_expected_hash_rejected(bundle):
    p=bundle/'manifest.json';m=read(p);m['hashes'][next(iter(m['hashes']))]='0'*64;write(p,m)
    with pytest.raises(ValueError,match='hash mismatch'):validate(bundle)
