"""Read-only equality proof against immutable V3.0 artifacts and failed-run evidence."""
from .common import *


def verify_amendment():
    old = REPO / 'evaluation/protocol-v3'
    frozen = read(old / 'manifest.json')
    for rel, sha in frozen['hashes'].items():
        if file_hash(REPO / rel) != sha:
            raise ValueError('V3.0 frozen artifact changed: ' + rel)
    failure = read(REPO / 'evaluation/protocol-v3-run-001/evidence-manifest.json')
    for rel, sha in failure['files'].items():
        if file_hash(REPO / rel) != sha:
            raise ValueError('Blocked V3.0 evidence changed: ' + rel)
    equality = {}
    for folder in ('workload', 'oracle', 'expected'):
        for path in (old / folder).rglob('*'):
            if path.is_file():
                rel = path.relative_to(old)
                target = BUNDLE / rel
                if path.read_bytes() != target.read_bytes():
                    raise ValueError('Input bytes differ: ' + str(rel))
                equality[rel.as_posix()] = file_hash(target)
    if (old / 'result-record.schema.json').read_bytes() != (BUNDLE / 'result-record.schema.json').read_bytes():
        raise ValueError('Result schema changed')
    previous = read(old / 'protocol-v3.json')
    current = read(BUNDLE / 'protocol-v3.1.json')
    assert current.pop('protocolVersion') == VERSION
    assert current.pop('environmentRequirement') == {'pythonMajor': 3, 'pythonMinor': 11, 'patch': 'any', 'failBeforeOpening': True}
    previous.pop('protocolVersion')
    if previous != current:
        raise ValueError('Effectiveness methodology changed beyond environment amendment')
    for path, sha in frozen['runtimeTrees'].items():
        if git('rev-parse', 'HEAD:' + path) != sha:
            raise ValueError('Runtime tree changed: ' + path)
    # The oracle-blind worker and evaluator arithmetic remain verbatim apart from
    # the separately named import and interpreter guard in the evaluator.
    scripts = REPO / 'hitl-ids/scripts'
    assert (scripts / 'protocol_v3/worker.py').read_text() == (scripts / 'protocol_v3_1/worker.py').read_text()
    prior = (scripts / 'evaluate_protocol_v3.py').read_text()
    revised = (scripts / 'evaluate_protocol_v3_1.py').read_text()
    revised = revised.replace('from protocol_v3_1.common import *', 'from protocol_v3.common import *')
    revised = revised.replace('\nfrom protocol_v3_1.environment import require_python', '')
    revised = revised.replace('    require_python()\n', '')
    assert prior == revised, 'Evaluator logic differs'
    return {'unchanged': {'inputs': equality, 'runtimeSha': RUNTIME_SHA,
            'runtimeTrees': frozen['runtimeTrees'], 'policies': frozen['runtimePolicies'],
            'protocolFields': sorted(previous), 'worker': 'identical', 'evaluatorArithmetic': 'identical',
            'v30FailureEvidence': 'verified'},
            'changed': ['protocol identity and bundle/tool paths', 'validator Python guard',
                        'independent opener guard', 'runner and evaluator Python guard',
                        'opening environment receipt', 'amendment documentation']}
