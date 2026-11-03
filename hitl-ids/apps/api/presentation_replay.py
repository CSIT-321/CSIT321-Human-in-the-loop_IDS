"""Frozen-input, oracle-blind presentation replay using current product commands."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from apps.api import auth
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.triage_policy import TriageContext
from packages.detection import analyst_work, selective_review, triage_memory
from packages.detection.analyst_verdict import VerdictCommand, read_verdict, record_verdict
from scripts.protocol_v3.common import SENSOR, SCOPE

REPOSITORY = Path(__file__).resolve().parents[3]
WORKLOAD = REPOSITORY / 'evaluation/protocol-v3.1/workload/operational-workload.jsonl'
STRUCTURE = REPOSITORY / 'evaluation/protocol-v3.1/expected/workload-structure.json'
CONTEXTS = REPOSITORY / 'evaluation/protocol-v3.1/workload/trusted-context.json'
LEARNING = REPOSITORY / 'evaluation/protocol-v3.1-run-001/adaptive/feedback.jsonl'
INITIAL_HOLDOUT = 10
RATE_SECONDS = 5


class OneRecord:
    def __init__(self, record): self.record = record
    def read_text(self, **_): return json.dumps([self.record])


def inputs():
    raw = WORKLOAD.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    structure = json.loads(STRUCTURE.read_text(encoding='utf-8'))
    contexts = json.loads(CONTEXTS.read_text(encoding='utf-8'))
    # Only the first 40 Learning lines are opened. Holdout feedback is never read.
    with LEARNING.open(encoding='utf-8') as source:
        feedback = [json.loads(source.readline()) for _ in range(40)]
    if len(rows) != 200 or len(structure) != 200 or len(feedback) != 40:
        raise ValueError('Frozen V3.1 workload / Learning structure is not 200 / 40')
    if any(meta['index'] != i or meta['phase'] != ('learning' if i <= 40 else 'holdout')
           for i, meta in enumerate(structure, 1)):
        raise ValueError('Frozen workload order or phase boundary changed')
    if any(item['index'] != i or item['phase'] != 'learning' or item['alertRef'] != structure[i-1]['alertRef']
           or item.get('explicitOverride') for i, item in enumerate(feedback, 1)):
        raise ValueError('Frozen Learning feedback does not match the 40 input identities')
    return rows, structure, contexts, feedback, hashlib.sha256(raw).hexdigest()


def arrival_order(structure):
    # A fixed presentation order. The first 10 remain chronological; one Unknown follows
    # early. Stratum is used only to select order, never for classification or routing.
    remaining = list(range(50, 200))
    unknown = next(i for i in remaining if structure[i]['stratum'] == 'unknown_tier2')
    remaining.remove(unknown)
    return list(range(40, 50)) + [unknown] + remaining


def _id(prefix: str, ref: str):
    return uuid5(NAMESPACE_URL, f'presentation-v31:{prefix}:{ref}')


def arrive(conn: sqlite3.Connection, index: int, rows, structure, contexts, admin_id: int):
    """Idempotent per identity, including recovery after interruption between source steps."""
    meta = structure[index]
    ref = meta['alertRef']
    existing = conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (ref,)).fetchone()
    if existing:
        if contexts.get(ref) and not conn.execute(
                "SELECT 1 FROM trusted_context_facts WHERE json_extract(snapshot,'$.subjectValue')=? "
                "AND json_extract(snapshot,'$.sourceType')='synthetic_fixture' LIMIT 1", (ref,)).fetchone():
            seed_synthetic_facts(conn, read_projection(conn, existing['id']),
                                 TriageContext.model_validate(contexts[ref]), m.utc_now())
        return ref
    stage_file(conn, OneRecord(rows[index]), SENSOR, capture_scope=SCOPE)
    inbox = conn.execute('SELECT id FROM external_alert_inbox WHERE canonical_alert_id=?', (ref,)).fetchone()
    if inbox is None:
        raise ValueError(f'Frozen record {index+1} did not preserve its canonical alert identity')
    inbox_id = inbox['id']
    review = conn.execute('SELECT id,decision FROM external_eligibility_review WHERE external_inbox_id=? ORDER BY id DESC LIMIT 1',
                          (inbox_id,)).fetchone()
    if review is None:
        review = review_eligibility(conn, inbox_id, actor_id=admin_id, request=EligibilityRequest(
            request_id=_id('eligibility', ref), expected_review_id=None, decision='accepted',
            reason='Presentation Replay frozen Suricata source accepted'))
        review_id = review['id']
    else:
        if review['decision'] != 'accepted': raise ValueError('Frozen source was held during Replay')
        review_id = review['id']
    receipt = conn.execute('SELECT operational_alert_id FROM external_operational_admission WHERE external_inbox_id=?',
                           (inbox_id,)).fetchone()
    if receipt is None:
        receipt, _ = admit_external(conn, inbox_id, actor_id=admin_id, request=AdmissionRequest(
            request_id=_id('admission', ref), expected_review_id=review_id,
            reason='Presentation Replay chronological operational arrival'))
        alert_id = receipt['operational_alert_id']
    else:
        alert_id = receipt['operational_alert_id']
    alert = read_projection(conn, alert_id)
    if str(alert.operational_alert_ref) != ref:
        raise ValueError('Operational alert identity differs from frozen workload')
    if contexts.get(ref):
        # Current trusted-fact producer, as used by the official runner; no outcome is supplied.
        seed_synthetic_facts(conn, alert, TriageContext.model_validate(contexts[ref]), m.utc_now())
    return ref


def build(path: Path, admin_name: str):
    rows, structure, contexts, feedback, source_hash = inputs()
    conn = db.connect(path)
    try:
        db.create_schema(conn)
        auth.ensure_demo_accounts(conn)
        for index in range(1, 4):
            username = f'v3-analyst-{index}'
            if not conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                db.insert(conn, m.User(username=username, display_name=f'V3 Analyst {index}',
                    password_hash=auth.hash_password('presentation-replay-only'),
                    email=f'v3-replay-{index}@example.test', role='security_analyst'))
        conn.commit()
        admin = conn.execute("SELECT id FROM users WHERE username=? AND role='system_admin'", (admin_name,)).fetchone()
        if admin is None: raise ValueError('Preparing Admin account is missing in Replay')
        admin_id = admin['id']
        for index in range(40):
            meta, item = structure[index], feedback[index]
            ref = arrive(conn, index, rows, structure, contexts, admin_id)
            actor = conn.execute('SELECT id FROM users WHERE username=?', (meta['analyst'],)).fetchone()
            if actor is None: raise ValueError('Frozen Learning actor is not an Analyst')
            actor_id = actor['id']
            current = selective_review.read_review(conn, UUID(ref))
            selective_review.decide_review(conn, UUID(ref), actor_id=actor_id, action='apply',
                request=selective_review.ReviewCommand(request_id=_id('review', ref),
                    expected_version=current.version, reason='Presentation Replay Learning-phase pre-verdict review'))
            work = analyst_work.read_work(conn, conn.execute(
                'SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (ref,)).fetchone()['id'], actor_id)
            if not work.can_claim: raise ValueError(f'Learning alert {index+1} cannot be claimed under current policy')
            claim = analyst_work.claim(conn, UUID(ref), actor_id=actor_id,
                request=analyst_work.ClaimCommand(request_id=_id('claim', ref), expected_revision=work.revision))
            if claim.outcome != 'claimed': raise ValueError(f'Learning claim failed at index {index+1}')
            view = read_verdict(conn, UUID(ref), actor_id)
            source_verdict = item['verdict']['verdict']
            record_verdict(conn, UUID(ref), actor_id=actor_id, request=VerdictCommand(
                request_id=_id('verdict', ref), expected_revision=view.revision,
                expected_state_version=view.source_state_version, outcome=source_verdict['outcome'],
                reason=source_verdict['reason']))
        lessons = [triage_memory.read_memory(conn, row['lesson_ref']) for row in conn.execute(
            'SELECT lesson_ref FROM triage_memory_lessons')]
        counts = {'total': len(lessons), 'active': sum(x.status == 'active' for x in lessons),
                  'candidate': sum(x.status == 'candidate' for x in lessons)}
        if counts != {'total': 20, 'active': 10, 'candidate': 10}:
            raise ValueError(f'Current runtime Learning checkpoint differs from official 20/10/10: {counts}')
        for index in range(40, 40 + INITIAL_HOLDOUT):
            arrive(conn, index, rows, structure, contexts, admin_id)
        total = conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]
        if total != 40 + INITIAL_HOLDOUT or conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Presentation Replay operational checkpoint failed integrity check')
        return source_hash, counts, total
    finally:
        conn.close()


def advance_one(path: Path, index: int, admin_name: str):
    rows, structure, contexts, _, _ = inputs()
    with closing(db.connect(path)) as conn:
        admin = conn.execute("SELECT id FROM users WHERE username=? AND role='system_admin'", (admin_name,)).fetchone()
        if admin is None: raise ValueError('Preparing Admin account is missing in Replay')
        return arrive(conn, index, rows, structure, contexts, admin['id'])
