"""C3 (decision Q4, approved 2026-11-08; user choice 2026-11-08 option A): the "Why Tier 2" panel's server rules.

- A Tier 2 recommendation is OPEN only while the alert is in Tier 1 and no analyst has decided on its route
  (decision_source = system_policy). The stored recommendation and its reasons never change; they stay as history.
- "Keep in Tier 1" = the existing reject_tier2 action. After it the recommendation is closed: the panel goes,
  a second reject is refused, and no later policy run can reopen it.
- "Escalate to Tier 2" = the existing atomic tier2/escalate-case with action approve_tier2 (C1 records the +15).
- The view offers an action exactly when the server accepts it, for every actor (Release pattern).
"""
from contextlib import closing
from uuid import uuid4
import json

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection import routing
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.analyst_verdict import record_verdict
from packages.detection.triage_policy_service import apply_triage_policy
from pre_freeze_fixture import event, stage, admit_all
from test_analyst_work_claim import command, headers
from work_claim_fixture import claim_work

REASON = 'E3: score 100 and Brute Force has attack severity 7.5. A Tier 1 analyst confirms before escalation. (2 of 2 members; first shown.)'


@pytest.fixture
def rec(tmp_path, monkeypatch):
    """6 system-routed Tier 1 alerts, each with an open Tier 2 recommendation. Users 1-3 analysts, 4 evaluator, 5 admin."""
    path = tmp_path / 'c3.db'
    with closing(db.connect(path)) as c:
        db.create_schema(c)
        for i, role in enumerate(('security_analyst',) * 3 + ('evaluator', 'system_admin'), 1):
            db.insert(c, m.User(username=f'user{i}', password_hash='test', display_name=f'Analyst {i}',
                                email=f'u{i}@example.test', role=role))
        c.commit()
        stage(c, [event(i, 'SSH brute force') for i in range(1, 7)])
        alerts = admit_all(c)
        c.execute("UPDATE operational_triage_state_v2 SET tier2_recommended=1, tier2_recommendation_reasons=?",
                  (json.dumps([REASON]),))
        c.commit()
    monkeypatch.setenv('HITL_IDS_DB', str(path))
    return path, alerts


def get(client, path, a, actor):
    return client.get(f'/api/v2/alerts/{a.operational_alert_ref}/triage-state', headers=headers(path, actor))


def reject(client, path, a, actor, view, reason='Time constraints; I finish it in Tier 1.'):
    return client.post(f'/api/v2/alerts/{a.operational_alert_ref}/tier2/reject', headers=headers(path, actor),
                       json={'requestId': str(uuid4()), 'expectedStateVersion': view['stateVersion'], 'reason': reason})


def approve(client, path, a, actor, view):
    return client.post(f'/api/v2/alerts/{a.operational_alert_ref}/tier2/escalate-case', headers=headers(path, actor),
                       json={'requestId': str(uuid4()), 'expectedStateVersion': view['stateVersion'],
                             'reason': 'Matches the campaign seen on 14 Feb.', 'action': 'approve_tier2'})


def test_open_only_in_tier1_before_any_analyst_route_decision(rec):
    path, alerts = rec
    with closing(db.connect(path)) as c:
        state = read_triage(c, alerts[0].id)
    assert routing.recommendation_open(state, 'current')
    assert not routing.recommendation_open(state.model_copy(update={'decision_source': 'analyst'}), 'current')
    assert not routing.recommendation_open(state, 'none')                     # not in Tier 1 triage
    assert not routing.recommendation_open(state.model_copy(update={'tier2_recommended': False, 'tier2_recommendation_reasons': ()}), 'current')
    # Historical (not system-routed) rows keep the earlier rule; the panel is never shown for them.
    assert routing.recommendation_open(state.model_copy(update={'decision_source': 'analyst'}), 'historical')


