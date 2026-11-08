"""E3 (S9-02): the routing-rehearsal fixture script stages at all, with each stage naming its capture_scope.

Before E3, every stage_file call in scripts/serve_routing_rehearsal.py passed no capture_scope, so the
script raised TypeError: stage_file() missing 1 required keyword-only argument: 'capture_scope'.
"""
import shutil
import sys
from contextlib import closing
from pathlib import Path

import pytest

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL / 'scripts'))
sys.path.insert(0, str(HITL))

from packages.contracts import db  # noqa: E402
from serve_routing_rehearsal import build_fixture  # noqa: E402


def test_the_fixture_builds_and_stages_every_sensor(tmp_path):
    path = tmp_path / 'routing.db'
    shutil.copy2(HITL / 'data/demo.db', path)
    build_fixture(path)  # no TypeError, no partial fixture
    with closing(db.connect(path)) as conn:
        staged = {row['sensor_id']: row['n'] for row in conn.execute(
            "SELECT sensor_id, COUNT(*) AS n FROM suricata_eve_records WHERE capture_scope='disposable-routing-rehearsal' "
            "GROUP BY sensor_id")}
        assert staged == {'routing-recommended': 2, 'routing-reject': 2, 'routing-staged': 2,
                          'memory-demo': 5, 'selective-demo': 6}
        inbox = {row['sensor_id']: row['n'] for row in conn.execute(
            "SELECT sensor_id, COUNT(*) AS n FROM external_alert_inbox WHERE sensor_id IN "
            "('routing-staged','routing-recommended','routing-reject','memory-demo','selective-demo') GROUP BY sensor_id")}
        assert inbox == {'routing-recommended': 2, 'routing-reject': 2, 'routing-staged': 2,
                         'memory-demo': 5, 'selective-demo': 6}
        assert conn.execute("SELECT COUNT(*) FROM operational_alerts_v2").fetchone()[0] >= 3
        assert conn.execute("SELECT COUNT(*) FROM external_operational_admission").fetchone()[0] == 11  # 5 memory + 6 selective


def test_the_prospective_flag_stages_the_journey_fixture(tmp_path):
    path = tmp_path / 'routing.db'
    shutil.copy2(HITL / 'data/demo.db', path)
    build_fixture(path, prospective=True)
    with closing(db.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM external_alert_inbox WHERE sensor_id='prospective-demo'").fetchone()[0] > 0
