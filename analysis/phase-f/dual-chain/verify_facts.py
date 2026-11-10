"""Facts for one finished replay: what arrived, what was flagged, what the analyst can see.

    python verify_facts.py <replay.db> [label]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

path, label = Path(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else 'run')
conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
one = lambda sql, *args: conn.execute(sql, args).fetchone()[0]  # noqa: E731

facts = {'label': label}
facts['flowsArrived'] = one('SELECT count(*) FROM alerts')
facts['flowDataRows'] = one('SELECT count(*) FROM flow_data')
facts['queue'] = {row['source_kind']: row['n'] for row in conn.execute(
    'SELECT source_kind, count(*) n FROM operational_alerts_v2 GROUP BY 1')}
facts['queueTotal'] = one('SELECT count(*) FROM operational_alerts_v2')
facts['byEvidence'] = {row['evidence_class']: row['n'] for row in conn.execute(
    'SELECT evidence_class, count(*) n FROM alerts GROUP BY 1')}
facts['flagged'] = one("SELECT count(*) FROM alerts WHERE evidence_class != 'none'")
facts['unflagged'] = one("SELECT count(*) FROM alerts WHERE evidence_class = 'none'")
facts['groups'] = one('SELECT count(*) FROM alert_groups')
facts['groupMembers'] = one('SELECT count(*) FROM alert_group_members')
facts['tier2'] = {row['source_kind']: row['n'] for row in conn.execute(
    'SELECT o.source_kind, count(*) n FROM tier2_cases k JOIN operational_alerts_v2 o '
    'ON o.id=k.primary_operational_alert_id GROUP BY 1')}
facts['routes'] = {f"{row['source_kind']}|{row['handling_route']}": row['n'] for row in conn.execute(
    'SELECT o.source_kind, t.handling_route, count(*) n FROM operational_alerts_v2 o '
    'JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id GROUP BY 1,2')}
facts['unrouted'] = one('SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN operational_system_routing s '
                        'ON s.operational_alert_id=o.id WHERE s.operational_alert_id IS NULL')
# Flagging consistency: a corroborated alert must carry a rule whose category equals its attack category and a
# model that agrees; an ml_only alert must have no matching rule; an unflagged alert must be low priority.
bad = []
for row in conn.execute("SELECT id, evidence_class, attack_category, ml_predicted_class, combined_score, "
                        "signature_rules FROM alerts WHERE evidence_class != 'none' LIMIT 4000"):
    rules = json.loads(row['signature_rules'] or '[]')
    if row['evidence_class'] == 'corroborated' and (not rules or row['attack_category'] != row['ml_predicted_class']):
        bad.append(('corroborated-mismatch', row['id']))
    if row['evidence_class'] == 'ml_only' and rules:
        bad.append(('ml_only-with-rule', row['id']))
facts['flaggingDefects'] = bad[:20]
facts['flaggingDefectsCount'] = len(bad)
facts['unflaggedWithScore'] = one("SELECT count(*) FROM alerts WHERE evidence_class='none' AND combined_score > 50")
facts['topFlagged'] = [dict(row) for row in conn.execute(
    "SELECT attack_category, evidence_class, combined_score, count(*) n FROM alerts "
    "WHERE evidence_class != 'none' GROUP BY 1,2,3 ORDER BY n DESC LIMIT 6")]
facts['suricata'] = {row['k']: row['n'] for row in conn.execute(
    "SELECT json_extract(classification,'$.attackCategory') k, count(*) n FROM operational_system_routing s "
    "JOIN operational_alerts_v2 o ON o.id=s.operational_alert_id "
    "WHERE o.source_kind='external_nids_alert' GROUP BY 1")}
facts['suricataAdmitted'] = one('SELECT count(*) FROM external_operational_admission')
facts['suricataTitles'] = [row['detection_title'] for row in conn.execute(
    "SELECT detection_title FROM operational_alerts_v2 WHERE source_kind='external_nids_alert' "
    "GROUP BY 1 ORDER BY count(*) DESC LIMIT 5")]
# The chain summary an analyst reads on a flow alert (detector block on the alert row).
row = conn.execute("SELECT detector, explanation FROM alerts WHERE evidence_class='corroborated' "
                   "ORDER BY combined_score DESC LIMIT 1").fetchone()
facts['analystSummarySample'] = {'explanation': row['explanation']}
facts['verdicts'] = one('SELECT count(*) FROM analyst_verdict_events')
print(json.dumps(facts, indent=1, default=str))
(Path(path).parent / f'facts_{label}.json').write_text(json.dumps(facts, indent=1, default=str), encoding='utf-8')
