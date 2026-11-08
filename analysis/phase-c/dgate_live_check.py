"""Phase D live check in Camoufox via its REST API. Demo copy only (API :8016 on %LOCALAPPDATA%/Temp/hitl-review/cgate-ui.db).

Checks, as g.ang:
  D1  /analyst/tier2-cases shows the status + owner filters and the "Escalated by" column; the API filter answers.
  D2  a case whose primary alert is a flow alert shows the "Flow and score" region.
  D3  POST /findings is gone (404/405); the page has no "Create case" panel.
"""
import json, time
import requests
import notes_live_check as n

n.WEB = 'http://localhost:5186'
n.USER = 'hermes-dgate-check'
API = 'http://localhost:8016'

LIST = """(() => ({ headers: [...document.querySelectorAll('thead th')].map(h => h.textContent.trim()),
  selects: [...document.querySelectorAll('select')].map(s => (s.getAttribute('aria-label') || s.name || '') + '=' + s.value),
  rows: document.querySelectorAll('tbody tr').length,
  firstRow: (document.querySelector('tbody tr') || {}).innerText || null,
  createPanel: document.body.innerText.includes('Create Tier 2 case') }))()"""
CASE = """(() => { const p = document.querySelector('[aria-label="Flow and score"]');
  return { flowRegion: !!p, headings: p ? [...p.querySelectorAll('h2')].map(h => h.textContent.trim()) : [],
           title: (document.querySelector('h1') || {}).textContent || null }; })()"""


def api():
    tok = requests.post(f'{API}/api/auth/login', json={'username': 'g.ang', 'password': 'analyst-demo'}, timeout=30).json()['token']
    h = {'Authorization': f'Bearer {tok}'}
    counts = {s: requests.get(f'{API}/api/v2/tier2/cases', params={'status': s}, headers=h, timeout=30).json()['page']['total']
              for s in ('active', 'open', 'investigating', 'resolved')}
    items = requests.get(f'{API}/api/v2/tier2/cases', params={'status': 'active', 'limit': 200}, headers=h, timeout=30).json()['items']
    flow = [c for c in items if (c.get('snapshot') or {}).get('detector', {}).get('detectorEvidence', {}).get('detectorSource') == 'current_flow']
    ref = (flow or items)[0]['caseRef'] if items else None
    gone = requests.post(f'{API}/api/v2/tier2/cases/{ref}/findings', json={}, headers=h, timeout=30).status_code if ref else None
    return counts, len(items), len(flow), ref, gone


def main():
    counts, active, flows, ref, gone = api()
    print('D1 API counts:', counts, '| active items:', active, '| flow cases:', flows)
    print('D3 POST /findings status:', gone)
    tab = n.post('/tabs', sessionKey='dgate', url=f'{n.WEB}/login')['tabId']
    try:
        n.sign_in(tab, 'g.ang', 'analyst-demo')
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/tier2-cases'); time.sleep(7)
        print('list:', json.dumps(n.js(tab, LIST)))
        print('shot list:', n.shot(tab, 'dgate-list.png'))
        if ref:
            n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/tier2-cases/{ref}'); time.sleep(8)
            print('case:', json.dumps(n.js(tab, CASE)))
            print('shot case:', n.shot(tab, 'dgate-case.png'))
    finally:
        requests.delete(f'{n.BASE}/tabs/{tab}', params={'userId': n.USER}, timeout=30)


if __name__ == '__main__':
    main()
