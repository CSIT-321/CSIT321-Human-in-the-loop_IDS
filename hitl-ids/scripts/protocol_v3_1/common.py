"""Canonical artifact hashing and immutable runtime verification (no oracle loading)."""
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BUNDLE = REPO / 'evaluation/protocol-v3.1'
RUNTIME_SHA = 'c00c556405198f60adc42f8bb2a7cee03689a60c'
VERSION = 'final-evaluation-protocol-v3.1'
TOOL_VERSION = 'protocol-v3-tooling-1'
SENSOR = 'controlled-v3-sensor'
SCOPE = 'controlled-v3-final'
OUTCOMES = {'expected_activity', 'false_positive', 'suspicious', 'confirmed_malicious'}
BENIGN = {'expected_activity', 'false_positive'}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def file_hash(path):
    path = Path(path)
    if path.suffix == '.json': return digest(read(path))
    if path.suffix == '.jsonl': return digest([json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line])
    return hashlib.sha256(path.read_text(encoding='utf-8').replace('\r\n', '\n').encode()).hexdigest()

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')

def git(*args, root=REPO):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def verify_runtime(runtime):
    """A run imports a separate exact-base checkout, not whatever is on the evaluator branch."""
    runtime = Path(runtime).resolve()
    if git('rev-parse', 'HEAD', root=runtime) != RUNTIME_SHA:
        raise ValueError('Runtime checkout must be at exact frozen runtime SHA')
    protected = ['hitl-ids/apps/api', 'hitl-ids/packages', 'hitl-ids/config']
    if git('status', '--porcelain', '--untracked-files=all', '--', *protected, root=runtime):
        raise ValueError('Runtime code/config must be clean, including untracked files')
    return runtime / 'hitl-ids'
