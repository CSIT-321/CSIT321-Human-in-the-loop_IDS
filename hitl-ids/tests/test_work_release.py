"""C7 / decision D5: a claim can be released, and every release is audited.

- The owner releases their own claim (reason optional).
- An administrator releases any analyst's claim, with a reason (required).
- Anyone else is refused. An evaluator is refused by role.
- The release is one transaction: work goes back to `available`, the revision moves by one, and one
  WORK_RELEASED event records who released it, from whom, when the claim started, and why.
- A retry with the same request id changes nothing. A stale revision is refused.
- After a release, another analyst can claim the alert.
"""
from contextlib import closing
from uuid import uuid4
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db
from packages.detection import analyst_work as work
from test_analyst_work_claim import headers, setup  # noqa: F401  (pytest fixture: users 1-3 analysts, 4 evaluator, 5 admin)
from work_claim_fixture import claim_work


def release(c, alert, actor, reason=None, revision=None, request_id=None):
    view = work.read_work(c, alert.id, actor)
    return work.release(c, alert.operational_alert_ref, actor_id=actor, request=work.ReleaseCommand(
        request_id=request_id or uuid4(), expected_revision=view.revision if revision is None else revision,
        reason=reason))


def events(c, alert):
    return [(r['event_type'], r['actor_id'], json.loads(r['detail'])) for r in c.execute(
        "SELECT * FROM analyst_work_events WHERE operational_alert_id=? AND event_type='WORK_RELEASED' ORDER BY id",
        (alert.id,))]


