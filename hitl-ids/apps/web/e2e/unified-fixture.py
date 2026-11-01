"""Disposable canonical workstation rehearsal; never reads data/demo.db."""
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
from packages.detection.adapters.operational_v2 import materialize_source
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.triage_policy_service import apply_triage_policy


def initial_database(_source, target):
    build_pristine_fixture(target)
    with closing(db.connect(target)) as conn:
        materialize_source(conn, 'legacy_flow_alert', 478)
        extra = Path(target).with_name('unified-extra.json')
        event = json.loads((HITL / 'tests/fixtures/suricata-alerts.json').read_text())[1]
        extra.write_text(json.dumps(event), encoding='utf-8')
        for sensor in ('direct-manual-demo', 'direct-continue-demo'):
            stage_file(conn, extra, sensor)
        event['alert']['signature'] = 'SYNTHETIC unified-workstation journey'
        extra.write_text(json.dumps(event), encoding='utf-8')
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        for index in range(2):
            sensor = f'unified-journey-{index}'
            stage_file(conn, extra, sensor)
            source_id = conn.execute('SELECT id FROM external_alert_inbox WHERE sensor_id=?', (sensor,)).fetchone()[0]
            alert = materialize_source(conn, 'external_nids_alert', source_id)
            if index:
                apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=read_triage(conn, alert.id))
    return target


with patch.object(routing.shutil, 'copy2', side_effect=initial_database):
    routing.main()
