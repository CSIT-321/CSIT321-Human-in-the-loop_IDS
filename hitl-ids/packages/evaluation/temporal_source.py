"""Read-only export of immutable database history; no final-state or policy-time inference."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.triage_memory import MemoryLesson
from packages.evaluation.temporal_review import TemporalArchive


def load_database(path, policies, holdout_start, holdout_end):
    # mode=ro prevents writes at SQLite's boundary, even if a future caller attempts one.
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        alerts = [read_projection(conn, r[0]) for r in conn.execute('SELECT id FROM operational_alerts_v2 ORDER BY id')]
        refs = {a.id: a.operational_alert_ref for a in alerts}
        states, contexts, lessons, supports, activations, outcomes, overrides = [], [], [], [], [], [], []
        for row in conn.execute('SELECT * FROM operational_triage_policy_audit ORDER BY id'):
            ref = refs[row['operational_alert_id']]
            states.append(dict(alert_ref=ref, available_at=row['created_at'], state=json.loads(row['after_state'])))
            contexts.append(dict(alert_ref=ref, available_at=row['created_at'], audit_id=row['id'], context=json.loads(row['context_snapshot'])))
        for row in conn.execute('SELECT * FROM operational_routing_audit ORDER BY id'):
            states.append(dict(alert_ref=refs[row['operational_alert_id']], available_at=row['created_at'], state=json.loads(row['after_state'])))
        lesson_refs = {}
        for row in conn.execute('SELECT * FROM triage_memory_lessons ORDER BY id'):
            lesson = MemoryLesson.model_validate_json(row['snapshot'])
            if lesson.created_at != row['created_at']:
                raise ValueError('lesson snapshot timestamp disagrees with immutable row')
            lessons.append(lesson)
            lesson_refs[row['id']] = lesson.lesson_ref
        for row in conn.execute('SELECT * FROM triage_memory_support_events ORDER BY id'):
            supports.append(dict(event_id=f"memory:{row['id']}", lesson_ref=lesson_refs[row['lesson_id']],
                alert_ref=refs[row['source_alert_id']], available_at=row['created_at'], outcome=row['outcome'], relation=row['relation']))
            if row['is_primary']:
                outcomes.append(dict(event_id=f"memory:{row['id']}", alert_ref=refs[row['source_alert_id']],
                    available_at=row['created_at'], outcome=row['outcome']))
        for row in conn.execute('SELECT * FROM triage_memory_decisions ORDER BY id'):
            activations.append(dict(lesson_ref=lesson_refs[row['lesson_id']], available_at=row['created_at'],
                action=row['action'], actor_id=row['actor_id'], reason=row['reason'], valid_from=row['valid_from'], expires_at=row['expires_at']))
        for row in conn.execute("SELECT e.*, c.primary_operational_alert_id FROM tier2_case_events e JOIN tier2_cases c ON c.id=e.case_id WHERE e.action='finding' ORDER BY e.id"):
            outcomes.append(dict(event_id=f"case:{row['id']}", alert_ref=refs[row['primary_operational_alert_id']],
                available_at=row['created_at'], outcome=row['finding']))
        for row in conn.execute("SELECT * FROM selective_review_events WHERE action='require_review' ORDER BY id"):
            overrides.append(dict(alert_ref=refs[row['operational_alert_id']], available_at=row['created_at']))
        return TemporalArchive(data_basis='historical-inputs-unverified', provenance='Immutable SQLite history: '+Path(path).name,
            holdout_start=holdout_start, holdout_end=holdout_end, alerts=alerts, states=states, contexts=contexts,
            policies=policies, lessons=lessons, supports=supports, activations=activations, outcomes=outcomes, overrides=overrides)
