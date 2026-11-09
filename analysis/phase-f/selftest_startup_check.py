"""Read-only start-up check: the API on :8000 serves the routed self-test copy, not data/demo.db.
data/demo.db has never been routed, so it has no auto-escalated work; the copy has 3."""
import json
import urllib.request

BASE = 'http://127.0.0.1:8000'


def call(path, token=None, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                 headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


token = call('/api/auth/login', body={'username': 'g.ang', 'password': 'analyst-demo'})['token']
s = call('/api/v2/alerts/summary', token)
keys = ('totalAlerts', 'activeAlerts', 'tier1Review', 'tier1Groups', 'tier1Singles', 'tier2Candidates', 'autoEscalated', 'tier2Cases')
print({k: s.get(k) for k in keys})
print('actors', [a['displayName'] for a in call('/api/auth/actors', token)['items']])
