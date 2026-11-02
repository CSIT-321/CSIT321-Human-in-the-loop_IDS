"""One-time design freeze, not an experiment opening. Refuses to overwrite a frozen manifest."""
from datetime import datetime,timezone
from pathlib import Path
from protocol_v3.common import *
from validate_protocol_v3 import validate_structure

if __name__=='__main__':
    target=BUNDLE/'manifest.json'
    if target.exists(): raise ValueError('Already frozen; do not silently re-freeze after observing results')
    validate_structure(BUNDLE)
    paths=list(BUNDLE.rglob('*.json'))+list(BUNDLE.rglob('*.jsonl'))+list(BUNDLE.glob('*.md'))
    paths += list((REPO/'hitl-ids/scripts').glob('*protocol_v3*.py'))+list((REPO/'hitl-ids/scripts/protocol_v3').glob('*.py'))
    paths += [REPO/'docs/final-evaluation-protocol-v3.md',REPO/'hitl-ids/tests/test_protocol_v3.py',REPO/'hitl-ids/requirements.txt']
    policies={}
    for p in sorted((REPO/'hitl-ids/config').glob('*.json')):
        paths.append(p)
        value=read(p);policies[p.name]={'version':value.get('version',value.get('protocolVersion')),'sha256':file_hash(p)}
    manifest={'protocolVersion':VERSION,'status':'frozen_unopened','runtimeSha':RUNTIME_SHA,
        'createdAt':datetime.now(timezone.utc).isoformat(),'workloadAlertCount':200,'learningCount':40,'holdoutCount':160,
        'primaryCount':140,'generatorVersion':'protocol-v3-generator-1','runnerVersion':'protocol-v3-runner-1','evaluatorVersion':'protocol-v3-evaluator-1',
        'hashEncoding':'JSON = UTF-8 sorted keys compact separators no NaN; JSONL = ordered parsed array canonical JSON; source/docs = UTF-8 LF; manifest excludes itself',
        'runtimePolicies':policies,'runtimeTrees':{p:git('rev-parse',RUNTIME_SHA+':'+p) for p in ('hitl-ids/apps','hitl-ids/packages','hitl-ids/config')},
        'hashes':{p.relative_to(REPO).as_posix():file_hash(p) for p in sorted(set(paths))}}
    write(target,manifest)
    print('FROZEN / UNOPENED; manifest canonical SHA-256:',file_hash(target))
