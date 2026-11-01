"""Disposable queue read-model fixture shared by HTTP tests and browser rehearsal.

All detections/cases use real staging/admission. Two no-review rows are explicitly
seeded current-state examples (not a policy experiment); the production policy is untouched.
"""
from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from uuid import uuid4

from apps.api import auth
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import materialize_source
from packages.detection.context_store import collect_fact, FactRequest
from packages.detection.external_admission import review_eligibility, admit_external, EligibilityRequest, AdmissionRequest
from packages.detection.tier2_cases import mutate_case, CaseCommand
from legacy_suricata_fixture import stage_file as stage_compat


def build_queue_fixture(path):
    with closing(db.connect(path)) as conn:
        db.create_schema(conn)
        auth.ensure_demo_accounts(conn)
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        now = m.utc_now()
        collect_fact(conn, actor_id=actor, request=FactRequest(request_id=uuid4(), expected_revision=0,
            subject_type='ip', subject_value='198.51.100.99', context_key='assetCriticality', value='critical',
            observed_at=now-timedelta(seconds=1), valid_from=now-timedelta(minutes=1), expires_at=now+timedelta(hours=12),
            reason='SYNTHETIC critical asset', source_reference='synthetic:queue'))
        template = json.loads((Path(__file__).parent/'fixtures/suricata-correlated.json').read_text(encoding='utf-8'))[0]
        events = []
        groups = [(52, 'Critical SQL injection', 1, '198.51.100.99'), (2, 'Unresolved encrypted pattern', 2, '198.51.100.2'),
                  (2, 'High SSH brute force', 1, '198.51.100.3'), (7, 'Routine port scan', 3, '198.51.100.4'),
                  (2, 'No-review port scan', 4, '198.51.100.5')]
        for count, title, severity, destination in groups:
            for i in range(count):
                event = deepcopy(template)
                event.update(flow_id=len(events)+1000, dest_ip=destination, timestamp=f'2026-10-31T12:{len(events):02d}:00+0000' if len(events)<60 else f'2026-10-31T13:{len(events)-60:02d}:00+0000')
                event['alert'].update(signature=f'SYNTHETIC {title} {i+1:02d}', severity=severity)
                events.append(event)
        eve = Path(path).with_suffix('.eve.json')
        eve.write_text(json.dumps(events), encoding='utf-8')
        stage_file(conn, eve, 'synthetic-queue')
        for row in conn.execute('SELECT id FROM external_alert_inbox ORDER BY id').fetchall():
            review = review_eligibility(conn,row[0],actor_id=actor,request=EligibilityRequest(
                request_id=uuid4(),expected_review_id=None,decision='accepted',reason='SYNTHETIC fixture reviewed'))
            admit_external(conn,row[0],actor_id=actor,request=AdmissionRequest(
                request_id=uuid4(),expected_review_id=review['id'],reason='SYNTHETIC queue admission'))
        with conn:
            conn.execute("UPDATE operational_triage_state_v2 SET handling_route='no_immediate_review', review_required=0, review_reason='SYNTHETIC persisted no-review example' WHERE operational_alert_id IN (SELECT id FROM operational_alerts_v2 WHERE detection_title LIKE '%No-review%')")
        # One case in each currently supported open status.
        case_ref = conn.execute('SELECT case_ref FROM tier2_cases ORDER BY id LIMIT 1').fetchone()[0]
        mutate_case(conn, case_ref, actor_id=actor, action='start', request=CaseCommand(request_id=uuid4(), expected_revision=1, reason='SYNTHETIC investigation'))
        # Historical single-record projection: no current classification/priority is invented.
        compat = deepcopy(template); compat['flow_id'] = 9999
        compat['alert']['signature'] = 'SYNTHETIC Unassigned historical compatibility'
        eve.write_text(json.dumps([compat]), encoding='utf-8')
        stage_compat(conn, eve, 'synthetic-compat')
        materialize_source(conn, 'external_nids_alert', conn.execute('SELECT max(id) FROM external_alert_inbox').fetchone()[0])
        assert conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0] == 66
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 54
        assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0] == 0
