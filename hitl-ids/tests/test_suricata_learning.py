"""Suricata alerts rerank on a verdict, through the approved guardrails and agreement gate (2026-11-12).

Measured defect: on the packet replay a false positive on ETERNALBLUE (priority 85) left it at 85, because only
flow alerts carried a verdict delta. These tests pin the fix: own verdict, the critical floor, the family gate
(3 agreeing verdicts on one signature against one internal asset), the family key, and the flow path unchanged.
"""
from uuid import uuid4

import pytest

from apps.api import operational_queue
from packages.detection import suricata_learning as learning
from packages.detection.analyst_verdict import VerdictCommand, read_verdict, record_verdict
from pre_freeze_fixture import admit_all, event, stage
from test_pre_freeze_review_fixes import conn  # noqa: F401  (pytest fixture)
from work_claim_fixture import claim_work


def _admit(conn, count, signature='SSH brute force', category='Misc activity',
           dst='198.51.100.20', start=1):
    events = []
    for i in range(count):
        raw = event(flow=start + i, signature=signature, category=category, severity=2)
        raw['dest_ip'] = dst
        raw['src_ip'] = f'203.0.113.{start + i}'
        raw['src_port'] = 40000 + start + i
        events.append(raw)
    stage(conn, events)
    return admit_all(conn)


def _verdict(conn, alert, outcome):
    claim_work(conn, alert, 1)
    view = read_verdict(conn, alert.operational_alert_ref, 1)
    return record_verdict(conn, alert.operational_alert_ref, actor_id=1, request=VerdictCommand(
        request_id=uuid4(), expected_revision=view.revision, expected_state_version=view.source_state_version,
        outcome=outcome, reason='Analyst conclusion'))


def _priority(conn, alert):
    return conn.execute('SELECT operational_priority FROM operational_triage_state_v2 WHERE operational_alert_id=?',
                        (alert.id,)).fetchone()[0]


def _set_priority(conn, alert, value):
    conn.execute('UPDATE operational_triage_state_v2 SET operational_priority=? WHERE operational_alert_id=?',
                 (value, alert.id))
    conn.commit()




def test_the_internal_host_is_the_home_net_side():
    assert learning.internal_host('203.0.113.5', '172.31.65.56') == '172.31.65.56'      # inbound attack
    assert learning.internal_host('172.31.64.80', '93.184.216.34') == '172.31.64.80'    # outbound beacon
    assert learning.internal_host('172.31.64.80', '172.31.0.2') == '172.31.64.80>172.31.0.2'  # lateral
    assert learning.internal_host('203.0.113.5', '198.51.100.20') == '198.51.100.20'    # neither: the target


def test_many_sources_against_one_asset_are_one_family_and_one_source_against_many_assets_too():
    inbound = {learning.family_of('ETERNALBLUE', f'203.0.113.{i}', '172.31.65.56') for i in range(25)}
    outbound = {learning.family_of('JA3', '172.31.64.80', f'93.184.216.{i}') for i in range(111)}
    assert len(inbound) == len(outbound) == 1
    assert learning.family_of('ETERNALBLUE', '203.0.113.1', '172.31.65.56') != \
        learning.family_of('ETERNALBLUE', '203.0.113.1', '172.31.65.57'), 'a verdict must not reach another asset'


def test_a_false_positive_lowers_a_suricata_alert_by_the_capped_change(conn):
    [alert] = _admit(conn, 1)
    _set_priority(conn, alert, 60.0)
    assert learning.delta_for(conn, alert.id) == 0.0
    _verdict(conn, alert, 'false_positive')
    assert learning.delta_for(conn, alert.id) == -30.0
    assert _priority(conn, alert) == 60.0, 'the stored routing priority is never rewritten'


def test_the_critical_floor_holds_a_critical_suricata_alert_at_70(conn):
    [alert] = _admit(conn, 1)
    _set_priority(conn, alert, 85.0)
    _verdict(conn, alert, 'false_positive')
    assert learning.delta_for(conn, alert.id) == -15.0, '85 - 30 = 55 is below the floor, so it stops at 70'


@pytest.mark.parametrize('outcome, expected', [('confirmed_malicious', 10.0), ('suspicious', 0.0),
                                               ('expected_activity', -15.0), ('false_positive', -30.0)])
def test_each_outcome_maps_to_the_approved_change(conn, outcome, expected):
    [alert] = _admit(conn, 1)
    _set_priority(conn, alert, 50.0)
    _verdict(conn, alert, outcome)
    assert learning.delta_for(conn, alert.id) == expected


def test_family_learning_waits_for_three_agreeing_verdicts_then_moves_unjudged_members(conn):
    alerts = _admit(conn, 5)
    for a in alerts:
        _set_priority(conn, a, 50.0)
    unjudged = alerts[4]
    for count, judged in enumerate(alerts[:3], start=1):
        _verdict(conn, judged, 'false_positive')
        moved = learning.delta_for(conn, unjudged.id)
        if count < 3:
            assert moved == 0.0, f'gate closed after {count} verdicts'
    assert moved < 0, 'three agreeing verdicts open the gate'
    assert moved >= -30.0, 'the family moves inside the guardrail cap'


def test_family_learning_does_not_reach_another_asset(conn):
    alerts = _admit(conn, 3)
    [other] = _admit(conn, 1, dst='198.51.100.99', start=50)
    for a in alerts:
        _verdict(conn, a, 'false_positive')
    assert learning.delta_for(conn, other.id) == 0.0


def test_a_suricata_false_positive_moves_the_alert_down_the_queue(conn):
    """Two alerts of one severity: the verdict target starts above (higher priority), and must end below."""
    first, second = _admit(conn, 2, signature='FTP brute force')
    _set_priority(conn, first, 60.0)
    _set_priority(conn, second, 50.0)
    _, before = operational_queue.queue_page(conn, limit=100, offset=0)
    assert before.index(first.id) < before.index(second.id)
    _verdict(conn, first, 'false_positive')
    _, after = operational_queue.queue_page(conn, limit=100, offset=0)
    assert after.index(first.id) > after.index(second.id)


def test_the_row_shows_the_same_score_the_order_uses(conn):
    from packages.detection.adapters.operational_v2 import read_triage
    from apps.api import routing_routes
    [alert] = _admit(conn, 1)
    _set_priority(conn, alert, 60.0)
    _verdict(conn, alert, 'false_positive')
    row = conn.execute('SELECT * FROM operational_alerts_v2 WHERE id=?', (alert.id,)).fetchone()
    assert routing_routes._effective_priority(conn, row, read_triage(conn, alert.id)).operational_priority == 30.0


def test_no_verdict_leaves_every_suricata_score_unchanged(conn):
    _admit(conn, 4)
    assert learning.all_deltas(conn) == {}


def test_the_shown_priority_moves_but_the_state_version_does_not(conn):
    """The server checks a routing write against the stored state. A verdict delta in the shown priority must
    not change the version the client sends back, or every action after a verdict is refused as stale."""
    from apps.api import routing_routes
    from packages.detection.routing import state_version
    from packages.detection.adapters.operational_v2 import read_triage
    from apps.api.auth import Principal
    [alert] = _admit(conn, 1)
    _set_priority(conn, alert, 60.0)
    _verdict(conn, alert, 'false_positive')
    view = routing_routes._view(conn, alert.id, Principal(user_id=1, username='reviewer', display_name='Reviewer', role='security_analyst'))
    assert view.state.operational_priority == 30.0
    assert view.state_version == state_version(read_triage(conn, alert.id))
