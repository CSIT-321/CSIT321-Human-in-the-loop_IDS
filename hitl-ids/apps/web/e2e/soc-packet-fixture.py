"""SOC packet-replay browser fixture: a disposable copy of data/demo.db served by the real API on :8040.

The spec drives the Admin Packet Replay through the UI, so the Replay database is built by the product
(apps/api/packet_replay.py), in <tempdir>/workspaces/v3-1-replay.db. data/demo.db is only copied.

The /__soc helpers are read-only and read the Replay database. They pick the spec's alerts by stored state
(the spec never hard-codes a ref) and read back what the UI wrote, so a step that only looks right fails.
"""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
import uvicorn  # noqa: E402
from apps.api import auth  # noqa: E402
from apps.api.main import create_app  # noqa: E402
from packages.contracts import db  # noqa: E402

FLOW_GROUP = """SELECT o.operational_alert_ref FROM alert_groups g
 JOIN operational_alerts_v2 o ON o.id=g.representative_operational_alert_id
 JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
 LEFT JOIN analyst_work w ON w.operational_alert_id=o.id
 WHERE {where} ORDER BY t.operational_priority DESC, g.member_count DESC, o.operational_alert_ref LIMIT 1"""
SURICATA = """SELECT o.operational_alert_ref FROM operational_alerts_v2 o
 JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
 LEFT JOIN analyst_work w ON w.operational_alert_id=o.id
 WHERE o.source_kind='external_nids_alert' AND {where}
 ORDER BY t.operational_priority DESC, o.operational_alert_ref LIMIT 1"""


def build(path: Path) -> None:
    shutil.copyfile(ROOT / 'data' / 'demo.db', path)
    with closing(db.connect(path)) as c:
        db.migrate(c)
        auth.ensure_demo_accounts(c)
        c.commit()


def serve(path: Path) -> None:
    app = create_app(path)
    replay = path.parent / 'workspaces' / 'v3-1-replay.db'

    def ro():
        c = sqlite3.connect(replay.as_uri() + '?mode=ro', uri=True)
        c.execute('PRAGMA query_only=ON')
        return closing(c)

    @app.get('/__soc/picks')
    def picks():
        with ro() as c:
            one = lambda sql, where: (c.execute(sql.format(where=where)).fetchone() or [None])[0]  # noqa: E731
            ssh = one(SURICATA, "t.handling_route='tier1_review' AND w.operational_alert_id IS NULL AND o.detection_title LIKE '%SSH Scan%'")
            source = c.execute('SELECT source_ip FROM operational_alerts_v2 WHERE operational_alert_ref=?',
                               (ssh,)).fetchone()[0] if ssh else None
            return {
                'suricataSsh': ssh, 'sshSource': source,
                'flowAuto': one(FLOW_GROUP, f"t.handling_route='tier2_case' AND g.grouping_key='{source}'")
                            or one(FLOW_GROUP, "t.handling_route='tier2_case'"),
                'flowRoutine': one(FLOW_GROUP, "t.handling_route='tier1_review' AND g.member_count>1 AND w.operational_alert_id IS NULL"),
                'suricataRelease': one(SURICATA, f"t.handling_route='tier1_review' AND w.operational_alert_id IS NULL "
                                                 f"AND o.operational_alert_ref!='{ssh}'"),
            }

    @app.get('/__soc/facts/{ref}')
    def facts(ref: str):
        with ro() as c:
            c.row_factory = sqlite3.Row
            row = c.execute("""SELECT o.source_kind, o.detection_title, o.source_ip, o.destination_ip, o.destination_port,
                t.handling_route, t.priority_band, t.operational_priority,
                (SELECT g.member_count FROM alert_groups g WHERE g.representative_operational_alert_id=o.id) members
                FROM operational_alerts_v2 o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
                WHERE o.operational_alert_ref=?""", (ref,)).fetchone()
            return dict(row)

    @app.get('/__soc/counts')
    def counts():
        with ro() as c:
            one = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
            return {
                'queue': one('SELECT count(*) FROM operational_alerts_v2'),
                'flow': one("SELECT count(*) FROM operational_alerts_v2 WHERE source_kind='legacy_flow_alert'"),
                'suricata': one("SELECT count(*) FROM operational_alerts_v2 WHERE source_kind='external_nids_alert'"),
                'groups': one('SELECT count(*) FROM alert_groups'),
                'groupMembers': one('SELECT count(*) FROM alert_group_members'),
                'tier2Cases': one('SELECT count(*) FROM tier2_cases'),
                'autoCases': one("SELECT count(*) FROM tier2_cases WHERE decision_source='system_policy'"),
                'autoFlowCases': one("SELECT count(*) FROM tier2_cases k JOIN operational_alerts_v2 o "
                                     "ON o.id=k.primary_operational_alert_id WHERE k.decision_source='system_policy' "
                                     "AND o.source_kind='legacy_flow_alert'"),
            }

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
    with tempfile.TemporaryDirectory(prefix='hitl-soc-packet-') as directory:
        path = Path(directory) / 'operational.db'
        build(path)
        serve(path)
