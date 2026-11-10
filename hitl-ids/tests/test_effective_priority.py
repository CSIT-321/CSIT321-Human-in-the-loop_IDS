"""The row must show the score the queue order uses (C1 display fix, 2026-11-10).

triage_state.operational_priority stays fixed at routing time. The queue sorts by
priority + (combined_score - detection_score). These tests prove the view copies
that same effective value without writing anything.
"""

import sqlite3

from apps.api import routing_routes
from packages.contracts.operational_v2 import OperationalTriageStateV2


def _state(priority):
    return OperationalTriageStateV2(operational_alert_id=1, operational_priority=priority,
                                    priority_band="P1", priority_band_scheme="p1_p4",
                                    handling_route="tier1_review", workflow_stage="triage")


def _conn(combined, detection):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, combined_score REAL, detection_score REAL)")
    conn.execute("INSERT INTO alerts (id, combined_score, detection_score) VALUES (7, ?, ?)", (combined, detection))
    return conn


def _row(legacy_id=7):
    return {"legacy_alert_id": legacy_id}


def test_own_verdict_moves_the_displayed_priority():
    state = routing_routes._effective_priority(_conn(22.39, 52.39), _row(), _state(52.39))
    assert state.operational_priority == 22.39
    assert state.priority_band == "P1"


def test_family_adjustment_moves_a_member_without_its_own_verdict():
    state = routing_routes._effective_priority(_conn(70.0, 92.7), _row(), _state(92.7))
    assert state.operational_priority == 70.0


def test_no_legacy_alert_keeps_the_routing_priority():
    state = routing_routes._effective_priority(_conn(0, 0), _row(None), _state(64.0))
    assert state.operational_priority == 64.0


def test_no_verdict_keeps_the_routing_priority():
    state = routing_routes._effective_priority(_conn(52.39, 52.39), _row(), _state(52.39))
    assert state.operational_priority == 52.39


def test_effective_priority_clamps_to_zero():
    state = routing_routes._effective_priority(_conn(0.0, 30.0), _row(), _state(5.0))
    assert state.operational_priority == 0.0
