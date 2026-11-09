"""Data-flow trace fixture: a disposable copy of data/demo.db, routed by scripts/materialize_flow_queue.py, served by
the real API on :8041. data/demo.db is only copied, never written.

Read-only helpers:
  /__trace/picks         one real record per routing branch, chosen by its stored route (never hard-coded)
  /__trace/state/{ref}   the stored facts of one record at this moment: raw flow, detection, group, routing
                         decision and reasons, Tier 1 work, verdicts, legacy score/feedback, Tier 2 case.
The spec calls /state before and after each action, so each step of the tree shows real before/after data.
Ground truth (data/processed/demo_ground_truth.json) is added for the reader only; the product never sees it.
"""
from contextlib import closing
from pathlib import Path
import json
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

TRUTH = json.loads((ROOT / 'data/processed/demo_ground_truth.json').read_text(encoding='utf-8'))
FEATURES = ('Flow Duration', 'Tot Fwd Pkts', 'Tot Bwd Pkts', 'TotLen Fwd Pkts', 'Flow Byts/s', 'Flow Pkts/s',
            'SYN Flag Cnt', 'Init Fwd Win Byts', 'Timestamp')
REP = """SELECT o.operational_alert_ref FROM operational_alerts_v2 o
 JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
 LEFT JOIN alert_groups g ON g.representative_operational_alert_id=o.id
 JOIN alerts a ON a.id=o.legacy_alert_id WHERE {where}
 ORDER BY COALESCE(g.member_count,1) DESC, o.operational_alert_ref LIMIT 1"""


def build(path: Path) -> None:
    shutil.copyfile(ROOT / 'data' / 'demo.db', path)
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'materialize_flow_queue.py'), '--database', str(path)],
                   check=True, cwd=ROOT)
    with closing(db.connect(path)) as c:
        auth.ensure_demo_accounts(c)


