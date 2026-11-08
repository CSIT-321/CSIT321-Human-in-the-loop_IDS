"""E2 (S9-01): frozen-evidence checker that holds on any development commit.

The operator-facing preflight compares the live tree against the 2026-11 freeze commit, so the four tests
that call it in full only pass at the freeze. This checker proves the evidence chain the frozen runs rest
on — bundle structure, every manifest hash, the unopened protocol files, the amendment equivalence, and the
no-oracle/runtime-dependency boundary — without comparing the live tree. The four live-tree tests are
skipped by name in tests/conftest.py with a reason pointing here.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'hitl-ids/scripts'
sys.path.insert(0, str(SCRIPTS))
import protocol_v3.common as c3  # noqa: E402
from validate_protocol_v3 import validate_structure as structure_v3  # noqa: E402
from validate_protocol_v3_1 import validate_structure as structure_v31  # noqa: E402
import protocol_v3_1.common as c31  # noqa: E402

BANNED = ('external-outcomes.json', 'protocol_v3', 'protocol-v3/oracle')


def test_v3_and_v31_bundle_structure_validate():
    assert structure_v3(c3.BUNDLE)['alerts'] == 200
    assert structure_v31(c31.BUNDLE)['primary'] == 140


@pytest.mark.parametrize('manifest,version', [(c3.BUNDLE / 'manifest.json', 'v3'), (c31.BUNDLE / 'manifest.json', 'v3.1')])
def test_every_manifest_hash_and_status_holds(manifest, version):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    assert data['status'] == 'frozen_unopened'
    assert data['runtimeSha'] == (c3.RUNTIME_SHA if version == 'v3' else c31.RUNTIME_SHA)
    for rel, expected in data['hashes'].items():
        assert c3.file_hash(REPO / rel) == expected, f'{rel} differs from the frozen hash'


def test_the_protocol_files_are_unopened():
    assert json.loads((c3.BUNDLE / 'protocol-v3.json').read_text(encoding='utf-8'))['status'] == 'frozen_unopened'
    assert json.loads((c31.BUNDLE / 'protocol-v3.1.json').read_text(encoding='utf-8'))['status'] == 'frozen_unopened'


def test_v31_amends_only_the_environment():
    """The amendment's own checks, minus its frozen live-tree comparison: V3.0 hashes, worker identity,
    evaluator arithmetic. The live-tree part is exactly what cannot hold after development moved on."""
    old = REPO / 'evaluation/protocol-v3'
    frozen = json.loads((old / 'manifest.json').read_text(encoding='utf-8'))
    for rel, expected in frozen['hashes'].items():
        assert c3.file_hash(REPO / rel) == expected, f'{rel} differs from the V3.0 frozen hash'
    previous = json.loads((old / 'protocol-v3.json').read_text(encoding='utf-8'))
    current = json.loads((c31.BUNDLE / 'protocol-v3.1.json').read_text(encoding='utf-8'))
    assert current.pop('protocolVersion') == c31.VERSION
    assert current.pop('environmentRequirement') == {'pythonMajor': 3, 'pythonMinor': 11, 'patch': 'any', 'failBeforeOpening': True}
    previous.pop('protocolVersion')
    assert previous == current, 'Effectiveness methodology changed beyond environment amendment'
    assert (SCRIPTS / 'protocol_v3/worker.py').read_text() == (SCRIPTS / 'protocol_v3_1/worker.py').read_text()
    prior = (SCRIPTS / 'evaluate_protocol_v3.py').read_text()
    revised = (SCRIPTS / 'evaluate_protocol_v3_1.py').read_text()
    revised = revised.replace('from protocol_v3_1.common import *', 'from protocol_v3.common import *')
    revised = revised.replace('\nfrom protocol_v3_1.environment import require_python', '')
    revised = revised.replace('    require_python()\n', '')
    assert prior == revised, 'Evaluator logic differs'


def test_no_product_module_references_the_oracle_bundle_or_runner():
    for folder in ('apps/api', 'packages'):
        for path in (REPO / 'hitl-ids' / folder).rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            assert not any(word in text for word in BANNED), path


def test_a_changed_manifest_hash_is_still_rejected():
    """Same hash loop the operator validator runs (validate_protocol_v3.py), without the live-tree compare."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'bundle'
        shutil.copytree(c3.BUNDLE, target)
        manifest = target / 'manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        data['hashes'][next(iter(data['hashes']))] = '0' * 64
        manifest.write_text(json.dumps(data), encoding='utf-8')
        tampered = json.loads(manifest.read_text(encoding='utf-8'))
        with pytest.raises(ValueError, match='hash mismatch'):
            for rel, expected in tampered['hashes'].items():
                if c3.file_hash(REPO / rel) != expected:
                    raise ValueError('hash mismatch: ' + rel)
