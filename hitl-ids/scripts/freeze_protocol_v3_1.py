"""One-time V3.1 freeze after successful preflight; never opens the experiment."""
from datetime import datetime, timezone
from protocol_v3_1.environment import require_python
from protocol_v3_1.common import *
from protocol_v3_1.amendment import verify_amendment
from validate_protocol_v3_1 import validate


if __name__ == '__main__':
    require_python()
    target = BUNDLE / 'manifest.json'
    if target.exists():
        raise ValueError('Already frozen; do not overwrite')
    validate(manifest=False)
    proof = verify_amendment()
    evidence = read(REPO / 'evaluation/protocol-v3.1-preflight/validation.json')
    if evidence['status'] != 'PASS' or evidence['pythonMajorMinor'] != [3, 11]:
        raise ValueError('Actual Python 3.11 preflight evidence required')
    if read(BUNDLE / 'amendment-diff.json') != proof:
        raise ValueError('Amendment comparison stale')
    old = read(REPO / 'evaluation/protocol-v3/manifest.json')
    paths = [p for p in BUNDLE.rglob('*') if p.is_file()]
    paths += list((REPO / 'hitl-ids/scripts').glob('*protocol_v3_1*.py'))
    paths += list((REPO / 'hitl-ids/scripts/protocol_v3_1').glob('*.py'))
    paths += [REPO / p for p in old['hashes']]
    paths += [REPO / 'docs/final-evaluation-protocol-v3.1.md',
              REPO / 'hitl-ids/tests/test_protocol_v3_1.py',
              REPO / 'evaluation/protocol-v3.1-preflight/validation.json',
              REPO / 'evaluation/protocol-v3/manifest.json',
              REPO / 'evaluation/protocol-v3-run-001/evidence-manifest.json']
    manifest = {'protocolVersion': VERSION, 'status': 'frozen_unopened',
        'runtimeSha': RUNTIME_SHA, 'createdAt': datetime.now(timezone.utc).isoformat(),
        'amendmentFrom': 'final-evaluation-protocol-v3.0',
        'amendmentReason': 'environment-version enforcement gap discovered during blocked V3.0 formal run',
        'requiredPython': {'major': 3, 'minor': 11, 'patch': 'any'},
        'workloadAlertCount': 200, 'learningCount': 40, 'holdoutCount': 160, 'primaryCount': 140,
        'workloadHash': file_hash(BUNDLE / 'workload/operational-workload.jsonl'),
        'oracleHash': file_hash(BUNDLE / 'oracle/external-outcomes.json'),
        'requirementsHash': file_hash(REPO / 'hitl-ids/requirements.txt'),
        'runtimePolicies': old['runtimePolicies'], 'runtimeTrees': old['runtimeTrees'],
        'hashEncoding': old['hashEncoding'],
        'hashes': {p.relative_to(REPO).as_posix(): file_hash(p) for p in sorted(set(paths))}}
    write(target, manifest)
    print('FROZEN / UNOPENED; manifest canonical SHA-256:', file_hash(target))
