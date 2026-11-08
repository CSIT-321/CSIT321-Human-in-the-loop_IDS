"""E4 (S9-03, S9-04): the evaluation path accepts system_route admissions, and the temporal exporter
coalesces the policy and routing audits one system admission writes at the same instant.

The system admission (admit_system_route) stamps the triage-policy audit and the routing audit with the
same created_at and the same after-state. load_database used to append both, so coherent_history raised
"ambiguous same-time observations" on any database with a system-routed Suricata alert, and the
prospective collector refused system_route admissions with "recorded operational admission is required".
"""
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from packages.contracts import db
from packages.detection.adapters.staging import stage_file
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)
from packages.evaluation.temporal_source import load_database
from test_api import database, client  # noqa: F401
from test_temporal_review import synthetic_archive

FIXTURE = Path(__file__).parent / 'fixtures/suricata-alerts.json'


def test_a_database_with_a_system_routed_admission_exports_a_coherent_archive(database):
    with closing(db.connect(database)) as conn:
        from apps.api import auth
        auth.ensure_demo_accounts(conn)
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        # The current adapter stages a bundled detection, so admission takes the system_route path.
        stage_file(conn, FIXTURE, 'e4-system', capture_scope='e4-system-scope')
        source = conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='e4-system' ORDER BY id LIMIT 1").fetchone()[0]
        review = review_eligibility(conn, source, actor_id=actor, request=EligibilityRequest(
            request_id=uuid4(), expected_review_id=None, decision='accepted', reason='E4 system admission'))
        admit_external(conn, source, actor_id=actor, request=AdmissionRequest(
            request_id=uuid4(), expected_review_id=review['id'], reason='E4 system admission'))
        system = conn.execute("SELECT COUNT(*) FROM operational_routing_audit WHERE action='system_route'").fetchone()[0]
        assert system == 1, 'fixture: the admission went through admit_system_route'
    demo = synthetic_archive('safe_learning')
    archive = load_database(database, demo.policies, '2000-01-01T00:00:00Z', '2100-01-01T00:00:00Z')
    assert any(e.state.operational_alert_id is not None for e in archive.states)
