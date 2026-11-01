"""Complete HTTP inspection inventory; no source database is opened by these tests."""
from contextlib import closing
from hashlib import sha256
import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.api import auth, deps, collection_routes
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.prospective_collection import CollectionConflict
from test_api import client, database
from test_prospective_blockers import old_database


INSPECTION_ROUTES = (
    '/api/v2/alerts/{alertRef}/triage-memory/verdict-state',
    '/api/v2/alerts/{alertRef}/verdict',
    '/api/v2/alerts/{alertRef}/verdict-history',
    '/api/auth/me',
    '/api/alerts',
    '/api/alerts/families',
    '/api/alerts/{alertRef}',
    '/api/alerts/{alertRef}/score-adjustment',
    '/api/alerts/{alertRef}/feedback-history',
    '/api/alerts/{alertRef}/notes',
    '/api/dashboard/breakdowns',
    '/api/entities/ip/{ip}',
    '/api/admin/reports/ips',
    '/api/admin/reports/ip/{ip}',
    '/api/dashboard/summary',
    '/api/audit-log',
    '/api/config/guardrails',
    '/api/evaluation/scenarios',
    '/api/evaluation/runs',
    '/api/evaluation/runs/{runId}',
    '/api/evaluation/runs/{runId}/detection',
    '/api/v2/alerts',
    '/api/v2/alerts/summary',
    '/api/v2/alerts/{alertRef}/triage-state',
    '/api/v2/alerts/{alertRef}/evidence',
    '/api/v2/external-alerts',
    '/api/v2/external-alerts/{inboxId}',
    '/api/v2/tier2/cases',
    '/api/v2/tier2/cases/{caseRef}',
    '/api/v2/tier2/cases/{caseRef}/events',
    '/api/v2/tier2/cases/{caseRef}/responses',
    '/api/v2/triage-memory',
    '/api/v2/triage-memory/{lessonRef}',
    '/api/v2/triage-memory/{lessonRef}/events',
    '/api/v2/alerts/{alertRef}/triage-memory/matches',
    '/api/v2/selective-review/metrics',
    '/api/v2/selective-review',
    '/api/v2/alerts/{alertRef}/selective-review',
    '/api/v2/alerts/{alertRef}/selective-review/events',
    '/api/v2/context/facts',
    '/api/v2/alerts/{alertRef}/context',
    '/api/v2/collection/runs',
    '/api/v2/collection/runs/{runRef}',
    '/api/v2/collection/runs/{runRef}/export',
    '/api/v2/collection/runs/{runRef}/report',
)
DB_FREE_GETS = {'/api/health', '/openapi.json', '/docs', '/docs/oauth2-redirect'}
REF = '00000000-0000-4000-8000-000000000001'


def path_for(route):
    return route.format(alertRef=REF, caseRef=REF, lessonRef=REF, runRef=REF,
                        inboxId=1, ip='192.0.2.1', runId='missing-review-run')


def dependency_calls(dependant):
    return {dependant.call}.union(*(dependency_calls(child) for child in dependant.dependencies))


