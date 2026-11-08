"""E1 (S2-10, S3-12, S4-09, S7-10): one flow alert through the whole triage path, over HTTP, as an analyst does it.

materialize + route (fixture: test_queue_tier_views.routed = real detection -> grouping -> routing)
  -> the alert is in the Tier 1 queue
  -> claim it (POST /work/claim)
  -> record a verdict (POST /verdict)
  -> the approved engine applies it inside the guardrails (alerts.combined_score moves, capped)
  -> the family records the verdict (alert_families)
  -> the queue order changes
And a second flow alert:
  -> claim -> escalate to a Tier 2 case (POST /tier2/escalate-case) -> the case lists it, "Escalated by" = analyst.
Every step reads through the API or the stored row the API writes; nothing calls a package function directly.
"""
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db
from flow_group_fixture import grouped_database  # noqa: F401  (fixture)
from test_analyst_work_claim import headers
from test_queue_tier_views import routed  # noqa: F401  (fixture)


@pytest.fixture
def api(routed):  # noqa: F811
    with TestClient(create_app()) as client:
        client.headers.update(headers(str(routed), 1))
        client.db = str(routed)
        yield client


def queue(api):
    """The whole queue in served order (paged, 200 a page). 'all', because a judged alert leaves 'active'."""
    refs, offset = [], 0
    while True:
        body = api.get('/api/v2/alerts', params={'workScope': 'all', 'limit': 200, 'offset': offset}).json()
        refs += [item['operationalAlertRef'] for item in body['items']]
        offset += 200
        if offset >= body['page']['total']:
            return refs


def tier1_groups(api):
    body = api.get('/api/v2/alerts', params={'handlingRoute': 'tier1_review', 'workScope': 'active', 'limit': 200}).json()
    return [i for i in body['items'] if i.get('groupMemberCount')]


def claim(api, ref):
    work = api.get(f'/api/v2/alerts/{ref}/work').json()
    response = api.post(f'/api/v2/alerts/{ref}/work/claim', json={'requestId': str(uuid4()), 'expectedRevision': work['revision']})
    assert response.status_code == 200, response.text
    assert response.json()['outcome'] == 'claimed'


def legacy_row(api, ref):
    with closing(db.connect(api.db)) as conn:
        return conn.execute("""SELECT a.id, a.detection_score, a.combined_score, a.family_key FROM operational_alerts_v2 o
            JOIN alerts a ON a.id = o.legacy_alert_id WHERE o.operational_alert_ref = ?""", (ref,)).fetchone()


def test_e1_a_flow_alert_from_queue_to_verdict_moves_score_family_and_queue(api):
    groups = tier1_groups(api)
    assert len(groups) >= 2, 'fixture: two Tier 1 flow groups'
    order = queue(api)
    target = min(groups, key=lambda g: order.index(g['operationalAlertRef']))     # the higher-ranked group
    other = next(g for g in groups if g is not target)
    ref = target['operationalAlertRef']
    alert_id, detection, before, family = legacy_row(api, ref)
    assert before == detection, 'fixture: no verdict yet'

    claim(api, ref)
    view = api.get(f'/api/v2/alerts/{ref}/verdict').json()
    assert view['canRecord'] is True
    response = api.post(f'/api/v2/alerts/{ref}/verdict', json={
        'requestId': str(uuid4()), 'expectedRevision': view['revision'], 'expectedStateVersion': view['sourceStateVersion'],
        'outcome': 'false_positive', 'reason': 'E1: benign scanner on the allow list.'})
    assert response.status_code == 200, response.text

    _, _, after, _ = legacy_row(api, ref)
    assert after < before, 'the approved engine lowered the score'
    assert before - after <= 30, 'the guardrail caps a single verdict (max_feedback_reduction)'
    with closing(db.connect(api.db)) as conn:
        events = conn.execute('SELECT category FROM feedback_events WHERE alert_id = ?', (alert_id,)).fetchall()
        assert [e[0] for e in events] == ['mark_false_positive']
        assert conn.execute('SELECT COUNT(*) FROM alert_families WHERE family_key = ?', (family,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE event_type = 'FEEDBACK' AND alert_id = ?",
                            (alert_id,)).fetchone()[0] == 1
    after_order = queue(api)
    assert after_order.index(ref) > after_order.index(other['operationalAlertRef']), 'the false positive moved down'


def test_e1_a_flow_alert_escalated_to_a_tier2_case_appears_in_the_case_list(api):
    ref = tier1_groups(api)[0]['operationalAlertRef']
    claim(api, ref)
    routing = api.get(f'/api/v2/alerts/{ref}/triage-state').json()
    response = api.post(f'/api/v2/alerts/{ref}/tier2/escalate-case', json={
        'requestId': str(uuid4()), 'expectedStateVersion': routing['stateVersion'],
        'reason': 'E1: lateral movement suspected', 'action': 'manual_escalate'})
    assert response.status_code == 200, response.text
    case_ref = response.json()['case']['caseRef']
    cases = api.get('/api/v2/tier2/cases', params={'status': 'active', 'limit': 200}).json()['items']
    mine = next(c for c in cases if c['caseRef'] == case_ref)
    assert mine['primaryOperationalAlertRef'] == ref
    assert mine['snapshot']['routingDecision']['decisionSource'] == 'analyst'
    assert api.get('/api/v2/tier2/cases', params={'status': 'active', 'owner': 'unassigned'}).status_code == 200
