"""Packet Replay: both detection chains of one recorded capture arrive step by step in the Replay workspace.

Input is data/packet-replay/ (scripts/build_packet_replay.py). A step is an equal share of capture time.
  flow chain      the step's scored flows are copied in, then grouped, projected and routed by the product's
                  own queue code (packages/detection/flow_queue.py)
  Suricata chain  the step's alerts are staged, accepted and admitted by the product's own commands, in the
                  preparing Admin's name (the same rule as Presentation Replay)

Informational Suricata signatures are not in the input. Recorded traffic, not live traffic.
The base must come from the current schema: the rows are copied column for column.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from apps.api import auth
from packages.contracts import db
from packages.detection import flow_queue
from packages.detection.adapters.staging import stage_file
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility,
)

DATA = Path(__file__).resolve().parents[2] / 'data' / 'packet-replay'
SENSOR = 'packet-replay-sensor'
SCOPE = 'cse-cic-ids2018-2018-02-14'
REASON = 'Packet Replay: non-informational Suricata alert, accepted by the replay rule'


class _Batch:
    """The step's Suricata alerts, in the shape that staging reads."""
    def __init__(self, events): self.events = events
    def read_text(self, **_): return json.dumps(self.events)


def available() -> bool:
    return all((DATA / name).is_file() for name in ('base.db', 'steps.json', 'eve.jsonl'))


def source_hash() -> str:
    return hashlib.sha256((DATA / 'steps.json').read_bytes() + (DATA / 'eve.jsonl').read_bytes()).hexdigest()


def build(path: Path) -> int:
    """An empty Replay database with the capture's model, dataset and detection run. Returns the flow count."""
    with closing(db.connect(path)) as conn:
        db.create_schema(conn)
        auth.ensure_demo_accounts(conn)
        conn.commit()
        conn.execute('ATTACH DATABASE ? AS base', (str(DATA / 'base.db'),))
        for table in ('ml_models', 'datasets', 'detection_runs'):
            conn.execute(f'INSERT INTO {table} SELECT * FROM base.{table}')
        flows = conn.execute('SELECT count(*) FROM base.alerts').fetchone()[0]
        conn.commit()
        conn.execute('DETACH DATABASE base')
        return flows


def advance_one(path: Path, step: int, admin_name: str, project_flows: bool = True) -> tuple[int, int]:
    """One step of the capture: the data always arrives. ``project_flows`` is the program's flow-chain
    switch, not a replay option: when False the flow records are stored but not grouped or queued.

    Returns (Suricata alerts admitted, queue items) so far.

    Idempotent: a step that stopped part-way continues from what the database already holds.
    """
    through = json.loads((DATA / 'steps.json').read_text(encoding='utf-8'))[step]['throughAlertId']
    with (DATA / 'eve.jsonl').open(encoding='utf-8') as source:
        events = [item['event'] for item in map(json.loads, source) if item['step'] == step]
    with closing(db.connect(path)) as conn:
        admin = conn.execute("SELECT id FROM users WHERE username=? AND role='system_admin'", (admin_name,)).fetchone()
        if admin is None:
            raise ValueError('Preparing Admin account is missing in Replay')
        conn.execute('ATTACH DATABASE ? AS base', (str(DATA / 'base.db'),))
        have = conn.execute('SELECT COALESCE(max(id),0) FROM alerts').fetchone()[0]
        conn.execute('INSERT INTO alerts SELECT * FROM base.alerts WHERE id>? AND id<=?', (have, through))
        conn.execute('INSERT INTO flow_data SELECT * FROM base.flow_data WHERE alert_id>? AND alert_id<=?',
                     (have, through))
        conn.commit()
        conn.execute('DETACH DATABASE base')
        if project_flows:
            flow_queue.materialize_and_route(conn)
            conn.commit()      # staging needs a connection outside a transaction
        if events:
            stage_file(conn, _Batch(events), SENSOR, capture_scope=SCOPE)
        waiting = conn.execute(
            'SELECT i.id FROM external_alert_inbox i LEFT JOIN external_operational_admission a '
            'ON a.external_inbox_id=i.id WHERE a.id IS NULL ORDER BY i.id').fetchall()
        for (inbox_id,) in waiting:
            review = conn.execute('SELECT id FROM external_eligibility_review WHERE external_inbox_id=? '
                                  'ORDER BY id DESC LIMIT 1', (inbox_id,)).fetchone()
            if review is None:
                review = review_eligibility(conn, inbox_id, actor_id=admin['id'], request=EligibilityRequest(
                    request_id=uuid5(NAMESPACE_URL, f'packet-replay:review:{inbox_id}'),
                    expected_review_id=None, decision='accepted', reason=REASON))
            admit_external(conn, inbox_id, actor_id=admin['id'], request=AdmissionRequest(
                request_id=uuid5(NAMESPACE_URL, f'packet-replay:admit:{inbox_id}'),
                expected_review_id=review['id'], reason=REASON))
        return (conn.execute('SELECT count(*) FROM external_operational_admission').fetchone()[0],
                conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0])
