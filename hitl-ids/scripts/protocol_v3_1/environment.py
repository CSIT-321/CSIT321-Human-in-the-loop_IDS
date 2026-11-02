"""Fail-closed interpreter contract; standard library only, before runtime imports or writes."""
import platform
import sys


def require_python(version=None):
    current = sys.version_info if version is None else version
    if tuple(current[:2]) != (3, 11):
        actual = '.'.join(map(str, current[:3]))
        raise RuntimeError(
            'FAIL — ENVIRONMENT REQUIREMENT NOT SATISFIED: '
            f'Protocol V3.1 requires Python 3.11.x; current interpreter is Python {actual}.'
        )


def environment_receipt():
    require_python()
    return {'pythonFullVersion': sys.version, 'pythonMajor': sys.version_info.major,
            'pythonMinor': sys.version_info.minor, 'pythonPatch': sys.version_info.micro,
            'executablePath': sys.executable, 'platform': platform.platform()}


def validate_opening_environment(receipt):
    require_python()
    if receipt.get('protocolVersion') != 'final-evaluation-protocol-v3.1':
        raise ValueError('Opening must belong to Protocol V3.1; V3.0 results cannot be reused')
    env = receipt.get('environment', {})
    if (env.get('pythonMajor'), env.get('pythonMinor')) != (3, 11):
        raise ValueError('Opening must record Python 3.11.x')
    for field in ('pythonFullVersion', 'pythonPatch', 'executablePath', 'platform'):
        if field not in env:
            raise ValueError('Opening environment field missing: ' + field)
    from .common import REPO, file_hash
    if receipt.get('requirementsHash') != file_hash(REPO / 'hitl-ids/requirements.txt'):
        raise ValueError('Opening requirements hash mismatch')
