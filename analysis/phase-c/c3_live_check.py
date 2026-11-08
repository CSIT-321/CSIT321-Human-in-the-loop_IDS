"""C3 live check in Camoufox via its REST API. Demo copy only: the API on :8015 uses
%LOCALAPPDATA%/Temp/hitl-review/c3-ui.db. Real data/demo.db untouched.

Steps (g.ang): open alert A (Tier 2 recommended) -> the claim starts on open; the Why Tier 2 panel shows, with
one Escalate button on the Overview tab. Keep in Tier 1 with "Time constraints" -> panel gone, manual escalation
block back. Open alert B -> Escalate to Tier 2 -> a Tier 2 case opens. Screenshots go to the review folder.
"""
import json, time
import notes_live_check as n

n.WEB = 'http://localhost:5185'
n.USER = 'hermes-c3-check'
A = 'f742e96c-cc71-4e76-936d-b98fbd388062'
B = 'c12d8bb2-46ce-4d38-a0fe-63ffe5398002'
PANEL = '[aria-label=\\"Why Tier 2 is recommended\\"]'

STATE = """(() => {
  const p = document.querySelector('%s');
  const esc = [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Escalate to Tier 2');
  const manual = [...document.querySelectorAll('h3')].some(h => h.textContent === 'Manual Escalation / Override' && !h.closest('[hidden]'));
  const work = document.querySelector('[aria-label=\\"Human work status\\"]');
  return { panel: p ? p.innerText.replace(/\\n+/g, ' | ') : null,
           escalateButtons: esc.filter(b => !b.closest('[hidden]')).length, manualBlock: manual,
           work: work ? work.innerText.replace(/\\n+/g, ' | ') : null };
})()""" % PANEL


def click_in_panel(tab, label):
    return n.js(tab, "(() => { const b = [...document.querySelectorAll('%s button')].find(b => b.textContent.trim() === '%s');"
                     " if (!b || b.disabled) return 'disabled or missing'; b.click(); return 'clicked'; })()" % (PANEL, label))


def open_alert(tab, ref):
    n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/operations?q={ref}&alertRef={ref}'); time.sleep(6)
    # A row click starts the review (claim); opening by URL only shows the alert.
    print('row click:', n.js(tab, "(() => { const b = document.querySelector('button[data-alert-ref=\"%s\"]');"
                                   " if (!b) return 'row not on page'; b.click(); return 'clicked'; })()" % ref))
    time.sleep(5)


def main():
    tab = n.post('/tabs', sessionKey='c3', url=f'{n.WEB}/login')['tabId']
    try:
        n.sign_in(tab, 'g.ang', 'analyst-demo')
        open_alert(tab, A)
        print('A before:', json.dumps(n.js(tab, STATE)))
        n.js(tab, "(() => { document.querySelector('%s').scrollIntoView({block:'center'}); return 1; })()" % PANEL)
        print('shot A open:', n.shot(tab, 'c3-open.png'))
        n.post(f'/tabs/{tab}/type', selector='#tier2-recommendation-reason', text='Time constraints')
        print('keep:', click_in_panel(tab, 'Keep in Tier 1')); time.sleep(4)
        print('A after keep:', json.dumps(n.js(tab, STATE)))
        print('shot A kept:', n.shot(tab, 'c3-kept.png'))
        open_alert(tab, B)
        print('B before:', json.dumps(n.js(tab, STATE)))
        n.post(f'/tabs/{tab}/type', selector='#tier2-recommendation-reason', text='Same DDoS source as alert f742e96c.')
        print('escalate:', click_in_panel(tab, 'Escalate to Tier 2')); time.sleep(5)
        print('B after escalate:', json.dumps(n.js(tab, STATE)))
        print('B route text:', json.dumps(n.js(tab, "(() => { const s = document.querySelector('[aria-label=\\\"System Routing\\\"]'); return s ? s.innerText.slice(0, 300) : null; })()")))
        print('shot B:', n.shot(tab, 'c3-escalated.png'))
    finally:
        n.requests.delete(f'{n.BASE}/tabs/{tab}', params={'userId': n.USER}, timeout=30)


if __name__ == '__main__':
    main()