def state(c, ref):
    c.row_factory = sqlite3.Row
    o = c.execute('SELECT * FROM operational_alerts_v2 WHERE operational_alert_ref=?', (ref,)).fetchone()
    a = c.execute('SELECT * FROM alerts WHERE id=?', (o['legacy_alert_id'],)).fetchone()
    f = c.execute('SELECT * FROM flow_data WHERE alert_id=?', (a['id'],)).fetchone()
    feats = json.loads(f['flow_features'] or '{}')
    t = c.execute('SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?', (o['id'],)).fetchone()
    s = c.execute('SELECT * FROM operational_system_routing WHERE operational_alert_id=?', (o['id'],)).fetchone()
    g = c.execute('SELECT * FROM alert_groups WHERE representative_operational_alert_id=?', (o['id'],)).fetchone()
    members = []
    if g:
        members = [r[0] for r in c.execute("""SELECT f.source_record_id FROM alert_group_members gm
            JOIN flow_data f ON f.alert_id=gm.legacy_alert_id WHERE gm.group_id=? ORDER BY gm.occurred_at""", (g['id'],))]
    truth = {}
    for rec in members or [f['source_record_id']]:
        k = TRUTH[rec]['groundTruth'] + ': ' + TRUTH[rec]['attackType']
        truth[k] = truth.get(k, 0) + 1
    w = c.execute('SELECT * FROM analyst_work WHERE operational_alert_id=?', (o['id'],)).fetchone()
    case = c.execute("""SELECT t.case_ref, t.decision_source, t.created_by_actor_id, s.status, s.revision
        FROM tier2_cases t JOIN tier2_case_state s ON s.case_id=t.id WHERE t.primary_operational_alert_id=?""",
                     (o['id'],)).fetchone()
    fb = [dict(r) for r in c.execute("""SELECT category, original_score, requested_delta, actual_delta, guardrail_action, user_id
        FROM feedback_events WHERE alert_id=? ORDER BY id""", (a['id'],))]
    rules = json.loads(a['signature_rules'] or 'null') or []
    return {
        'ref': ref, 'recordId': f['source_record_id'],
        'raw': {'srcIp': f['src_ip'], 'dstIp': f['dst_ip'], 'srcPort': f['src_port'], 'dstPort': f['dst_port'],
                'protocol': f['protocol'], 'duration': f['duration'], 'packets': f['packets'], 'bytes': f['bytes'],
                'features': {k: feats.get(k) for k in FEATURES if k in feats}, 'featureCount': len(feats)},
        'detection': {'signatureRules': [{'rule': r['rule_id'], 'name': r['name'], 'severity': r['severity'],
                                          'class': r['attack_category'],
                                          'conditions': [f"{x['feature']} {x['expected']} -> {x['observed']}" for x in r['matched_conditions']]}
                                         for r in rules],
                      'signatureSeverity': a['signature_severity'], 'mlClass': a['ml_predicted_class'],
                      'mlProbability': a['ml_probability'], 'evidenceClass': a['evidence_class'],
                      'detectionScore': a['detection_score'], 'combinedScore': a['combined_score'],
                      'severity': a['severity'], 'attackCategory': a['attack_category'], 'isCritical': bool(a['is_critical'])},
        'group': {'members': g['member_count'], 'key': g['grouping_key'], 'firstSeen': g['first_seen_at'],
                  'lastSeen': g['last_seen_at']} if g else None,
        'routing': {'route': t['handling_route'], 'stage': t['workflow_stage'], 'priority': t['operational_priority'],
                    'band': t['priority_band'], 'tier2Recommended': bool(t['tier2_recommended']),
                    'reasons': json.loads(t['tier2_recommendation_reasons'] or '[]'), 'reviewReason': t['review_reason'],
                    'decisionSource': t['decision_source'],
                    'classification': json.loads(s['classification']) if s else None},
        'work': {'status': w['status'], 'owner': w['owner_name'], 'finishedBy': w['finished_by_name']} if w else None,
        'verdicts': c.execute('SELECT count(*) FROM analyst_verdict_events WHERE operational_alert_id=?', (o['id'],)).fetchone()[0],
        'legacy': {'combinedScore': a['combined_score'], 'severity': a['severity'], 'feedback': fb},
        'case': dict(case) if case else None,
        'groundTruth': truth,
    }


def serve(path: Path) -> None:
    app = create_app(path)

    def ro():
        c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        c.execute('PRAGMA query_only=ON')
        return closing(c)

    @app.get('/__trace/picks')
    def picks():
        with ro() as c:
            one = lambda where: c.execute(REP.format(where=where)).fetchone()[0]
            return {'auto': one("t.handling_route='tier2_case'"),
                    'candidate': one("t.handling_route='tier1_review' AND t.tier2_recommended=1 AND g.id IS NOT NULL"),
                    'routineGroup': one("t.handling_route='tier1_review' AND t.tier2_recommended=0 AND g.id IS NOT NULL"),
                    # the approved demo's false positive: flagged by the model only, benign in truth
                    'falsePositive': c.execute("""SELECT o.operational_alert_ref FROM operational_alerts_v2 o
                        JOIN flow_data f ON f.alert_id=o.legacy_alert_id WHERE f.source_record_id='AL-00478'""").fetchone()[0],
                    # the approved demo's missed attack: unflagged, Benign by the model, malicious in truth
                    'missed': c.execute("""SELECT o.operational_alert_ref FROM operational_alerts_v2 o
                        JOIN flow_data f ON f.alert_id=o.legacy_alert_id WHERE f.source_record_id='AL-03086'""").fetchone()[0]}

    @app.get('/__trace/state/{ref}')
    def read_state(ref: str):
        with ro() as c:
            return state(c, ref)

    uvicorn.run(app, host='127.0.0.1', port=8041, log_level='warning')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hitl-trace-') as directory:
        path = Path(directory) / 'trace.db'
        build(path)
        serve(path)
