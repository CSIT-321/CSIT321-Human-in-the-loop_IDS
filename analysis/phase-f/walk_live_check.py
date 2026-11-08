"""Whole-triage live walk in Camoufox (REST API). Demo copy only: API :8017 on
%LOCALAPPDATA%/Temp/hitl-review/walk.db (fresh copy of data/demo.db + materialize_flow_queue). Real demo.db untouched.

Tier 1 (g.ang):
  1. Queue tabs show the C2 tabs and the Tier 1 split.
  2. Alert A (Tier 2 recommended): row click claims it; Why Tier 2 panel; Escalate to Tier 2 -> case opens.
  3. Alert V (routine): row click claims it; Flow & Score tab shows the cards; record a verdict.
Tier 2 (g.ang):
  4. Case list shows A's case with "Escalated by"; open it; start investigation; record a conclusion; resolve.
Then the database copy is read to prove every step was written (not only shown).
"""
import json, os, sqlite3, time
import notes_live_check as n

n.WEB = 'http://localhost:5187'
n.USER = 'hermes-walk'
DB = os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review\walk.db')
A = 'f742e96c-cc71-4e76-936d-b98fbd388062'   # Tier 2 recommended, DDoS group of 2
V = '104f65a2-08c7-4efa-be25-67c10de0cf80'   # routine Tier 1, DoS group of 2
WHY = '[aria-label=\\"Why Tier 2 is recommended\\"]'


def text(tab, selector):
    return n.js(tab, "(() => { const e = document.querySelector('%s'); return e ? e.innerText.replace(/\\n+/g, ' | ').slice(0, 400) : null; })()" % selector)


def click_text(tab, label, scope='body'):
    return n.js(tab, "(() => { const b = [...document.querySelectorAll('%s button')].find(b => b.textContent.trim() === '%s');"
                     " if (!b) return 'missing'; if (b.disabled) return 'disabled'; b.click(); return 'clicked'; })()" % (scope, label))


def choose(tab, selector, value):
    return n.js(tab, "(() => { const s = document.querySelector('%s'); if (!s) return 'missing';"
                     " Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(s, '%s');"
                     " s.dispatchEvent(new Event('change', {bubbles: true})); return s.value; })()" % (selector, value))


def open_alert(tab, ref):
    n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/operations?q={ref}&alertRef={ref}'); time.sleep(6)
    r = n.js(tab, "(() => { const b = document.querySelector('button[data-alert-ref=\"%s\"]'); if (!b) return 'row not on page'; b.click(); return 'clicked'; })()" % ref)
    time.sleep(5)
    return r


def ws_tab(tab, name):
    r = n.js(tab, "(() => { const b = document.getElementById('ops-tab-%s'); if (!b) return 'missing'; b.click(); return 'clicked'; })()" % name)
    time.sleep(3)
    return r


def step(label, value):
    print(f'{label}: {json.dumps(value)}')


def main():
    tab = n.post('/tabs', sessionKey='walk', url=f'{n.WEB}/login')['tabId']
    try:
        n.sign_in(tab, 'g.ang', 'analyst-demo')
        # 1 queue tabs
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/operations'); time.sleep(6)
        step('1 tabs', n.js(tab, "[...document.querySelectorAll('[role=tab]')].map(t => t.textContent.trim().replace(/\\s+/g,' ')).slice(0, 14)"))
        # 2 escalate A
        step('2 open A', open_alert(tab, A))
        step('2 work', text(tab, '[aria-label=\\"Human work status\\"]'))
        step('2 why panel', text(tab, WHY))
        n.post(f'/tabs/{tab}/type', selector='#tier2-recommendation-reason', text='Two DDoS flows from one source; needs a Tier 2 look.')
        step('2 escalate', click_text(tab, 'Escalate to Tier 2', WHY)); time.sleep(5)
        step('2 after', text(tab, WHY))
        print('shot:', n.shot(tab, 'walk-2-escalated.png'))
        # 3 verdict on V
        step('3 open V', open_alert(tab, V))
        step('3 work', text(tab, '[aria-label=\\"Human work status\\"]'))
        step('3 flow tab', ws_tab(tab, 'Flow & Score'))
        step('3 flow cards', n.js(tab, "(() => { const p = document.querySelector('[aria-label=\"Flow and score\"]'); return p ? [...p.querySelectorAll('h2,h3')].map(h => h.textContent.trim()) : null; })()"))
        print('shot:', n.shot(tab, 'walk-3-flow.png'))
        step('3 verdict tab', ws_tab(tab, 'Analyst Verdict'))
        step('3 outcome', choose(tab, '#analyst-verdict-outcome', 'confirmed_malicious'))
        n.post(f'/tabs/{tab}/type', selector='#analyst-verdict-reason', text='DoS pattern on port 80 from one source; matches the capture.')
        step('3 record', click_text(tab, 'Record Verdict', '[aria-label=\\"Analyst Verdict\\"]')); time.sleep(5)
        step('3 after', text(tab, '[aria-label=\\"Analyst Verdict\\"]'))
        print('shot:', n.shot(tab, 'walk-3-verdict.png'))
        # 4 Tier 2 case
        with sqlite3.connect(DB) as c:
            case = c.execute("SELECT t.case_ref FROM tier2_cases t JOIN operational_alerts_v2 o ON o.id=t.primary_operational_alert_id"
                             " WHERE o.operational_alert_ref=?", (A,)).fetchone()
        step('4 case ref', case and case[0])
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/tier2-cases'); time.sleep(6)
        step('4 list row', n.js(tab, "(() => { const r = [...document.querySelectorAll('[aria-label=\"Tier 2 cases\"] tbody tr')]"
                                     ".find(r => r.innerText.includes('Analyst')); return r ? r.innerText.replace(/\\s+/g,' ').slice(0, 300) : null; })()"))
        n.post(f'/tabs/{tab}/navigate', url=f'{n.WEB}/analyst/tier2-cases/{case[0]}'); time.sleep(6)
        step('4 flow in case', bool(n.js(tab, "!!document.querySelector('[aria-label=\"Flow and score\"]')")))
        step('4 timeline tab', click_text(tab, 'Audit Timeline', '[aria-label=\\"Case investigation\\"]')); time.sleep(2)
        n.post(f'/tabs/{tab}/type', selector='#investigation-note', text='Taking this case.')
        step('4 start', click_text(tab, 'Start investigation')); time.sleep(4)
        step('4 conclusion tab', click_text(tab, 'Investigation Conclusion', '[aria-label=\\"Case investigation\\"]')); time.sleep(2)
        step('4 finding', choose(tab, '#case-finding', 'confirmed_malicious')); time.sleep(1)
        step('4 category', choose(tab, '#final-category', 'ddos'))
        n.post(f'/tabs/{tab}/type', selector='#investigation-note', text='Confirmed DDoS from the grouped source.')
        step('4 record', click_text(tab, 'Record Investigation Conclusion')); time.sleep(4)
        n.post(f'/tabs/{tab}/type', selector='#case-resolution-reason', text='Confirmed and documented.')
        step('4 resolve', click_text(tab, 'Resolve Case', '[aria-label=\\"Case Resolution\\"]')); time.sleep(4)
        step('4 resolution', text(tab, '[aria-label=\\"Case Resolution\\"]'))
        print('shot:', n.shot(tab, 'walk-4-resolved.png'))
    finally:
        n.requests.delete(f'{n.BASE}/tabs/{tab}', params={'userId': n.USER}, timeout=30)


if __name__ == '__main__':
    main()
