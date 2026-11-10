"""Integrity audit of a finished replay: every row is where it should be, and nothing is orphaned.

    python audit_integrity.py <replay.db> <on|off>

Prints PASS/FAIL per check as JSON. Read-only.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

path, state = Path(sys.argv[1]), sys.argv[2]
conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
one = lambda sql, *args: conn.execute(sql, args).fetchone()[0]  # noqa: E731
checks: list[dict] = []


def check(name: str, passed: bool, detail) -> None:
    checks.append({'check': name, 'pass': bool(passed), 'detail': detail})


flows = one('SELECT count(*) FROM alerts')
flow_rows = one('SELECT count(*) FROM flow_data')
queue_flow = one("SELECT count(*) FROM operational_alerts_v2 WHERE source_kind='legacy_flow_alert'")
queue_suri = one("SELECT count(*) FROM operational_alerts_v2 WHERE source_kind='external_nids_alert'")
admitted = one('SELECT count(*) FROM external_operational_admission')
groups = one('SELECT count(*) FROM alert_groups')
members = one('SELECT count(*) FROM alert_group_members')

check('capture delivered in full', flows == 27516 and flow_rows == 27516, {'alerts': flows, 'flow_data': flow_rows})
check('every flow row has its alert', one('SELECT count(*) FROM flow_data f LEFT JOIN alerts a ON a.id=f.alert_id '
                                          'WHERE a.id IS NULL') == 0, 'orphan flow_data rows')
check('no duplicate operational refs',
      one('SELECT count(*) FROM (SELECT operational_alert_ref FROM operational_alerts_v2 '
          'GROUP BY 1 HAVING count(*)>1)') == 0, 'duplicate refs')
check('no duplicate alerts per legacy id',
      one("SELECT count(*) FROM (SELECT legacy_alert_id FROM operational_alerts_v2 WHERE legacy_alert_id IS NOT NULL "
          "GROUP BY 1 HAVING count(*)>1)") == 0, 'duplicate legacy ids')
check('every queue item is routed', one('SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN '
                                        'operational_system_routing s ON s.operational_alert_id=o.id '
                                        'WHERE s.operational_alert_id IS NULL') == 0, 'unrouted items')
check('every queue item has triage state', one('SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN '
                                               'operational_triage_state_v2 t ON t.operational_alert_id=o.id '
                                               'WHERE t.operational_alert_id IS NULL') == 0, 'missing triage')
check('every queue item has a legacy source row',
      one("SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN alerts a ON a.id=o.legacy_alert_id "
          "WHERE o.source_kind='legacy_flow_alert' AND a.id IS NULL") == 0, 'queue item without alert')
check('no flow queue item when the chain is off', state == 'on' or queue_flow == 0, {'flowQueue': queue_flow})
check('both chains queued when on', state == 'off' or (queue_flow > 0 and queue_suri > 0),
      {'flowQueue': queue_flow, 'suricataQueue': queue_suri})
check('suricata queue equals admitted', queue_suri == admitted, {'queue': queue_suri, 'admitted': admitted})
check('groups cover their members',
      one('SELECT count(*) FROM alert_groups g WHERE g.member_count != (SELECT count(*) FROM alert_group_members m '
          'WHERE m.group_id=g.id)') == 0, {'groups': groups, 'members': members})
check('every member resolves to an alert',
      one('SELECT count(*) FROM alert_group_members m LEFT JOIN alerts a ON a.id=m.legacy_alert_id '
          'WHERE a.id IS NULL') == 0, 'orphan members')
check('every group representative is a queue item',
      one('SELECT count(*) FROM alert_groups g LEFT JOIN operational_alerts_v2 o '
          'ON o.id=g.representative_operational_alert_id WHERE o.id IS NULL') == 0, 'missing representative')
check('every tier 2 case points at a tier 2 item',
      one("SELECT count(*) FROM tier2_cases k JOIN operational_triage_state_v2 t "
          "ON t.operational_alert_id=k.primary_operational_alert_id WHERE t.handling_route!='tier2_case'") == 0,
      {'cases': one('SELECT count(*) FROM tier2_cases')})
check('every tier 2 case has state', one('SELECT count(*) FROM tier2_cases k LEFT JOIN tier2_case_state s '
                                         'ON s.case_id=k.id WHERE s.case_id IS NULL') == 0, 'case without state')
check('routing decision matches triage route',
      one('SELECT count(*) FROM operational_system_routing s JOIN operational_triage_state_v2 t '
          "ON t.operational_alert_id=s.operational_alert_id WHERE json_extract(s.routing_decision,'$.route') != t.handling_route") == 0,
      'route mismatch')
check('evidenced rows carry a rule or a model hit (corroborated)',
      one("SELECT count(*) FROM alerts WHERE evidence_class='corroborated' AND "
          "(signature_rules IS NULL OR signature_rules='[]' OR attack_category != ml_predicted_class)") == 0,
      'corroborated inconsistency')
check('model-only rows carry no rule',
      one("SELECT count(*) FROM alerts WHERE evidence_class='ml_only' AND signature_rules NOT IN ('[]','')") == 0,
      'ml_only with rule')
check('unflagged rows are not escalated',
      one("SELECT count(*) FROM operational_alerts_v2 o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
          "JOIN alerts a ON a.id=o.legacy_alert_id WHERE a.evidence_class='none' AND t.handling_route='tier2_case'") == 0,
      'benign escalated')
check('no foreign key violations', conn.execute('PRAGMA foreign_key_check').fetchone() is None, 'fk_check')
check('inbox rows are admitted at most once',
      one('SELECT count(*) FROM (SELECT external_inbox_id FROM external_operational_admission '
          'GROUP BY 1 HAVING count(*)>1)') == 0, 'double admission')
summary = {'state': state, 'queue': {'flow': queue_flow, 'suricata': queue_suri},
           'checks': checks, 'failed': [c['check'] for c in checks if not c['pass']]}
print(json.dumps(summary, indent=1))
(Path(sys.argv[1]).parent / f'audit_{state}.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
