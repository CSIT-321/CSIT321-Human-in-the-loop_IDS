"""Only an independent eight-alert DEVELOPMENT fixture. Cannot run the final 200-alert bundle."""
import argparse
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_v3_1.common import *
from protocol_v3_1.runner import run
from packages.detection.adapters.suricata_bundle import build_bundle,parse_record
from evaluate_protocol_v3_1 import evaluate

def fixture(out):
    rows=[]; structure=[]; contexts={}; oracle={}
    for i in range(1,9):
        unknown=i==8
        record={'timestamp':(datetime(2026,11,4,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat(),
            'flow_id':990000+i,'event_type':'alert','src_ip':'192.0.2.201' if not unknown else '192.0.2.202',
            'dest_ip':'198.51.100.201','src_port':51234,'dest_port':22,'proto':'TCP',
            'alert':{'signature_id':9900001,'rev':1,'severity':3,'action':'allowed',
                'signature':'DEVELOPMENT ONLY '+('opaque anomaly' if unknown else 'SSH brute force'),
                'category':'Development opaque' if unknown else 'Development scan'}}
        ref=str(build_bundle([parse_record(record,'controlled-v3-development','controlled-v3-development')]).canonical_alert_id)
        rows.append(record); structure.append({'index':i,'alertRef':ref,'phase':'learning' if i<=3 else 'holdout',
            'stratum':'stable_learning' if i<=3 else 'stable_matching_benign' if i==4 else 'unknown_tier2' if unknown else 'drift_conflict',
            'pattern':'development-unknown' if unknown else 'development-one','driftAudit':i==5,'analyst':f'v3-analyst-{(i-1)%3+1}'})
        oracle[ref]='expected_activity' if i<=4 else 'confirmed_malicious'
        contexts[ref]=dict(assetCriticality='low',repeatedCampaign=False,correlatedAlertCount=1,responseRequired=False,
            knownMaliciousIndicator=False,analystEscalated=False,unresolvedByTier1=False,evidenceConflict=False,confirmedMalicious=False)
    (out/'workload').mkdir(parents=True)
    (out/'workload/operational-workload.jsonl').write_bytes(b'\n'.join(canonical(r) for r in rows)+b'\n')
    write(out/'workload/trusted-context.json',contexts);write(out/'expected/workload-structure.json',structure);write(out/'oracle/external-outcomes.json',oracle)

def smoke(runtime,out):
    out.mkdir(parents=True,exist_ok=False); fixture(out/'fixture')
    run('baseline',out/'fixture',runtime,out/'baseline',development=True)
    run('adaptive',out/'fixture',runtime,out/'adaptive',development=True)
    result=evaluate(out/'baseline',out/'adaptive',out/'report',development=True)
    learning=read(out/'adaptive/learning-end.json'); final=read(out/'adaptive/final-memory.json')
    assert len(learning['lessons'])==1 and learning['lessons'][0]['status']=='active'
    assert learning['lessons'][0]['supportCount']==3 and len(learning['evidenceAuthorDistribution'])==3
    assert result['criticalSafetyPass'] and result['safety']['conflictTriggeredWithdrawals']==1
    assert final['verdictEvents']==4 and final['collectionRuns']==0
    print('PASS: independent 8-alert development smoke; final experiment NOT run')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();smoke(a.runtime_root,a.out)
