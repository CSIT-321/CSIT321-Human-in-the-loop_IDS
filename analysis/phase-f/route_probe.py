"""Build the routing rehearsal fixture into a temp file and print why each admitted Suricata alert routed where it did.
Read-only probe; data/demo.db is copied by the fixture, never written."""
import sqlite3, sys, tempfile
from pathlib import Path
HITL = Path(r'C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids')
sys.path.insert(0, str(HITL)); sys.path.insert(0, str(HITL / 'scripts'))
import shutil
from serve_routing_rehearsal import build_fixture
from packages.contracts import db
from packages.detection.external_admission import EligibilityRequest, AdmissionRequest, review_eligibility, admit_external
from uuid import uuid4
from contextlib import closing

with tempfile.TemporaryDirectory(prefix='route-probe-') as folder:
    path = Path(folder) / 'probe.db'
    shutil.copy2(HITL / 'data/demo.db', path)
    build_fixture(path)
    with closing(db.connect(path)) as c:
        actor = c.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        staged = c.execute("SELECT i.id, i.sensor_id FROM external_alert_inbox i WHERE NOT EXISTS (SELECT 1 FROM operational_alerts_v2 a "
                           "WHERE a.external_inbox_id=i.id) ORDER BY i.id").fetchall()
        print('staged, not admitted:', len(staged))
        for source_id, raw in staged[:3]:
            review = review_eligibility(c, source_id, actor_id=actor, request=EligibilityRequest(
                request_id=uuid4(), expected_review_id=None, decision='accepted', reason='probe'))
            receipt, _ = admit_external(c, source_id, actor_id=actor, request=AdmissionRequest(
                request_id=uuid4(), expected_review_id=review['id'], reason='probe'))
            aid = receipt['operational_alert_id']
            row = c.execute('SELECT a.detection_title, a.detection_category, t.handling_route, t.operational_priority, t.review_reason '
                            'FROM operational_alerts_v2 a JOIN operational_triage_state_v2 t ON t.operational_alert_id=a.id WHERE a.id=?', (aid,)).fetchone()
            print(tuple(row)[:4]); print('   reason:', row[4])
