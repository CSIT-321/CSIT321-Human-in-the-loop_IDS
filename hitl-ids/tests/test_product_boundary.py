"""X6 (S9-05): the product API must start without scripts/ and must not import runner code.

presentation_replay imported SENSOR/SCOPE from scripts.protocol_v3.common, so every API start needed scripts/,
and the V3.1 preflight boundary rule (scripts/validate_protocol_v3_1.py:87-90) rejects any product file that
contains 'protocol_v3'. The replay's data files stay under evaluation/: they are read only on request, and a
missing file already answers 503 REPLAY_WORKLOAD_UNAVAILABLE (apps/api/workspaces.py:204).
"""
import ast
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
BANNED_WORDS = ('external-outcomes.json', 'protocol_v3', 'protocol-v3/oracle')  # the preflight's own list


def product_files():
    for folder in ('apps/api', 'packages'):
        yield from (HITL / folder).rglob('*.py')


def test_no_product_module_imports_scripts_or_evaluation():
    offenders = []
    for path in product_files():
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            offenders += [f'{path.relative_to(HITL)}: {n}' for n in names if n.split('.')[0] in ('scripts', 'evaluation')]
    assert offenders == []


def test_no_product_module_trips_the_preflight_boundary_rule():
    hits = [str(p.relative_to(HITL)) for p in product_files()
            if any(word in p.read_text(encoding='utf-8') for word in BANNED_WORDS)]
    assert hits == []


def test_the_replay_keeps_the_frozen_sensor_and_scope():
    """The values must not drift from the frozen protocol, or a replay stages records under another scope."""
    from apps.api import presentation_replay
    from scripts.protocol_v3.common import SCOPE, SENSOR   # tests may read runner code; the product may not
    assert (presentation_replay.SENSOR, presentation_replay.SCOPE) == (SENSOR, SCOPE)