def fingerprint(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        state = (conn.execute('PRAGMA user_version').fetchone()[0],
                 conn.execute('PRAGMA schema_version').fetchone()[0],
                 conn.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                 sha256('\n'.join(conn.iterdump()).encode()).hexdigest())
    return state, sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def forbid_writable(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('inspection reached a writable/migrating dependency')
    for name in ('connect', 'migrate', 'create_schema'):
        monkeypatch.setattr(db, name, forbidden)


def test_complete_dependency_graph_separates_inspection_and_mutation():
    app = create_app()
    gets = {r.path for r in app.routes if 'GET' in getattr(r, 'methods', set())}
    assert gets == set(INSPECTION_ROUTES) | DB_FREE_GETS
    for route in app.routes:
        if not hasattr(route, 'dependant'):
            continue
        chain = dependency_calls(route.dependant)
        if route.path in INSPECTION_ROUTES and 'GET' in route.methods:
            assert deps.get_readonly_connection in chain, route.path
            assert auth.current_readonly_user in chain, route.path
            assert deps.get_connection not in chain, route.path
            assert auth.current_user not in chain, route.path
        elif route.methods & {'POST', 'PUT', 'PATCH', 'DELETE'}:
            assert deps.get_connection in chain, route.path
            assert deps.get_readonly_connection not in chain, route.path


@pytest.mark.parametrize('route', INSPECTION_ROUTES)
def test_every_inspection_preserves_schema_twelve(tmp_path, monkeypatch, route):
    path = tmp_path/'schema12.db'
    old_database(path, monkeypatch)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        token = auth.encode_token(db.from_row(m.User, conn.execute("SELECT * FROM users WHERE role='system_admin'").fetchone()))
    before = fingerprint(path)
    assert before[0][0] == 12
    assert not any(row[1].startswith('prospective_') for row in before[0][2])
    forbid_writable(monkeypatch)
    with TestClient(create_app(path)) as api:
        response = api.get(path_for(route), headers={'Authorization': 'Bearer '+token})
    assert response.status_code == 503, response.text
    assert response.json()['error']['code'] == 'DATABASE_SCHEMA_UNSUPPORTED'
    assert fingerprint(path) == before


@pytest.mark.parametrize('route', INSPECTION_ROUTES)
def test_every_inspection_refuses_missing_database(tmp_path, monkeypatch, route):
    path = tmp_path/'must-not-create'/'missing.db'
    before = list(tmp_path.rglob('*'))
    forbid_writable(monkeypatch)
    with TestClient(create_app(path)) as api:
        response = api.get(path_for(route), headers={'Authorization': 'Bearer unused-with-missing-database'})
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'DATABASE_MISSING'
    assert list(tmp_path.rglob('*')) == before and not path.parent.exists()


@pytest.mark.parametrize('route', INSPECTION_ROUTES)
def test_current_schema_inspection_uses_one_readonly_connection(database, client, monkeypatch, route):
    before = fingerprint(database)
    forbid_writable(monkeypatch)
    connect = sqlite3.connect
    traces = []
    def readonly(source_uri, **kwargs):
        assert source_uri.endswith('?mode=ro') and kwargs.get('uri') is True
        conn = connect(source_uri, **kwargs)
        trace = []; traces.append(trace); conn.set_trace_callback(trace.append)
        return conn
    with monkeypatch.context() as calls:
        calls.setattr(sqlite3, 'connect', readonly)
        response = client.get(path_for(route), headers={'Authorization': 'Bearer '+client.tokens['admin']})
    assert response.status_code in (200, 404), response.text
    assert len(traces) == 1 and traces[0][0] == 'PRAGMA query_only=ON'
    assert fingerprint(database) == before


@pytest.mark.parametrize('route,role,status', [
    ('/api/auth/me', 'admin', 200),
    ('/api/admin/reports/ip/not-an-ip', 'admin', 400),
    ('/api/admin/reports/ips', 'evaluator', 403),
    ('/api/v2/alerts/'+REF+'/triage-state', 'evaluator', 404),
    ('/api/v2/collection/runs/'+REF, 'evaluator', 409),
])
def test_error_responses_do_not_write(database, client, monkeypatch, route, role, status):
    before = fingerprint(database)
    forbid_writable(monkeypatch)
    if status == 409:
        def conflict(*args): raise CollectionConflict('Injected read conflict, no mutation')
        monkeypatch.setattr(collection_routes.service, 'read_run', conflict)
    response = client.get(route, headers={'Authorization': 'Bearer '+client.tokens[role]})
    assert response.status_code == status, response.text
    assert fingerprint(database) == before


def test_database_free_liveness_and_documentation_do_not_create_database(tmp_path, monkeypatch):
    path = tmp_path/'missing.db'
    forbid_writable(monkeypatch)
    with TestClient(create_app(path)) as api:
        for route in DB_FREE_GETS:
            assert api.get(route).status_code == 200
    assert not list(tmp_path.iterdir())
