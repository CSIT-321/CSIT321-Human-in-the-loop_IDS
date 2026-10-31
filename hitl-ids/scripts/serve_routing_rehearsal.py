"""Test-only V2 fixture preparation on a disposable demo database copy."""
import argparse
from contextlib import closing
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.adapters.operational_v2 import materialize_source, read_triage, read_projection
from packages.detection.adapters.staging import stage_file
from packages.detection.triage_policy import TriageContext
from packages.detection.triage_policy_service import apply_triage_policy
from packages.detection.external_admission import EligibilityRequest,AdmissionRequest,review_eligibility,admit_external


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8002)
    parser.add_argument('--prospective',action='store_true',help='Add an unadmitted synthetic prospective journey fixture')
    parser.add_argument('--pristine', action='store_true', help='Build a disposable synthetic fixture without reading demo.db')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-routing-e2e-') as folder:
        path = Path(folder) / 'routing.db'
        if args.pristine:
            from serve_s16_rehearsal import build_pristine_fixture
            build_pristine_fixture(path)
        else:
            shutil.copy2(HITL / 'data/demo.db', path)
        with closing(db.connect(path)) as conn:
            db.migrate(conn)
            auth.ensure_demo_accounts(conn)
            if args.prospective:
                stage_file(conn,HITL/'tests/fixtures/prospective-collection-demo.json','prospective-demo')
            actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
            for sensor in ('routing-staged', 'routing-recommended', 'routing-reject'):
                stage_file(conn, HITL / 'tests/fixtures/suricata-alerts.json', sensor)
                source_id = conn.execute('SELECT id FROM external_alert_inbox WHERE sensor_id=? ORDER BY id LIMIT 1', (sensor,)).fetchone()[0]
                alert = materialize_source(conn, 'external_nids_alert', source_id)
                if sensor != 'routing-staged':
                    apply_triage_policy(conn, alert.id, actor_id=actor, expected_state=read_triage(conn, alert.id),
                        context=TriageContext(unresolved_by_tier1=True))
            stage_file(conn,HITL/'tests/fixtures/triage-memory-scans.json','memory-demo')
            ids=[r[0] for r in conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='memory-demo' ORDER BY id")]
            for source_id in ids:
                review=review_eligibility(conn,source_id,actor_id=actor,request=EligibilityRequest(
                    request_id=uuid4(),expected_review_id=None,decision='accepted',reason='Disposable memory scenario fixture verified'))
                admit_external(conn,source_id,actor_id=actor,request=AdmissionRequest(
                    request_id=uuid4(),expected_review_id=review['id'],reason='Disposable demo admission; no memory verdict seeded'))
            # Explicit synthetic safety facts for this disposable scenario only. Production admission keeps unknowns.
            stage_file(conn,HITL/'tests/fixtures/selective-review-demo.json','selective-demo')
            safe=TriageContext(asset_criticality='low',repeated_campaign=False,correlated_alert_count=1,
                response_required=False,known_malicious_indicator=False,analyst_escalated=False,
                unresolved_by_tier1=False,evidence_conflict=False,confirmed_malicious=False)
            ids=[r[0] for r in conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='selective-demo' ORDER BY id")]
            for source_id in ids:
                review=review_eligibility(conn,source_id,actor_id=actor,request=EligibilityRequest(
                    request_id=uuid4(),expected_review_id=None,decision='accepted',reason='SYNTHETIC selective-review fixture; safety context is demo-only'))
                receipt,_=admit_external(conn,source_id,actor_id=actor,request=AdmissionRequest(
                    request_id=uuid4(),expected_review_id=review['id'],reason='SYNTHETIC safe context; not observed production evidence'),trusted_context=safe)
                seed_synthetic_facts(conn,read_projection(conn,receipt['operational_alert_id']),safe,m.utc_now())
            if args.pristine:
                # Extra untouched admissions for the additional UI journey; preserve existing routing fixture order.
                stage_file(conn, HITL / 'tests/fixtures/suricata-alerts.json', 'ui-admission')
        print(f'Serving disposable routing fixture: {path}', flush=True)
        uvicorn.run(create_app(path), host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
