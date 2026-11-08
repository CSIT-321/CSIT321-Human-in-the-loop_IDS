"""Prove which database the walk API (:8017) reads, through the API itself. Read-only."""
import os, sqlite3, sys
import httpx as requests

for p in ('data/demo.db', os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review\walk.db')):
    c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
    has = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='alert_groups'").fetchone()[0]
    print(p[-28:], 'groups', c.execute('SELECT COUNT(*) FROM alert_groups').fetchone()[0] if has else 'no table')

s = requests.Client()
r = s.post('http://127.0.0.1:8017/api/auth/login', json={'username': 'g.ang', 'password': 'analyst-demo'}, timeout=30)
print('login', r.status_code)
if r.is_success:
    tok = r.json().get('token') or r.json().get('accessToken')
    h = {'Authorization': f'Bearer {tok}'}
    r = s.get('http://127.0.0.1:8017/api/v2/alerts/summary', headers=h, timeout=60)
    print('summary', r.status_code, str(r.json())[:300] if r.is_success else r.text[:200])
sys.exit(0)
