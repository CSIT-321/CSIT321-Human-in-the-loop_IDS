"""Run the whole Packet Replay in the live demo with the flow chain in a chosen state, then record facts.

    python run_full.py on|off [base-url]

Resets the Replay workspace, prepares Packet Replay, activates it, sets the program switch, advances all
160 steps through the product API, then prints and writes run_<state>.json beside this file.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import uuid
import urllib.request
from pathlib import Path

BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:5173'
STATE = sys.argv[1]
HERE = Path(__file__).resolve().parent


def call(path: str, token: str | None = None, data=None, timeout: int = 900):
    request = urllib.request.Request(
        BASE + path, data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {token}'} if token else {})},
        method='GET' if data is None else 'POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def admin(token: str, path: str, body: dict, timeout: int = 900):
    status, payload = call(path, token, body, timeout)
    if status != 200:
        raise SystemExit(f'{path} -> {status} {payload}')
    return payload


started = time.time()
token = call('/api/auth/login', data={'username': 'admin', 'password': 'admin-demo'})[1]['token']
admin(token, '/api/admin/workspaces/operational/activate', {'reason': f'Full replay, flow chain {STATE}'})
admin(token, '/api/admin/workspaces/v3-1-replay/reset', {'reason': f'Full replay, flow chain {STATE}'})
admin(token, '/api/admin/workspaces/v3-1-replay/prepare', {'reason': f'Full replay, flow chain {STATE}', 'mode': 'packet'})
state = admin(token, '/api/admin/detection/flow-chain',
              {'reason': f'Full replay, flow chain {STATE}', 'enabled': STATE == 'on'})
print('switch:', state['detection'], flush=True)
admin(token, '/api/admin/workspaces/v3-1-replay/activate', {'reason': f'Full replay, flow chain {STATE}'})
for count in (150, 150):
    body = admin(token, '/api/admin/workspaces/v3-1-replay/advance',
                 {'reason': f'Full replay, flow chain {STATE}', 'requestId': str(uuid.uuid4()),
                  'count': count})
    workspace = body['workspaces'][1]
    print('arrived', workspace['holdoutArrived'], 'queue', workspace['alertCount'], flush=True)
end = admin(token, '/api/admin/workspaces', None) if False else None
final = body if True else None
facts = {'state': STATE, 'detection': body['detection'], 'workspace': body['workspaces'][1],
         'seconds': round(time.time() - started, 1)}
(HERE / f'run_{STATE}.json').write_text(json.dumps(facts, indent=1), encoding='utf-8')
print(json.dumps(facts, indent=1))
