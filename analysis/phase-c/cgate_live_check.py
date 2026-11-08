"""Phase C gate live check in Camoufox via its REST API. Demo copy only: the API on :8016 uses
%LOCALAPPDATA%/Temp/hitl-review/cgate-ui.db (a fresh copy of the routed demo copy). Real data/demo.db untouched.

Checks, as g.ang:
  C2  the queue tabs show "Tier 2 candidates N", "Auto-escalated N" and the Tier 1 split "G groups · S single";
      the Tier 2 candidates tab lists only rows with the TIER 2 RECOMMENDED strip.
  C5  opening a flow alert shows the "Flow & Score" tab; clicking it shows the 7 cards.
  X1  the evaluator's POST to the legacy feedback route returns 403 FORBIDDEN_ROLE (API, same server).
"""
import json, time
import requests
import notes_live_check as n

n.WEB = 'http://localhost:5186'
n.USER = 'hermes-cgate-check'
API = 'http://localhost:8016'
FLOW = 'c12d8bb2-46ce-4d38-a0fe-63ffe5398002'

TABS = """(() => [...document.querySelectorAll('[role=tab]')].map(t => t.textContent.trim().replace(/\\s+/g, ' ')))()"""
ROWS = """(() => { const rows = [...document.querySelectorAll('button[data-alert-ref]')];
  return { rows: rows.length, withStrip: rows.filter(r => r.innerText.includes('TIER 2 RECOMMENDED')).length,
           first: rows[0] ? rows[0].innerText.replace(/\\n+/g, ' | ').slice(0, 300) : null }; })()"""
CARDS = """(() => { const p = document.querySelector('[aria-label="Flow and score"]');
  if (!p) return null;
  return { headings: [...p.querySelectorAll('h2')].map(h => h.textContent.trim()),
           buttons: [...p.querySelectorAll('button')].map(b => b.textContent.trim()), textboxes: p.querySelectorAll('textarea,input[type=text]').length }; })()"""


def click_tab(tab, prefix):
    return n.js(tab, "(() => { const t = [...document.querySelectorAll('[role=tab]')].find(t => t.textContent.trim().startsWith('%s'));"
                     " if (!t) return 'missing'; t.click(); return 'clicked'; })()" % prefix)


def x1():
    tok = requests.post(f'{API}/api/auth/login', json={'username': 'evaluator', 'password': 'evaluator-demo'}, timeout=30).json()['token']
    r = requests.post(f'{API}/api/alerts/{FLOW}/feedback', json={'category': 'confirm_true_positive', 'note': 'x1 live'},
                      headers={'Authorization': f'Bearer {tok}'}, timeout=30)
    return r.status_code, r.json().get('error', {}).get('code')


def main():
    print('X1 evaluator feedback POST:', x1())
    tab = n.post('/tabs', sessionKey='cgate', url=f'{n.WEB}/login')['tabId']
    try:
        n.sign_in(tab, 'g.ang', 'analyst-demo')
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/operations'); time.sleep(7)
        print('tabs:', json.dumps(n.js(tab, TABS)))
        print('shot queue:', n.shot(tab, 'cgate-tabs.png'))
        print('candidates tab:', click_tab(tab, 'Tier 2 candidates')); time.sleep(5)
        print('candidates rows:', json.dumps(n.js(tab, ROWS)))
        print('shot candidates:', n.shot(tab, 'cgate-candidates.png'))
        print('auto tab:', click_tab(tab, 'Auto-escalated')); time.sleep(5)
        print('auto rows:', json.dumps(n.js(tab, ROWS)))
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/operations?q={FLOW}&alertRef={FLOW}'); time.sleep(7)
        print('alert tabs:', json.dumps(n.js(tab, "(() => [...document.querySelectorAll('[aria-label=\"Operational alert sections\"] [role=tab]')].map(t => t.textContent))()")))
        print('flow tab:', click_tab(tab, 'Flow & Score')); time.sleep(5)
        print('cards:', json.dumps(n.js(tab, CARDS)))
        print('shot flow:', n.shot(tab, 'cgate-flow-score.png'))
    finally:
        requests.delete(f'{n.BASE}/tabs/{tab}', params={'userId': n.USER}, timeout=30)


if __name__ == '__main__':
    main()
