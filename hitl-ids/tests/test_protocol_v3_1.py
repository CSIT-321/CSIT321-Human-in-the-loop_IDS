"""Environment amendment tests; never opens the actual formal protocol."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from protocol_v3_1 import environment as env
from protocol_v3_1.common import VERSION, REPO, file_hash
from protocol_v3_1.amendment import verify_amendment
from protocol_v3_1.runner import run
from open_protocol_v3_1 import open_protocol
from validate_protocol_v3_1 import validate


@pytest.mark.parametrize('version', [(3, 11, 0), (3, 11, 9), (3, 11, 14), (3, 11, 18)])
def test_311_patch_versions_pass(version):
    env.require_python(version)


@pytest.mark.parametrize('version', [(3, 12, 14), (3, 10, 9), (4, 11, 0)])
def test_other_versions_fail(version):
    with pytest.raises(RuntimeError, match='ENVIRONMENT REQUIREMENT NOT SATISFIED'):
        env.require_python(version)


def test_wrong_python_rejected_before_any_write(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'version_info', (3, 12, 14))
    with pytest.raises(RuntimeError, match='requires Python 3.11.x'):
        validate()
    with pytest.raises(RuntimeError, match='requires Python 3.11.x'):
        open_protocol(tmp_path / 'missing-runtime', tmp_path / 'opening')
    for arm in ('baseline', 'adaptive'):
        with pytest.raises(RuntimeError, match='requires Python 3.11.x'):
            run(arm, tmp_path / 'missing-bundle', tmp_path / 'missing-runtime', tmp_path / arm)
    assert list(tmp_path.iterdir()) == []


def test_opener_guard_independent_of_validator(monkeypatch, tmp_path):
    import validate_protocol_v3_1
    monkeypatch.setattr(validate_protocol_v3_1, 'validate', lambda: None)
    monkeypatch.setattr(sys, 'version_info', (3, 12, 14))
    with pytest.raises(RuntimeError):
        open_protocol(tmp_path, tmp_path / 'opening')
    assert not (tmp_path / 'opening').exists()


def test_receipt_environment_and_version_contract():
    receipt = {'protocolVersion': VERSION, 'environment': env.environment_receipt(),
               'requirementsHash': file_hash(REPO / 'hitl-ids/requirements.txt')}
    env.validate_opening_environment(receipt)
    assert receipt['environment']['pythonMajor'] == 3
    assert receipt['environment']['pythonMinor'] == 11
    for key, value in [('protocolVersion', 'final-evaluation-protocol-v3.0'),
                       ('requirementsHash', 'invalid')]:
        bad = copy.deepcopy(receipt); bad[key] = value
        with pytest.raises(ValueError): env.validate_opening_environment(bad)
    bad = copy.deepcopy(receipt); bad['environment']['pythonMinor'] = 12
    with pytest.raises(ValueError): env.validate_opening_environment(bad)


def test_only_environment_amended():
    proof = verify_amendment()
    assert proof['unchanged']['worker'] == 'identical'
    assert proof['unchanged']['evaluatorArithmetic'] == 'identical'
    assert validate(manifest=False)['primary'] == 140
