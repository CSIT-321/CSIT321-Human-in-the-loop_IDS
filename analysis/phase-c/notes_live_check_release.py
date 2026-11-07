"""C6 live check, part 2: after g.ang releases the claim, g.ang is not the owner. The notes must stay, and the
add form must be gone. Demo copy on :8014 only."""
import json, time
import notes_live_check as n

tab = n.post('/tabs', sessionKey='c6-release', url=f'{n.WEB}/login')['tabId']
try:
    n.sign_in(tab, 'g.ang', 'analyst-demo')
    n.open_notes(tab)
    n.js(tab, "(() => { const s = document.querySelector('[aria-label=\"Human work status\"]'); [...s.querySelectorAll('button')].find(b => b.textContent === 'Release claim').click(); return 1; })()")
    time.sleep(1)
    n.js(tab, "(() => { const s = document.querySelector('[aria-label=\"Human work status\"]'); [...s.querySelectorAll('button')].find(b => b.textContent === 'Release').click(); return 1; })()")
    time.sleep(3)
    print('work after release:', n.js(tab, "document.querySelector('[aria-label=\"Human work status\"]').innerText.replace(/\\n+/g,' | ')"))
    print('notes after release:', json.dumps(n.open_notes(tab)))
    n.js(tab, "(() => { document.querySelector('[aria-label=\"Investigation notes section\"]').scrollIntoView({block:'center'}); return 1; })()")
    print('shot:', n.shot(tab, 'c6-non-owner.png'))
finally:
    n.requests.delete(f'{n.BASE}/tabs/{tab}', params={'userId': n.USER}, timeout=30)
