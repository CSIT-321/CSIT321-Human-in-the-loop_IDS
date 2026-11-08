"""Start a browser fixture API, sign in as g.ang, print one GET's status and body head. Read-only probe.
Usage: python api_probe.py <fixture.py> <port> <path>"""
import subprocess
import sys
import time
from pathlib import Path

import httpx

HITL = Path(__file__).resolve().parents[2] / 'hitl-ids'
fixture, port, path = sys.argv[1], sys.argv[2], sys.argv[3]
server = subprocess.Popen([sys.executable, fixture, '--port', port], cwd=HITL / 'apps/web',
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
base = f'http://127.0.0.1:{port}'
try:
    for _ in range(240):
        try:
            if httpx.get(base + '/api/health', timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if server.poll() is not None:
            print('SERVER EXITED', server.returncode, server.stderr.read()[-1500:])
            sys.exit(1)
        time.sleep(0.5)
    token = httpx.post(base + '/api/auth/login', json={'username': 'g.ang', 'password': 'analyst-demo'}).json()['token']
    r = httpx.get(base + path, headers={'Authorization': f'Bearer {token}'}, timeout=60)
    print(r.status_code, r.text[:700])
finally:
    server.terminate()
