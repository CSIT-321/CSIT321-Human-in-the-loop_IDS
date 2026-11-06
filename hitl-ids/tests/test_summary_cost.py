"""C8: the queue summary and the review-filtered queue must not evaluate the selective-review policy for every alert.

`read_review` returns `must_review` for any alert with no persisted selective-review decision
(selective_review.py, read_review: `last is None`). So only alerts with at least one row in
`selective_review_events` can be deferred, and only they need the full policy evaluation. These tests pin both:
the shortcut's premise, and that summary / queue_page use it while returning the same numbers.
"""
from contextlib import closing

import pytest

from apps.api import operational_queue
from packages.contracts import db
from packages.detection import selective_review
from test_operational_queue import pristine, queue_db  # noqa: F401  (pytest fixtures)


def reviewed_refs(conn):
    return {row[0] for row in conn.execute(
        'SELECT DISTINCT a.operational_alert_ref FROM selective_review_events e '
        'JOIN operational_alerts_v2 a ON a.id = e.operational_alert_id')}


def counting(monkeypatch):
    calls = []
    real = operational_queue.effective_review

    def spy(conn, ref):
        calls.append(ref)
        return real(conn, ref)
    monkeypatch.setattr(operational_queue, 'effective_review', spy)
    return calls


def test_an_alert_with_no_persisted_review_decision_is_always_must_review(queue_db):
    with closing(db.connect(queue_db)) as conn:
        reviewed = reviewed_refs(conn)
        unreviewed = [r[0] for r in conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2')
                      if r[0] not in reviewed]
        assert unreviewed and reviewed, 'the fixture must hold both kinds'
        for ref in unreviewed:
            assert selective_review.effective_review(conn, ref).disposition == 'must_review', ref


def test_summary_evaluates_the_policy_only_for_alerts_with_a_review_decision(queue_db, monkeypatch):
    with closing(db.connect(queue_db)) as conn:
        reviewed = reviewed_refs(conn)
        calls = counting(monkeypatch)
        result = operational_queue.summary(conn)
    assert set(calls) <= reviewed
    assert len(calls) == len(set(calls)), 'each reviewed alert is evaluated at most once'
    assert (result.no_immediate_review, result.review_required, result.available_work) == (2, 64, 6)


@pytest.mark.parametrize('query, total', [(dict(review_required=True), 64), (dict(review_required=False), 2),
                                          (dict(review_disposition='no_immediate_review'), 2)])
def test_review_filtered_queue_evaluates_only_reviewed_alerts(queue_db, monkeypatch, query, total):
    with closing(db.connect(queue_db)) as conn:
        reviewed = reviewed_refs(conn)
        calls = counting(monkeypatch)
        got, ids = operational_queue.queue_page(conn, limit=50, offset=0, **query)
    assert set(calls) <= reviewed
    assert got == total
