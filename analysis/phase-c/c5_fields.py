"""C5: real payload shapes of the 3 legacy GETs for one judged flow alert (demo copy only, TestClient)."""
import json, os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from apps.api.main import create_app
from apps.api import auth
from packages.contracts import db, models as m
import sqlite3

path = os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review\c3-ui.db')
conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
# a flow alert with a verdict (C3 live check wrote one), as its operational ref == legacy alert_ref
ref = conn.execute("SELECT a.alert_ref FROM alerts a JOIN feedback_events f ON f.alert_id=a.id ORDER BY f.id DESC LIMIT 1").fetchone()[0]
op = conn.execute("SELECT operational_alert_ref FROM operational_alerts_v2 WHERE legacy_alert_id=(SELECT id FROM alerts WHERE alert_ref=?)", (ref,)).fetchone()
print('legacy alert_ref', ref, '| operational ref', op[0] if op else None, '| equal', op and op[0] == ref)
user = db.from_row(m.User, conn.execute("SELECT * FROM users WHERE username='g.ang'").fetchone())
h = {'Authorization': 'Bearer ' + auth.encode_token(user)}
with TestClient(create_app(path)) as c:
    for suffix in ('', '/score-adjustment', '/feedback-history'):
        r = c.get(f'/api/alerts/{ref}{suffix}', headers=h)
        body = r.json()
        if suffix == '':
            body['flow']['features'] = dict(list(body['flow'].get('features', {}).items())[:3])
            body = {k: body[k] for k in ('flow', 'family', 'feedbackCount') if k in body} | {'alert': {k: body['alert'][k] for k in ('combinedScore', 'detectionScore', 'severity', 'queueClass', 'evidenceClass', 'confidence')}}
        print(suffix or '/', r.status_code, json.dumps(body)[:1400]); print()