def test_keep_in_tier1_closes_the_recommendation_and_keeps_it_as_history(rec):
    path, alerts = rec
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, 1)
    with TestClient(create_app()) as client:
        before = get(client, path, a, 1).json()
        assert before['tier2RecommendationOpen'] is True
        assert {'approve_tier2', 'reject_tier2'} <= set(before['allowedActions'])
        done = reject(client, path, a, 1, before)
        assert done.status_code == 200, done.text
        after = done.json()['view']
        assert after['tier2RecommendationOpen'] is False
        assert after['state']['handlingRoute'] == 'tier1_review'
        assert after['state']['tier2Recommended'] is True                 # history kept, not erased
        assert after['state']['tier2RecommendationReasons'] == [REASON]
        assert after['work']['status'] == 'in_review' and after['work']['isOwner']   # still on my queue
        assert after['latestDecision']['reason'] == 'Time constraints; I finish it in Tier 1.'
        assert not {'approve_tier2', 'reject_tier2'} & set(after['allowedActions'])
        assert 'manual_escalate' in after['allowedActions']               # the normal escalate path returns
        assert reject(client, path, a, 1, after).status_code == 409       # a second reject is refused


def test_no_later_policy_run_can_reopen_a_closed_recommendation(rec):
    path, alerts = rec
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, 1)
        state = read_triage(c, a.id)
        routing.route_alert(c, a.id, actor_id=1, action='reject_tier2', request=routing.RoutingRequest(
            request_id=uuid4(), expected_state_version=routing.state_version(state), reason='Time constraints'))
        closed = read_triage(c, a.id)
        with pytest.raises(ValueError, match='immutable|cannot overwrite'):   # system-routed rows refuse any policy rerun
            apply_triage_policy(c, a.id, actor_id=1, expected_state=closed)
        assert not routing.recommendation_open(read_triage(c, a.id), 'current')


def test_escalate_from_the_panel_opens_a_case_and_records_the_approval(rec):
    path, alerts = rec
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, 1)
    with TestClient(create_app()) as client:
        done = approve(client, path, a, 1, get(client, path, a, 1).json())
        assert done.status_code == 200, done.text
        body = done.json()
        assert body['view']['state']['handlingRoute'] == 'tier2_case' and body['case']['caseRef']
        assert body['view']['tier2RecommendationOpen'] is False
        assert body['view']['work']['status'] == 'escalated'
    with closing(db.connect(path)) as c:
        assert c.execute("SELECT event_type FROM operational_routing_audit WHERE operational_alert_id=? "
                         "AND action='approve_tier2'", (a.id,)).fetchone()[0] == 'V2_TIER2_APPROVED'


def _offer_matches_server(client, path, a, actor, action):
    view = get(client, path, a, actor).json()
    offered = action in view['allowedActions']
    response = (reject if action == 'reject_tier2' else approve)(client, path, a, actor, view)
    assert response.status_code in (200, 403, 409), response.text
    return offered, response.status_code == 200


@pytest.mark.parametrize('action', ['reject_tier2', 'approve_tier2'])
@pytest.mark.parametrize('case', ['owner', 'other_analyst', 'evaluator', 'admin', 'unclaimed', 'owner_after_verdict'])
def test_the_view_offers_an_action_exactly_when_the_server_accepts_it(rec, case, action):
    path, alerts = rec
    a = alerts[0]
    actor = {'owner': 1, 'other_analyst': 2, 'evaluator': 4, 'admin': 5, 'unclaimed': 1, 'owner_after_verdict': 1}[case]
    with closing(db.connect(path)) as c:
        if case != 'unclaimed':
            claim_work(c, a, 1)
        if case == 'owner_after_verdict':
            record_verdict(c, a.operational_alert_ref, actor_id=1, request=command(c, a))
    with TestClient(create_app()) as client:
        offered, accepted = _offer_matches_server(client, path, a, actor, action)
    assert offered == accepted, f'{case}/{action}: view offers {offered}, server accepts {accepted}'
