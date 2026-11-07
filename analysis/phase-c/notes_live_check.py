"""C6 live check in Camoufox via its REST API (the Hermes browser tool kept a dead tab id).
Demo copy only: the API on :8014 uses %LOCALAPPDATA%/Temp/hitl-review/notes-ui.db. Real data/demo.db untouched.

Steps: g.ang opens the claimed alert, adds 2 notes on screen; a second Add on the same note is not sent twice;
then admin (not the owner) sees both notes and no add form. Screenshots go to the review folder.
"""
import json, os, sys, time
import requests

BASE, WEB = 'http://localhost:9377', 'http://localhost:5184'
USER = 'hermes-c6-check'
OUT = os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review')
ALERT = '107a0cf6-a827-4593-98c0-d340d154933d'


def post(path, **body):
    r = requests.post(BASE + path, json={'userId': USER, **body}, timeout=90)
    if r.status_code >= 400: sys.exit(f'{path} -> {r.status_code} {r.text[:300]}')
    return r.json()


def js(tab, expression):
    return post(f'/tabs/{tab}/evaluate', expression=expression)['result']


def shot(tab, name):
    r = requests.get(f'{BASE}/tabs/{tab}/screenshot', params={'userId': USER}, timeout=60)
    r.raise_for_status(); path = os.path.join(OUT, name)
    open(path, 'wb').write(r.content); return path


def sign_in(tab, username, password):
    post(f'/tabs/{tab}/navigate', url=f'{WEB}/login'); time.sleep(3)
    post(f'/tabs/{tab}/type', selector='#username, input[name=username], input[placeholder="e.g. g.ang"]', text=username)
    post(f'/tabs/{tab}/type', selector='input[type=password]', text=password, pressEnter=True)
    time.sleep(4)


def open_notes(tab):
    post(f'/tabs/{tab}/navigate', url=f'{WEB}/analyst/operations?alertRef={ALERT}'); time.sleep(5)
    js(tab, "(() => { document.getElementById('ops-tab-History & Notes').click(); return 1; })()"); time.sleep(3)
    return js(tab, "(() => { const s = document.querySelector('[aria-label=\"Investigation notes section\"]'); return s ? s.innerText : 'no notes section'; })()")


CLICK_ADD = "(() => { [...document.querySelectorAll('[aria-label=\"Investigation notes section\"] button')].find(b => b.textContent === 'Add note').click(); return 1; })()"


def main():
  tab = post('/tabs', sessionKey='c6', url=f'{WEB}/login')['tabId']
  try:
    sign_in(tab, 'g.ang', 'analyst-demo')
    print('g.ang before:', json.dumps(open_notes(tab)))
    work = js(tab, "(() => { const w = document.querySelector('[aria-label=\"Human work status\"]'); return w ? w.innerText.replace(/\\n+/g,' | ') : 'none'; })()")
    print('g.ang work:', work)
    for text in ('Source 172.31.69.29 is a lab host. Traffic to 18.219.211.138:8080 matches the Botnet pattern.',
                 'Asked IT to confirm the lab schedule for 8 Nov.'):
        post(f'/tabs/{tab}/type', selector='[aria-label="Investigation notes section"] textarea', text=text)
        js(tab, CLICK_ADD)  # DOM click: Camoufox's native mouse move times out on this page (see notes_probe.py)
        time.sleep(3)
    print('g.ang after:', json.dumps(js(tab, "document.querySelector('[aria-label=\"Investigation notes section\"]').innerText")))
    js(tab, "(() => { document.querySelector('[aria-label=\"Investigation notes section\"]').scrollIntoView({block:'center'}); return 1; })()")
    print('shot owner:', shot(tab, 'c6-owner.png'))
    post(f'/tabs/{tab}/navigate', url=f'{WEB}/login'); time.sleep(2)
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Sign out'); if (b) b.click(); localStorage.clear(); sessionStorage.clear(); return 1; })()")
    time.sleep(2)
    sign_in(tab, 'admin', 'admin-demo')
    print('admin path:', js(tab, 'location.pathname'))
    print('admin view:', json.dumps(open_notes(tab)))
    js(tab, "(() => { const s = document.querySelector('[aria-label=\"Investigation notes section\"]'); if (s) s.scrollIntoView({block:'center'}); return 1; })()")
    print('shot admin:', shot(tab, 'c6-admin.png'))
  finally:
    requests.delete(f'{BASE}/tabs/{tab}', params={'userId': USER}, timeout=30)


if __name__ == '__main__':
    main()
