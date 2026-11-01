"""Whole-dataset current V2 queue, with no policy/materialization during inspection."""
from contextlib import closing
import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient
from apps.api import auth, operational_queue
from apps.api.main import create_app
from packages.contracts import db, models as m
from operational_queue_fixture import build_queue_fixture
from test_inspection_readonly import fingerprint, forbid_writable


@pytest.fixture(scope='module')
def pristine(tmp_path_factory):
    path = tmp_path_factory.mktemp('queue')/'fixture.db'
    build_queue_fixture(path)
    return path


@pytest.fixture
def queue_db(pristine, tmp_path):
    path = tmp_path/'queue.db'; shutil.copyfile(pristine, path)
    return path


@pytest.fixture
def api(queue_db):
    with closing(db.connect(queue_db)) as conn:
        tokens = {row['username']: auth.encode_token(db.from_row(m.User, row)) for row in conn.execute('SELECT * FROM users')}
    with TestClient(create_app(queue_db)) as client:
        client.tokens = tokens
        client.headers['Authorization'] = 'Bearer '+tokens['g.ang']
        yield client


def page(api, **query):
    response = api.get('/api/v2/alerts', params=query)
    assert response.status_code == 200, response.text
    return response.json()


def test_whole_dataset_summary_overlap_and_readonly_snapshot(api, queue_db, monkeypatch):
    before = fingerprint(queue_db)
    forbid_writable(monkeypatch)
    traces = []; connect = sqlite3.connect
    def traced(*args, **kwargs):
        assert args[0].endswith('?mode=ro')
        conn = connect(*args, **kwargs); conn.set_trace_callback(traces.append); return conn
    monkeypatch.setattr(sqlite3, 'connect', traced)
    response = api.get('/api/v2/alerts/summary')
    assert response.status_code == 200
    assert response.json() == dict(totalAlerts=66, criticalAlerts=54, tier1Review=9, tier2Cases=54,
        expertReview=2, reviewRequired=64, noImmediateReview=2, openTier2Cases=54)
    assert traces.count('BEGIN') == 1 and traces.count('COMMIT') == 1
    assert all(not sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER','REPLACE')) for sql in traces)
    assert len(page(api)['items']) == 50  # KPI totals are not this page.
    monkeypatch.setattr(sqlite3, 'connect', connect)
    assert fingerprint(queue_db) == before


@pytest.mark.parametrize('query,total', [
    ({'handlingRoute':'tier2_case'},54), ({'handlingRoute':'tier1_review'},9),
    ({'routeClass':'EXPERT_REVIEW_REQUIRED'},2), ({'priorityBand':'P1'},54),
    ({'priorityBand':'critical'},54), ({'reviewRequired':True},64),
    ({'reviewRequired':False},2), ({'handlingRoute':'no_immediate_review'},2),
    ({'attackCategory':'web_attack'},52),
    ({'routeClass':'EXPERT_REVIEW_REQUIRED','attackCategory':'unknown_needs_expert'},2),
    ({'handlingRoute':'tier1_review','attackCategory':'web_attack'},0),
    ({'handlingRoute':'tier2_case','priorityBand':'P1','reviewRequired':True,'attackCategory':'web_attack'},52),
])
def test_filters_apply_before_pagination(api, query, total):
    result = page(api, **query, limit=1, offset=0)
    assert result['page'] == dict(total=total, limit=1, offset=0, returned=min(total,1))
    all_rows = page(api, **query, limit=200)['items']
    assert len(all_rows) == total
    if total:
        last = page(api, **query, limit=1, offset=total-1)
        assert last['items'][0] == all_rows[-1]
        assert page(api, **query, offset=total)['items'] == []
    for row in all_rows:
        if 'handlingRoute' in query: assert row['state']['handlingRoute'] == query['handlingRoute']
        if 'reviewRequired' in query: assert row['state']['reviewRequired'] == query['reviewRequired']
        if 'attackCategory' in query: assert row['classification']['attackCategory'] == query['attackCategory']
        if 'routeClass' in query: assert row['systemRouting']['routeClass'] == query['routeClass']
        if 'priorityBand' in query: assert row['state']['priorityBand'] == 'P1'


def test_tier2_second_page_and_search_entire_dataset(api):
    first = page(api, handlingRoute='tier2_case')
    second = page(api, handlingRoute='tier2_case', offset=50)
    assert first['page']['total'] == second['page']['total'] == 54
    assert len(first['items']) == 50 and len(second['items']) == 4
    assert not {r['operationalAlertRef'] for r in first['items']} & {r['operationalAlertRef'] for r in second['items']}
    assert page(api, q='historical compatibility')['page']['total'] == 1
    assert page(api, q="%_' OR 1=1 --")['page']['total'] == 0


def test_default_priority_time_and_reference_order_and_unassigned_last(api):
    rows = page(api, limit=200)['items']
    expected = sorted(rows, key=lambda r: r['operationalAlertRef'])
    expected.sort(key=lambda r: operational_queue.occurred_key(r['detectionSummary']['occurredAt']) or '', reverse=True)
    expected.sort(key=lambda r: r['state']['operationalPriority'] if r['state']['operationalPriority'] is not None else -1, reverse=True)
    assert rows == expected
    assert rows[0]['state']['operationalPriority'] == 95
    assert rows[-1]['state']['operationalPriority'] is None and rows[-1]['classification'] is None
    assert rows[-1]['state']['handlingRoute'] == 'unassigned'
    assert rows[0]['detectionSummary']['relatedSignatureCount'] == 1
    assert rows[0]['detectionSummary']['evidenceTypes'] == ['alert']


def test_exact_requested_scores_ties_offsets_microseconds_and_invalid_priority():
    # Minimal read-query tables isolate ordering from immutable evidence construction.
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.executescript('''CREATE TABLE operational_alerts_v2(id,operational_alert_ref,occurred_at);
            CREATE TABLE operational_triage_state_v2(operational_alert_id,operational_priority);
            CREATE TABLE operational_system_routing(operational_alert_id);''')
        for i, score, stamp, ref in [(1,95,'2026-10-31T12:00:00.000001+08:00','z'),
                (2,95,'2026-10-31T04:00:00.000002Z','b'), (3,72,'2026-11-01T00:00:00Z','c'),
                (4,60,'2026-11-02T00:00:00Z','d'), (5,40,'2026-11-03T00:00:00Z','e'),
                (6,95,'2026-10-31T04:00:00.000002Z','a'), (7,None,'invalid','g'), (8,'invalid','invalid','h')]:
            conn.execute('INSERT INTO operational_alerts_v2 VALUES (?,?,?)',(i,ref,stamp))
            conn.execute('INSERT INTO operational_triage_state_v2 VALUES (?,?)',(i,score))
        assert operational_queue.queue_page(conn,limit=50,offset=0) == (8,[6,2,1,3,4,5,7,8])


@pytest.mark.parametrize('query', [{'handlingRoute':'bogus'}, {'routeClass':'bogus'}, {'priorityBand':'P0'},
    {'attackCategory':'benign'}, {'sort':'confidence'}, {'q':'x'*201}, {'limit':201}, {'offset':-1}])
def test_invalid_filters_rejected(api, query):
    assert api.get('/api/v2/alerts',params=query).status_code == 400


@pytest.mark.parametrize('role',['g.ang','admin','evaluator'])
def test_current_authenticated_read_roles(api, role):
    for path in ('/api/v2/alerts/summary','/api/v2/alerts'):
        response = api.get(path,headers={'Authorization':'Bearer '+api.tokens[role]})
        assert response.status_code == 200
        if role == 'evaluator' and path.endswith('alerts'): assert all(not row['allowedActions'] for row in response.json()['items'])


def test_missing_forged_and_disabled_auth_rejected(api, queue_db):
    for token in ('', 'Bearer forged'):
        assert api.get('/api/v2/alerts/summary',headers={'Authorization':token}).status_code == 401
    with closing(db.connect(queue_db)) as conn:
        with conn: conn.execute("UPDATE users SET status='inactive' WHERE username='g.ang'")
    assert api.get('/api/v2/alerts/summary').status_code == 401


def test_empty_current_dataset(tmp_path):
    path = tmp_path/'empty.db'
    with closing(db.connect(path)) as conn:
        db.create_schema(conn); auth.ensure_demo_accounts(conn)
        token = auth.encode_token(db.from_row(m.User, conn.execute("SELECT * FROM users WHERE username='g.ang'").fetchone()))
    with TestClient(create_app(path)) as api:
        data = api.get('/api/v2/alerts/summary',headers={'Authorization':'Bearer '+token}).json()
    assert len(data) == 8 and set(data.values()) == {0}
