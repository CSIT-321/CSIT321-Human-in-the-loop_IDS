"""Disposable direct-escalation journeys, with extra unadmitted synthetic alerts."""
from contextlib import closing
import json
from pathlib import Path
import sys
from unittest.mock import patch

HITL = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HITL / 'scripts'))
import serve_routing_rehearsal as routing
from serve_s16_rehearsal import build_pristine_fixture
from packages.contracts import db
from packages.detection.adapters.staging import stage_file


def initial_database(_source, target):
    build_pristine_fixture(target)
    # Exactly two extra policy-event alerts are consumed by the two new journeys.
    # Preserve the existing suite's remaining staged-alert order and severity assertions.
    extra = Path(target).with_name('direct-extra-alert.json')
    extra.write_text(json.dumps(json.loads((HITL / 'tests/fixtures/suricata-alerts.json').read_text())[1]), encoding='utf-8')
    with closing(db.connect(target)) as conn:
        for sensor in ('direct-manual-demo', 'direct-continue-demo'):
            stage_file(conn, extra, sensor)
    return target


with patch.object(routing.shutil, 'copy2', side_effect=initial_database):
    routing.main()
