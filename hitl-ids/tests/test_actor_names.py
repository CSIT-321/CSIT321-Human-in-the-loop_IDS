"""SOC accountability: every "who acted" line names the person. /api/auth/actors gives the console the names."""
from test_api import client, database  # noqa: F401  (pytest fixtures)


def _login(c, username='g.ang', password='analyst-demo'):
    token = c.post('/api/auth/login', json={'username': username, 'password': password}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def test_actor_names_returns_display_names_for_every_signed_in_role(client):
    for user, password in (('g.ang', 'analyst-demo'), ('admin', 'admin-demo'), ('evaluator', 'evaluator-demo')):
        r = client.get('/api/auth/actors', headers=_login(client, user, password))
        assert r.status_code == 200, (user, r.text)
        names = {item['id']: item['displayName'] for item in r.json()['items']}
        assert 'Glenn Ang' in names.values()


def test_actor_names_exposes_no_username_email_role_or_hash(client):
    item = client.get('/api/auth/actors', headers=_login(client)).json()['items'][0]
    assert set(item) == {'id', 'displayName'}


def test_actor_names_requires_sign_in(client):
    client.headers.pop('Authorization', None)  # the fixture adds the analyst token to every request
    assert client.get('/api/auth/actors').status_code == 401
