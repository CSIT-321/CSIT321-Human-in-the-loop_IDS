"""Read the walk copy after walk_live_check.py: every step must be a stored row, not only a screen state."""
import os, sqlite3
DB = os.path.expandvars(r'%LOCALAPPDATA%\Temp\hitl-review\walk.db')
A = 'f742e96c-cc71-4e76-936d-b98fbd388062'
V = '104f65a2-08c7-4efa-be25-67c10de0cf80'
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row


def tables():
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def alert_id(ref):
    return c.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (ref,)).fetchone()[0]


have = tables()
for ref, name in ((A, 'A escalated'), (V, 'V verdict')):
    aid = alert_id(ref)
    print(f'--- {name} ({ref[:8]}) id={aid}')
    print(' state', dict(c.execute('SELECT handling_route, tier2_recommended, decision_source, operational_priority FROM operational_triage_state_v2 WHERE operational_alert_id=?', (aid,)).fetchone()))
    for t in ('analyst_work', 'analyst_work_events'):
        if t in have:
            cols = [r[1] for r in c.execute(f'PRAGMA table_info({t})')]
            rows = c.execute(f'SELECT * FROM {t} WHERE operational_alert_id=? ORDER BY rowid', (aid,)).fetchall()
            keep = [k for k in cols if k in ('status', 'action', 'owner_actor_id', 'outcome', 'created_at', 'finished_at')]
            print(f' {t}', [{k: r[k] for k in keep} for r in rows])
    for t in ('analyst_verdicts', 'tier1_verdicts', 'operational_verdicts'):
        if t in have:
            rows = c.execute(f'SELECT * FROM {t} WHERE operational_alert_id=?', (aid,)).fetchall()
            print(f' {t}', [dict(r) for r in rows][:2])
    rows = c.execute('SELECT action, decision_source, created_at FROM operational_routing_audit WHERE operational_alert_id=? ORDER BY id', (aid,)).fetchall()
    print(' routing_audit', [tuple(r) for r in rows])
    leg = c.execute('SELECT legacy_alert_id FROM operational_alerts_v2 WHERE id=?', (aid,)).fetchone()[0]
    rows = c.execute('SELECT * FROM feedback_events WHERE alert_id=? ORDER BY id', (leg,)).fetchall()
    print(' feedback_events', [{k: r[k] for k in r.keys() if k in ('category', 'reason', 'actor_id', 'adjustment', 'score_delta', 'source')} for r in rows])

print('--- case')
case = c.execute('SELECT t.*, s.status, s.revision FROM tier2_cases t JOIN tier2_case_state s ON s.case_id=t.id '
                 'WHERE t.primary_operational_alert_id=?', (alert_id(A),)).fetchone()
print(' case', {k: case[k] for k in case.keys() if k in ('case_ref', 'decision_source', 'status', 'owner_actor_id', 'revision', 'created_by_actor_id')})
for t in ('tier2_case_events', 'tier2_case_conclusions', 'tier2_case_resolutions'):
    if t in have:
        cols = [r[1] for r in c.execute(f'PRAGMA table_info({t})')]
        rows = c.execute(f'SELECT * FROM {t} WHERE case_id=? ORDER BY rowid', (case['id'],)).fetchall()
        keep = [k for k in cols if k in ('event_type', 'action', 'finding', 'final_attack_category', 'reason', 'actor_id', 'previous_status', 'status', 'kind', 'payload')]
        print(f' {t}', [{k: (str(r[k])[:120] if r[k] is not None else None) for k in keep} for r in rows])
print('users', [tuple(r) for r in c.execute('SELECT id, username, display_name FROM users ORDER BY id LIMIT 4')])
