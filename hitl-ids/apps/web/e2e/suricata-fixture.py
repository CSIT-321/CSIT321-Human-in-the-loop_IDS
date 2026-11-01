"""Real API, disposable synthetic database. Never opens data/demo.db or collection."""
import argparse
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

HITL = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HITL))
sys.path.insert(0, str(HITL / 'scripts'))
import uvicorn
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import materialize_source
from packages.detection.external_admission import review_eligibility, admit_external, EligibilityRequest, AdmissionRequest
from packages.detection.context_store import collect_fact, FactRequest
from serve_s16_rehearsal import build_pristine_fixture


def build_fixture(path):
    build_pristine_fixture(path)
    with closing(db.connect(path)) as conn:
        auth.ensure_demo_accounts(conn)
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        now = m.utc_now()
        collect_fact(conn, actor_id=actor, request=FactRequest(request_id=uuid4(), expected_revision=0,
            subject_type='ip', subject_value='198.51.100.99', context_key='assetCriticality', value='critical',
            observed_at=now-timedelta(seconds=1), valid_from=now-timedelta(minutes=1), expires_at=now+timedelta(hours=12),
            reason='SYNTHETIC critical asset fixture, not observed production evidence', source_reference='synthetic:asset-register'))
        stage_file(conn, HITL / 'tests/fixtures/suricata-correlated.json', 'synthetic-correlated-e2e')
        for row in conn.execute('SELECT id FROM external_alert_inbox ORDER BY id').fetchall():
            review = review_eligibility(conn,row[0],actor_id=actor,request=EligibilityRequest(
                request_id=uuid4(),expected_review_id=None,decision='accepted',reason='SYNTHETIC EVE fixture reviewed'))
            admit_external(conn,row[0],actor_id=actor,request=AdmissionRequest(
                request_id=uuid4(),expected_review_id=review['id'],reason='SYNTHETIC browser rehearsal'))
        materialize_source(conn, 'legacy_flow_alert', 478)
        assert conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM prospective_runs').fetchone()[0] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8009)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-suricata-e2e-') as folder:
        path = Path(folder) / 'suricata.db'
        build_fixture(path)
        print(f'Disposable synthetic Suricata database: {path}', flush=True)
        uvicorn.run(create_app(path), host='127.0.0.1', port=args.port, log_level='warning')
