"""X1 (review finding, pre-existing at f1b74b6): the evaluator role is read-only.

The evaluator audits results; it must not record verdicts, route alerts, write notes or change cases.
Before X1 only some write routes carried a role check, so an evaluator could POST legacy feedback
(review slice 1). This test walks every real write route in the app, so a new route is covered
without editing the test.
"""
from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from apps.api.main import create_app

from test_api import client, database, rows  # noqa: F401  (shared fixtures)

WRITE = {'POST', 'PUT', 'PATCH', 'DELETE'}
# Sign-in issues the token itself; sign-out only ends the caller's own session.
EXEMPT = {'/api/auth/login', '/api/auth/logout'}


def write_routes():
    out = []
    for route in create_app().routes:
        if isinstance(route, APIRoute) and route.path not in EXEMPT:
            for method in sorted(route.methods & WRITE):
                out.append((method, route.path))
    return out


def concrete(path: str) -> str:
    return re.sub(r'\{[^}]+\}', 'x-not-a-real-ref', path)


def token(client, username, password):
    return client.tokens[username]


def test_the_walk_finds_the_known_write_routes():
    found = {path for _, path in write_routes()}
    assert len(found) >= 30
    assert '/api/alerts/{alertRef}/feedback' in found               # the route the review found open
    assert '/api/v2/alerts/{alertRef}/tier2/escalate-case' in found


@pytest.mark.parametrize(('method', 'path'), write_routes())
def test_evaluator_cannot_call_any_write_route(client, method, path):
    headers = {'Authorization': f"Bearer {token(client, 'evaluator', 'evaluator-demo')}"}
    response = client.request(method, concrete(path), json={}, headers=headers)
    assert response.status_code == 403, f'{method} {path} -> {response.status_code} {response.text[:200]}'
    assert response.json()['error']['code'] == 'FORBIDDEN_ROLE'


def test_evaluator_can_still_read(client):
    headers = {'Authorization': f"Bearer {token(client, 'evaluator', 'evaluator-demo')}"}
    assert client.get('/api/alerts', headers=headers).status_code == 200


def test_analyst_write_is_not_blocked_by_the_role_rule(client):
    """The same empty request from an analyst fails on its content (400 or 404), never on the role."""
    headers = {'Authorization': f"Bearer {token(client, 'g.ang', 'analyst-demo')}"}
    response = client.post(concrete('/api/alerts/{alertRef}/feedback'), json={}, headers=headers)
    assert response.status_code in (400, 404), response.text