def test_the_owner_releases_and_another_analyst_can_then_claim(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claimed = claim_work(c, a, actor_id=1)
        result = release(c, a, 1)
        assert not result.replayed and result.work.status == 'available' and result.work.owner_actor_id is None
        assert result.work.revision == claimed.revision + 1
        (kind, actor, detail), = events(c, a)
        assert (kind, actor) == ('WORK_RELEASED', 1)
        assert detail['previousOwnerActorId'] == 1 and detail['releasedBy'] == 'owner' and detail['claimedAt']
        assert claim_work(c, a, actor_id=2).owner_actor_id == 2


def test_an_administrator_releases_another_analysts_claim_with_a_reason(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(ValueError, match='reason'):
            release(c, a, 5)
        with pytest.raises(ValueError, match='reason'):
            release(c, a, 5, reason='   ')
        result = release(c, a, 5, reason='Analyst 1 is off shift')
        assert result.work.status == 'available'
        (_, actor, detail), = events(c, a)
        assert actor == 5 and detail['releasedBy'] == 'administrator'
        assert detail['previousOwnerActorId'] == 1 and detail['reason'] == 'Analyst 1 is off shift'


def test_no_one_else_can_release(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(work.WorkConflict, match='Analyst 1'):
            release(c, a, 2, reason='I want it')
        with pytest.raises(PermissionError):
            release(c, a, 4, reason='Evaluator')
        assert work.read_work(c, a.id, 1).is_owner and events(c, a) == []


def test_only_work_in_review_can_be_released_and_the_revision_must_match(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        with pytest.raises(work.WorkConflict, match='In Review'):
            release(c, a, 1)
        view = claim_work(c, a, actor_id=1)
        with pytest.raises(work.WorkConflict, match='changed'):
            release(c, a, 1, revision=view.revision - 1)
        assert work.read_work(c, a.id, 1).is_owner


def test_a_retry_with_the_same_request_changes_nothing(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        request_id = uuid4()
        first = release(c, a, 1, request_id=request_id)
        again = work.release(c, a.operational_alert_ref, actor_id=1, request=work.ReleaseCommand(
            request_id=request_id, expected_revision=first.work.revision - 1, reason=None))
        assert again.replayed and again.work.revision == first.work.revision
        assert len(events(c, a)) == 1
        with pytest.raises(work.WorkConflict, match='requestId'):
            work.release(c, a.operational_alert_ref, actor_id=2, request=work.ReleaseCommand(
                request_id=request_id, expected_revision=0, reason=None))


def test_the_database_refuses_a_silent_release(setup):
    """Back to `available` from `in_review` only with a WORK_RELEASED event in the same transaction."""
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        with pytest.raises(Exception, match='release'):
            c.execute("UPDATE analyst_work SET status='available',revision=revision+1,owner_actor_id=NULL "
                      "WHERE operational_alert_id=?", (a.id,))
        c.rollback()
        assert work.read_work(c, a.id, 1).is_owner


def test_release_over_http(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        view = claim_work(c, a, actor_id=1)
    url = f'/api/v2/alerts/{a.operational_alert_ref}/work/release'
    with TestClient(create_app(path)) as client:
        body = {'requestId': str(uuid4()), 'expectedRevision': view.revision}
        assert client.post(url, headers=headers(path, 2), json=body).status_code == 409
        assert client.post(url, headers=headers(path, 4), json=body).status_code == 403
        assert client.post(url, headers=headers(path, 5), json=body).status_code == 400
        ok = client.post(url, headers=headers(path, 1), json=body)
        assert ok.status_code == 200 and ok.json()['work']['status'] == 'available'
        audit = client.get('/api/audit/current?limit=200', headers=headers(path, 5))
        if audit.status_code == 200:
            assert any(item.get('eventType') == 'WORK_RELEASED' and 'released' in item.get('summary', '')
                       for item in audit.json().get('items', [])), audit.json()


# D5: a claim idle for claimIdleExpiryMinutes (config/analyst-work-expiry-v1.json, 15) is released by the system.
# It happens only on a POST (another claim attempt, or the sweep). A read never expires a claim.

def later(monkeypatch, minutes):
    """Shift the clock forward but keep it moving: the claim loop waits for its round to close."""
    from datetime import datetime, timezone
    shift = work.timedelta(minutes=minutes)
    monkeypatch.setattr(work, 'now', lambda: datetime.now(timezone.utc) + shift)


def try_claim(c, alert, actor_id):
    view = work.read_work(c, alert.id, actor_id)
    with patch.object(work, 'policy', return_value={'version': 'analyst-work-claim-v1', 'claimArbitrationWindowMs': 1}):
        return work.claim(c, alert.operational_alert_ref, actor_id=actor_id,
                          request=work.ClaimCommand(request_id=uuid4(), expected_revision=view.revision))


def test_an_idle_claim_expires_when_another_analyst_claims(setup, monkeypatch):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        later(monkeypatch, 16)
        seen = work.read_work(c, a.id, 2)
        assert seen.owner_actor_id == 1, 'a read never expires a claim'
        assert seen.can_claim and 'idle' in seen.explanation
        assert events(c, a) == [], 'the read wrote nothing'
        assert try_claim(c, a, 2).work.owner_actor_id == 2
        (_, actor, detail), = events(c, a)
        assert actor is None and detail['releasedBy'] == 'expiry' and detail['previousOwnerActorId'] == 1
        assert '15 minutes' in detail['reason']


def test_a_claim_younger_than_the_limit_does_not_expire(setup, monkeypatch):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        later(monkeypatch, 14)
        assert not work.read_work(c, a.id, 2).can_claim
        with pytest.raises(work.WorkConflict, match='Analyst 1'):
            try_claim(c, a, 2)
        assert work.read_work(c, a.id, 1).is_owner and events(c, a) == []


def test_the_sweep_releases_only_idle_claims(setup, monkeypatch):
    path, alerts = setup
    with closing(db.connect(path)) as c:
        claim_work(c, alerts[0], actor_id=1)
        later(monkeypatch, 10)
        try_claim(c, alerts[1], 2)
        later(monkeypatch, 16)
        assert work.expire_idle_claims(c) == 1
        assert work.read_work(c, alerts[0].id, 1).status == 'available'
        assert work.read_work(c, alerts[1].id, 2).is_owner
        assert work.expire_idle_claims(c) == 0

# Release button (C7 screen, layout approved 2026-11-08): the server says who may release, so the web never
# guesses from the role. The rule must match `release()` exactly.

def test_the_work_view_says_who_may_release(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        before = work.read_work(c, a.id, 1)
        assert not before.can_release, 'nothing to release before a claim'
        claim_work(c, a, actor_id=1)
        owner, other, evaluator, admin = (work.read_work(c, a.id, actor) for actor in (1, 2, 4, 5))
        assert owner.can_release and not owner.release_reason_required
        assert not other.can_release and not evaluator.can_release
        assert admin.can_release and admin.release_reason_required
        release(c, a, 1)
        assert not work.read_work(c, a.id, 1).can_release and not work.read_work(c, a.id, 5).can_release


def test_the_view_matches_what_release_accepts(setup):
    """Every actor the view offers the button to succeeds; every other actor is refused."""
    path, alerts = setup
    with closing(db.connect(path)) as c:
        for alert, actor in zip(alerts, (1, 2, 4, 5)):
            claim_work(c, alert, actor_id=3)
            view = work.read_work(c, alert.id, actor)
            try:
                release(c, alert, actor, reason='Shift change' if view.release_reason_required else None)
                accepted = True
            except (work.WorkConflict, PermissionError):
                accepted = False
            assert accepted == view.can_release, (actor, view)


def test_the_view_reports_an_idle_claim(setup, monkeypatch):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
        assert not work.read_work(c, a.id, 5).idle
        later(monkeypatch, 16)
        assert work.read_work(c, a.id, 5).idle and work.read_work(c, a.id, 1).idle
        release(c, a, 1)
        assert not work.read_work(c, a.id, 5).idle


def test_the_api_work_view_carries_the_release_fields(setup):
    path, alerts = setup
    a = alerts[0]
    with closing(db.connect(path)) as c:
        claim_work(c, a, actor_id=1)
    url = f'/api/v2/alerts/{a.operational_alert_ref}/work'
    with TestClient(create_app(path)) as client:
        owner = client.get(url, headers=headers(path, 1)).json()
        admin = client.get(url, headers=headers(path, 5)).json()
    assert (owner['canRelease'], owner['releaseReasonRequired'], owner['idle']) == (True, False, False)
    assert (admin['canRelease'], admin['releaseReasonRequired']) == (True, True)
