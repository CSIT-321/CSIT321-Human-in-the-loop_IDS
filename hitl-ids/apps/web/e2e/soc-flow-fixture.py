"""SOC-flow browser fixture: a disposable copy of data/demo.db, grouped and routed by the product's own
scripts/materialize_flow_queue.py, served by the real API. data/demo.db is only read (copied), never written.

The one /__soc helper is read-only. It picks the spec's alerts by their routed state (so the spec never
hard-codes a ref) and reads back what the UI wrote, so the spec proves each step was stored, not only shown.
"""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db

PICK = """SELECT o.operational_alert_ref FROM alert_groups g
 JOIN operational_alerts_v2 o ON o.id=g.representative_operational_alert_id
 JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
 WHERE {where} ORDER BY t.operational_priority DESC, g.member_count DESC, o.operational_alert_ref LIMIT 1"""


def build(path: Path) -> None:
    shutil.copyfile(ROOT / 'data' / 'demo.db', path)
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'materialize_flow_queue.py'), '--database', str(path)],
                   check=True, cwd=ROOT)
    with closing(db.connect(path)) as c:
        auth.ensure_demo_accounts(c)


def serve(path: Path) -> None:
    app = create_app(path)

    def ro():
        c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        c.execute('PRAGMA query_only=ON')
        return closing(c)

    @app.get('/__soc/picks')
    def picks():
        with ro() as c:
            one = lambda where: c.execute(PICK.format(where=where)).fetchone()[0]
            return {'auto': one("t.handling_route='tier2_case'"),
                    'recommended': one("t.handling_route='tier1_review' AND t.tier2_recommended=1"),
                    'routine': one("t.handling_route='tier1_review' AND t.tier2_recommended=0 AND g.member_count>1")}

    @app.get('/__soc/proof/{ref}')
    def proof(ref: str):
        with ro() as c:
            alert = c.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (ref,)).fetchone()[0]
            work = c.execute('SELECT status, owner_name, finished_by_name FROM analyst_work WHERE operational_alert_id=?',
                             (alert,)).fetchone()
            case = c.execute("""SELECT t.case_ref, t.decision_source, s.status FROM tier2_cases t
                LEFT JOIN tier2_case_state s ON s.case_id=t.id WHERE t.primary_operational_alert_id=?""",
                             (alert,)).fetchone()
            return {'work': list(work) if work else None,
                    'notes': [r[0] for r in c.execute('SELECT actor_name FROM operational_alert_notes WHERE operational_alert_id=?', (alert,))],
                    'verdicts': c.execute('SELECT count(*) FROM analyst_verdict_events WHERE operational_alert_id=?', (alert,)).fetchone()[0],
                    'case': list(case) if case else None}

    uvicorn.run(app, host='127.0.0.1', port=8040, log_level='warning')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-soc-flow-') as directory:
        path = Path(directory) / 'soc.db'
        build(path)
        serve(path)
