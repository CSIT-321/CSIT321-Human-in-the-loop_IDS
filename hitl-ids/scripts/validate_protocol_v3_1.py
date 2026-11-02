"""Read-only structural, identity, policy, oracle-separation and manifest preflight; no experiment."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_v3_1.common import *
from protocol_v3_1.environment import require_python
if __name__ == "__main__": require_python()
from packages.detection.adapters.suricata_bundle import build_bundle, parse_record, bundle_for
from packages.detection.attack_classification import classify
from packages.detection.triage_memory import context_for, load_config
from packages.detection.triage_policy import TriageContext

def require(condition,message):
    if not condition: raise ValueError(message)

def validate_structure(bundle):
    rows=[__import__('json').loads(line) for line in (bundle/'workload/operational-workload.jsonl').read_text(encoding='utf-8').splitlines()]
    structure=read(bundle/'expected/workload-structure.json'); oracle=read(bundle/'oracle/external-outcomes.json')
    contexts=read(bundle/'workload/trusted-context.json')
    require(len(rows)==len(structure)==200,'exactly 200 operational records required')
    require([s['index'] for s in structure]==list(range(1,201)),'chronological indices')
    require([s['phase'] for s in structure]==['learning']*40+['holdout']*160,'40/160 chronological split')
    require(Counter(s['stratum'] for s in structure)==Counter(stable_learning=24,drift_learning=6,negative_learning=10,
        stable_matching_benign=80,unseen_benign=20,malicious=20,suspicious=20,unknown_tier2=10,drift_conflict=10),'stratum counts')
    refs=[s['alertRef'] for s in structure]
    require(len(set(refs))==200 and set(refs)==set(oracle)==set(contexts),'unique identity and complete oracle/context coverage')
    require(all(o in OUTCOMES for o in oracle.values()),'valid oracle outcomes')
    timestamps=[datetime.fromisoformat(row['timestamp']) for row in rows]
    require(all(a<b for a,b in zip(timestamps,timestamps[1:])),'strict timestamp chronology')
    groups=defaultdict(list); exacts={}; related={}; policy=load_config()
    for row,meta in zip(rows,structure):
        require(set(row)=={'timestamp','flow_id','event_type','src_ip','dest_ip','src_port','dest_port','proto','alert'},'operational input field whitelist')
        require(set(row['alert'])=={'signature_id','rev','severity','action','signature','category'},'EVE alert field whitelist')
        require(not any(o in canonical(row).decode() for o in OUTCOMES),'no oracle outcomes in evidence')
        alert=build_bundle([parse_record(row,SENSOR,SCOPE)])
        require(str(alert.canonical_alert_id)==meta['alertRef'],'actual adapter identity')
        classification=classify(bundle_for(alert))
        require((classification.attack_category=='unknown_needs_expert')==(meta['stratum']=='unknown_tier2'),'classification boundary')
        context=context_for(alert).model_dump(by_alias=True)
        exact=tuple(context[field] for field in policy.exact_required_fields)
        pattern=meta['pattern']; groups[pattern].append(meta)
        require(pattern not in exacts or exacts[pattern]==exact,'same Exact identity per pattern')
        exacts[pattern]=exact
        # Actual matcher vetoes related unsafe lessons: isolate title AND native category, not only IP.
        related[pattern]=(context['detectionTitle'],context['detectionCategory'])
        TriageContext.model_validate(contexts[meta['alertRef']])
        if meta['stratum']=='malicious': require(contexts[meta['alertRef']]['knownMaliciousIndicator'] is True,'malicious control risk context')
        if meta['stratum']=='suspicious': require(contexts[meta['alertRef']]['evidenceConflict'] is True,'suspicious control risk context')
        require(meta['analyst']==f"v3-analyst-{(meta['index']-1)%3+1}",'round-robin identity')
    require(len(set(exacts.values()))==len(exacts),'unrelated groups must not Exact-match')
    require(len(set(t for t,c in related.values()))==len(related) and len(set(c for t,c in related.values()))==len(related),'no unintended related unsafe lesson veto')
    for p in range(1,11):
        group=groups[f'p{p:03d}']; learning=[s for s in group if s['phase']=='learning']; holdout=[s for s in group if s['phase']=='holdout']
        require(len(learning)==3 and len(holdout)==(10 if p<=8 else 5),'3 learning / 10 stable or 5 drift')
        outcome='false_positive' if 5<=p<=8 else 'expected_activity'
        require(all(oracle[s['alertRef']]==outcome for s in learning),'canonical learning outcomes')
        require(all(oracle[s['alertRef']]==(outcome if p<=8 else 'confirmed_malicious' if p==9 else 'suspicious') for s in holdout),'holdout outcomes')
        require([s['index'] for s in holdout if s['driftAudit']]==([holdout[0]['index']] if p>=9 else []),'first drift contradiction only')
    require(Counter(oracle[s['alertRef']] for s in structure if s['stratum']=='unknown_tier2')=={'confirmed_malicious':5,'suspicious':5},'unknown control outcome balance')
    require(Counter(oracle[s['alertRef']] for s in structure[:40] if s['stratum']=='negative_learning')=={'confirmed_malicious':5,'suspicious':5},'negative outcome balance')
    require(sum(s['driftAudit'] for s in structure)==2,'exactly two predefined feedback injections')
    require(Counter(oracle[s['alertRef']] for s in structure if s['stratum']=='unseen_benign')=={'expected_activity':10,'false_positive':10},'unseen benign balance')
    require(all(oracle[s['alertRef']]==s['stratum'].replace('malicious','confirmed_malicious') for s in structure if s['stratum'] in ('malicious','suspicious')),'unsafe controls')
    for s in structure:
        c=contexts[s['alertRef']]
        if s['stratum'] in ('stable_learning','drift_learning','stable_matching_benign','unseen_benign','drift_conflict'):
            require(c['assetCriticality']=='low' and not any(c[k] for k in ('knownMaliciousIndicator','evidenceConflict','confirmedMalicious','responseRequired','repeatedCampaign')),'frozen initially safe context')
    return {'alerts':200,'learning':40,'holdout':160,'primary':140,'exactFields':policy.exact_required_fields,'patterns':len(groups)}

def validate(bundle=BUNDLE, *, manifest=True):
    require_python()
    result=validate_structure(bundle)
    from protocol_v3_1.amendment import verify_amendment
    verify_amendment()
    require(not git('diff',RUNTIME_SHA,'--','hitl-ids/apps','hitl-ids/packages','hitl-ids/config'),'product differs from frozen runtime')
    if manifest:
        m=read(bundle/'manifest.json')
        require(m['protocolVersion']==VERSION,'V3.1 manifest version')
        require(m['status']=='frozen_unopened' and m['runtimeSha']==RUNTIME_SHA,'frozen unopened runtime')
        for rel,expected in m['hashes'].items():
            require(file_hash(REPO/rel)==expected,'hash mismatch: '+rel)
        require(read(bundle/'protocol-v3.1.json')['status']=='frozen_unopened','protocol is unopened')
    # Product modules cannot reference evaluation artifacts or runner code.
    for folder in ('apps/api','packages'):
        for p in (REPO/'hitl-ids'/folder).rglob('*.py'):
            text=p.read_text(encoding='utf-8')
            require(not any(word in text for word in ('external-outcomes.json','protocol_v3','protocol-v3/oracle')),'oracle/runtime dependency: '+str(p))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--bundle',type=Path,default=BUNDLE)
    args=parser.parse_args(); print(__import__('json').dumps({'preflight':'PASS',**validate(args.bundle)}))
