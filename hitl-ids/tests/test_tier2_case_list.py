"""D1: the Tier 2 case list filters by status and owner, in a stable order.

Fixture (test_queue_tier_views.routed): 2 E1 groups auto-escalated by the system policy -> 2 unowned Tier 2 cases.
One case is set to resolved directly in the state table (open -> resolved is allowed; resolved -> any is not).
"""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.contracts import db
from test_analyst_work_claim import headers
from test_queue_tier_views import routed  # noqa: F401  (pytest fixture)
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)

URL = '/api/v2/tier2/cases'


@pytest.fixture
def client(routed):
    with closing(db.connect(str(routed))) as conn:
        first = conn.execute('SELECT id FROM tier2_cases ORDER BY id LIMIT 1').fetchone()[0]
        conn.execute("UPDATE tier2_case_state SET status='resolved' WHERE case_id=?", (first,))
        conn.commit()
    with TestClient(create_app()) as api:
        api.headers.update(headers(str(routed), 1))
        yield api


def refs(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['page']['returned'] == len(body['items'])
    if 'limit' not in params and 'offset' not in params:
        assert body['page']['total'] == len(body['items'])  # the total counts the filtered set, not the table
    return [item['caseRef'] for item in body['items']], [item['status'] for item in body['items']]


def test_status_filter(client):
    every, statuses = refs(client)
    assert len(every) == 2 and sorted(statuses) == ['open', 'resolved']   # guard: the fixture really has both
    assert refs(client, status='active')[1] == ['open']
    assert refs(client, status='resolved')[1] == ['resolved']
    assert refs(client, status='open')[1] == ['open']


def test_owner_filter(client):
    assert len(refs(client, owner='unassigned')[0]) == 2   # system-policy cases have no owner
    assert refs(client, owner='me')[0] == []


def test_order_is_newest_first_and_stable(client):
    first, _ = refs(client)
    assert first == refs(client)[0]
    paged = refs(client, limit=1)[0] + refs(client, limit=1, offset=1)[0]
    assert paged == first


def test_unknown_filter_value_is_rejected(client):
    assert client.get(URL, params={'status': 'closed'}).status_code == 400
    assert client.get(URL, params={'owner': 'someone'}).status_code == 400
