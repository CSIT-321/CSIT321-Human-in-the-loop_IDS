"""Drive one full replay in real time (the 5-second playback tick) and record how the queue grows.

    python run_realtime.py on|off [folder]

Prepares Packet Replay with the program switch in the requested state, activates it, clicks Start, then
polls the product state every 20 s until playback is complete or 25 minutes pass. Writes realtime_<state>.json.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STATE = sys.argv[1]
BASE = 'http://127.0.0.1:8000'
HERE = Path(__file__).resolve().parent


def call(path: str, token: str | None = None, data=None, timeout: int = 300):
    request = urllib.request.Request(
        BASE + path, data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {token}'} if token else {})},
        method='GET' if data is None else 'POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def admin(token: str, path: str, body: dict):
    status, payload = call(path, token, body)
    if status != 200:
        raise SystemExit(f'{path} -> {status} {payload}')
    return payload


token = call('/api/auth/login', data={'username': 'admin', 'password': 'admin-demo'})[1]['token']
admin(token, '/api/admin/workspaces/v3-1-replay/reset', {'reason': f'Real-time run, flow chain {STATE}'})
admin(token, '/api/admin/workspaces/v3-1-replay/prepare', {'reason': f'Real-time run, flow chain {STATE}', 'mode': 'packet'})
state = admin(token, '/api/admin/detection/flow-chain', {'reason': f'Real-time run, flow chain {STATE}',
                                                          'enabled': STATE == 'on'})
print('switch', state['detection'], flush=True)
admin(token, '/api/admin/workspaces/v3-1-replay/activate', {'reason': f'Real-time run, flow chain {STATE}'})
admin(token, '/api/admin/workspaces/v3-1-replay/start', {'reason': f'Real-time run, flow chain {STATE}'})

samples, started = [], time.time()
while time.time() - started < 1500:
    status, body = call('/api/admin/workspaces', token)
    workspace = body['workspaces'][1]
    sample = {'t': round(time.time() - started, 1), 'steps': workspace['holdoutArrived'],
              'queue': workspace['alertCount'], 'suricata': workspace['stagedAlerts'],
              'playback': workspace['playbackState']}
    if not samples or sample['steps'] != samples[-1]['steps']:
        samples.append(sample)
        print(sample, flush=True)
    if workspace['playbackState'] == 'complete':
        break
    time.sleep(20)

facts = {'state': STATE, 'seconds': round(time.time() - started, 1), 'samples': samples}
(HERE / f'realtime_{STATE}.json').write_text(json.dumps(facts, indent=1), encoding='utf-8')
print('done', facts['seconds'], 's', samples[-1] if samples else None)
