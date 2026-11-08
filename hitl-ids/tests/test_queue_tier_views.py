"""C2 + D4 condition 3 (screen review pack, approved 2026-11-08): the two new queue tabs and the Tier 1 split.

- "Tier 2 candidates" lists the alerts whose Tier 2 recommendation is OPEN (the C3 rule, routing.recommendation_open):
  current Tier 1, recommended, no analyst route decision yet, work still active. After "Keep in Tier 1" the alert
  leaves the tab, though its stored flag stays as history.
- "Auto-escalated" lists Tier 2 cases the system policy opened. An analyst escalation is a Tier 2 case, not
  auto-escalated.
- The Tier 1 tab and the Active Tier 1 KPI count groups and singles apart (D4 condition 3). They add up to tier1Review.
- A row carries its group size, so the screen can say "Group of N".

Fixture (flow_group_fixture + test_flow_routing.prepare_all): 2 E1 groups auto-escalated, 2 E3 candidate groups in
Tier 1, 6 unflagged singles in Tier 1.
"""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.routing import recommendation_open
from packages.detection.tier1_eligibility import tier1_status
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)
from test_analyst_work_claim import headers
from test_flow_routing import prepare_all


@pytest.fixture
def routed(grouped_database, monkeypatch):
    with closing(db.connect(str(grouped_database))) as conn:
        prepare_all(conn)
        db.insert(conn, m.User(username='user1', password_hash='test', display_name='Analyst 1',
                               email='u1@example.test', role='security_analyst'))
        conn.commit()
    monkeypatch.setenv('HITL_IDS_DB', str(grouped_database))
    return grouped_database


def candidates(conn):
    """Representative alert ids of the two candidate groups, in first_seen_at order."""
    return [r[0] for r in conn.execute(
        "SELECT g.representative_operational_alert_id FROM alert_groups g "
        "JOIN operational_triage_state_v2 t ON t.operational_alert_id = g.representative_operational_alert_id "
        "WHERE t.handling_route = 'tier1_review' ORDER BY g.first_seen_at, g.id")]


def keep_in_tier1(conn, alert_id):
    """The stored state after reject_tier2: the analyst decided the route; the flag and reasons stay."""
    conn.execute("UPDATE operational_triage_state_v2 SET decision_source = 'analyst' WHERE operational_alert_id = ?",
                 (alert_id,))
    conn.commit()


def escalate_by_analyst(conn, alert_id):
    stage = conn.execute("SELECT workflow_stage FROM operational_triage_state_v2 WHERE handling_route = 'tier2_case' "
                         "LIMIT 1").fetchone()[0]
    conn.execute("UPDATE operational_triage_state_v2 SET handling_route = 'tier2_case', workflow_stage = ?, "
                 "decision_source = 'analyst' WHERE operational_alert_id = ?", (stage, alert_id))
    conn.commit()


def client_for(path):
    client = TestClient(create_app(path))
    client.headers.update(headers(path, 1))
    return client


def summary(client):
    response = client.get('/api/v2/alerts/summary')
    assert response.status_code == 200, response.text
    return response.json()


def listed(client, **query):
    response = client.get('/api/v2/alerts', params={**query, 'limit': 200})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_summary_counts_the_new_tabs_and_splits_tier1(routed):
    with client_for(routed) as client:
        s = summary(client)
    assert (s['tier2Candidates'], s['autoEscalated'], s['tier2Cases']) == (2, 2, 2)
    assert (s['tier1Groups'], s['tier1Singles'], s['tier1Review']) == (2, 6, 8)


def test_keep_in_tier1_removes_the_alert_from_the_candidates_tab_but_not_from_tier1(routed):
    with closing(db.connect(str(routed))) as conn:
        first, second = candidates(conn)
        keep_in_tier1(conn, first)
        assert read_triage(conn, first).tier2_recommended  # guard: the stored flag stays as history
    with client_for(routed) as client:
        s = summary(client)
        page = listed(client, tier2Candidate=True, workScope='active')
    assert s['tier2Candidates'] == 1 and s['tier1Groups'] == 2
    assert page['page']['total'] == 1
    assert [row['tier2RecommendationOpen'] for row in page['items']] == [True]


def test_an_analyst_escalation_is_a_tier2_case_but_not_auto_escalated(routed):
    with closing(db.connect(str(routed))) as conn:
        escalate_by_analyst(conn, candidates(conn)[0])
    with client_for(routed) as client:
        s = summary(client)
        page = listed(client, handlingRoute='tier2_case', decisionSource='system_policy')
    assert (s['tier2Cases'], s['autoEscalated'], s['tier2Candidates']) == (3, 2, 1)
    assert page['page']['total'] == 2
    assert {row['state']['decisionSource'] for row in page['items']} == {'system_policy'}


def test_the_candidates_filter_and_the_panel_flag_use_the_same_rule_on_every_row(routed):
    with closing(db.connect(str(routed))) as conn:
        first, second = candidates(conn)
        keep_in_tier1(conn, first)
        ids = [r[0] for r in conn.execute('SELECT id FROM operational_alerts_v2')]
        expected = {i for i in ids if recommendation_open(read_triage(conn, i), tier1_status(conn, i, read_triage(conn, i)))}
        refs = dict(conn.execute('SELECT operational_alert_ref, id FROM operational_alerts_v2'))
    with client_for(routed) as client:
        page = listed(client, tier2Candidate=True)
        everything = listed(client)
    assert {refs[row['operationalAlertRef']] for row in page['items']} == expected == {second}
    assert {refs[r['operationalAlertRef']] for r in everything['items'] if r['tier2RecommendationOpen']} == expected


def test_a_row_carries_its_group_size_and_a_single_carries_none(routed):
    with closing(db.connect(str(routed))) as conn:
        sizes = dict(conn.execute('SELECT o.operational_alert_ref, g.member_count FROM operational_alerts_v2 o '
                                  'LEFT JOIN alert_groups g ON g.representative_operational_alert_id = o.id'))
    with client_for(routed) as client:
        rows = listed(client)['items']
    assert len(rows) == 10
    assert {row['operationalAlertRef']: row['groupMemberCount'] for row in rows} == sizes
    assert sorted(v for v in sizes.values() if v) == [1, 4, 5, 5]  # guard: the fixture's real group sizes
    assert list(sizes.values()).count(None) == 6                    # a group of 1 is still a group, not a single
