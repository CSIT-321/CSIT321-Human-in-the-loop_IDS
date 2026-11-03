"""Current Admin read projections are role-gated, fixed-source and non-mutating."""
from hashlib import sha256

from fastapi.testclient import TestClient

from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db, models as m


def test_current_admin_reads_are_fixed_source_and_do_not_write(tmp_path):
    path = tmp_path / 'admin.db'
    with db.connect(path) as conn:
        db.create_schema(conn)
    client = TestClient(create_app(path))
    credentials = {}
    for role, username, password in [('admin', 'admin', 'admin-demo'),
                                     ('analyst', 'g.ang', 'analyst-demo'),
                                     ('evaluator', 'evaluator', 'evaluator-demo')]:
        result = client.post('/api/auth/login', json={'username': username, 'password': password})
        assert result.status_code == 200, result.text
        credentials[role] = {'Authorization': 'Bearer ' + result.json()['token']}
    with db.connect(path) as conn:
        password_hash = auth.hash_password('test-only')
        for index in range(1, 4):
            db.insert(conn, m.User(username=f'v3-analyst-{index}', display_name=f'V3 Analyst {index}',
                                   password_hash=password_hash, email=f'v3-replay-{index}@example.test',
                                   role='security_analyst'))
        db.insert(conn, m.User(username='bob', display_name='Bob', password_hash=password_hash,
                               email='bob@example.test', role='security_analyst'))
        db.insert(conn, m.User(username='v3-analyst-4', display_name='Custom Analyst',
                               password_hash=password_hash, email='custom@example.test',
                               role='security_analyst'))
    before = sha256(path.read_bytes()).hexdigest()

    for endpoint in ('overview', 'governance', 'users'):
        route = '/api/admin/' + endpoint
        assert client.get(route).status_code == 401
        assert client.get(route, headers=credentials['analyst']).status_code == 403
        assert client.get(route, headers=credentials['evaluator']).status_code == 403

    overview = client.get('/api/admin/overview', headers=credentials['admin'])
    assert overview.status_code == 200, overview.text
    state = overview.json()
    assert state['detectorSource'] == 'Suricata'
    assert state['activeWorkspaceId'] == 'operational'
    assert state['databaseReady'] and state['workspaceReady']
    assert state['workspaceAlertCount'] == state['operational']['totalAlerts'] == 0
    assert state['operational']['availableWork'] == state['operational']['inReviewWork'] == 0
    assert state['memory'] == {'total': 0, 'active': 0, 'conflictReview': 0}

    governance = client.get('/api/admin/governance', headers=credentials['admin'])
    assert governance.status_code == 200, governance.text
    policy = governance.json()
    assert policy['classification']['version'] == state['classificationPolicyVersion'] == 'suricata-classification-v3'
    assert policy['classification']['conflictPolicy'] == 'unknown_needs_expert'
    assert policy['routing']['version'] == state['routingPolicyVersion'] == 'system-routing-v1'
    assert 'unknown_classification_requires_expert' in policy['routing']['rules']
    assert policy['memory']['version'] == state['memoryPolicyVersion'] == 'triage-memory-v1'
    assert (policy['memory']['minimumSupport'], policy['memory']['minimumAgreementRatio'],
            policy['memory']['maximumConflicts'], policy['memory']['defaultValidityDays']) == (3, 0.67, 0, 30)
    assert policy['autoLearning']['version'] == 'safe-memory-auto-activation-v1'
    assert policy['autoLearning']['activationScope'] == 'exact'
    assert policy['autoLearning']['slidingRenewal'] is False
    assert policy['autoLearning']['postExpiryReactivation'] is False
    assert policy['selectiveReview']['version'] == state['selectiveReviewPolicyVersion'] == 'selective-review-v1'
    assert (policy['selectiveReview']['falsePositiveMinimumSupport'],
            policy['selectiveReview']['contextMaximumAgeHours'],
            policy['selectiveReview']['auditSamplePercent']) == (5, 24, 10)
    assert policy['analystWork'] == {'version': 'analyst-work-claim-v1', 'claimArbitrationWindowMs': 750}
    assert policy['responseExecution'] == 'disabled'
    assert policy['automaticLearningEnabled'] is True
    # A caller cannot choose a path or expose an old policy through a query string.
    assert client.get('/api/admin/governance?path=../../private&version=v1',
                      headers=credentials['admin']).json() == policy

    users = client.get('/api/admin/users', headers=credentials['admin'])
    assert users.status_code == 200, users.text
    account = users.json()['items']
    assert {user['username'] for user in account} == {'admin', 'g.ang', 'bob', 'v3-analyst-4'}
    assert {('admin', 'LIOW CHEE KUANG', 'system_admin'),
            ('g.ang', 'Glenn Ang', 'security_analyst')} <= {
        (user['username'], user['displayName'], user['role']) for user in account}
    assert {(user['username'], user['displayName']) for user in account if user['username'] in ('bob', 'v3-analyst-4')} == {
        ('bob', 'Bob'), ('v3-analyst-4', 'Custom Analyst'),
    }
    assert all(set(user) == {'username', 'displayName', 'role', 'status', 'lastLogin'} for user in account)
    assert 'password' not in users.text.lower() and 'email' not in users.text.lower()
    assert sha256(path.read_bytes()).hexdigest() == before
