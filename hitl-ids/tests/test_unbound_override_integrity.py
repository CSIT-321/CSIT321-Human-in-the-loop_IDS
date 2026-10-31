"""Real operational overrides, isolated collection fixtures and corrupted export copies."""
from contextlib import closing
from datetime import timedelta
import json
from uuid import uuid4, UUID

import pytest
from packages.contracts import db
from packages.detection import prospective_collection as c
from packages.detection.selective_review import ReviewCommand, decide_review, read_review
from packages.evaluation.prospective_recorded import evaluate_recorded, export_connection, ArchiveIntegrityError
from test_api import client, database
from test_selective_review import alerts
from test_prospective_collection import collection, apply, finish


def override(conn, items):
    actor, rows = items
    ref = rows[3].operational_alert_ref
    return decide_review(conn, ref, actor_id=actor, action='require_review',
        request=ReviewCommand(request_id=uuid4(), expected_version=read_review(conn, ref).version,
                              reason='Explicit unbound human safety override'))


@pytest.fixture
def unbound(collection):
    path, items, admin, run, clock = collection
    with closing(db.connect(path)) as conn:
        assert apply(conn, items, run)[1].view.disposition == 'no_immediate_review'
        ledger = c.decisions(conn, run.run_ref)
        clock[0] += timedelta(seconds=1)
        assert override(conn, items).view.disposition == 'must_review'
        assert read_review(conn, items[1][3].operational_alert_ref).human_override
        assert c.decisions(conn, run.run_ref) == ledger
        assert c.read_run(conn, run.run_ref).decision_count == 1
        finish(conn, admin, run, clock)
        return export_connection(conn, run.run_ref)


def report(a):
    return evaluate_recorded(a, now=a.run.closed_at)


def test_valid_unbound_control(unbound):
    r = report(unbound)
    assert r['recalls'] == r['eligibleAlerts'] == r['persistedDecisionCount'] == 1
    assert len(unbound.review_events) == 2
    assert 'collectionRecording' not in json.loads(unbound.review_events[-1]['request_payload'])


@pytest.mark.parametrize('damage', [
    'actor_missing', 'actor_null', 'actor_bool', 'actor_zero', 'raw_request',
    'original_request_missing', 'snapshot_empty', 'event_missing', 'event_null',
    'event_empty', 'event_malformed', 'duplicate_event', 'duplicate_request',
    'duplicate_id', 'alert_ref', 'numeric_alert', 'action', 'type_missing',
    'type_invalid', 'type_mismatch', 'time_missing', 'time_naive', 'time_invalid',
    'reason_empty', 'reason_mismatch', 'at_decision', 'before_decision', 'at_cutoff',
    'after_cutoff', 'snapshot_alert', 'snapshot_numeric_alert', 'snapshot_disposition',
    'snapshot_source', 'snapshot_stage', 'snapshot_route', 'snapshot_codes',
    'snapshot_explanation', 'snapshot_policy', 'snapshot_triage_identity',
    'payload_alert', 'payload_action', 'payload_reason',
])
def test_corrupt_consumed_unbound_override_rejected(unbound, damage):
    e = unbound.review_events[-1]
    payload = json.loads(e['request_payload'])
    snapshot = json.loads(e['decision_snapshot'])
    values = {
        'actor_null': ('actor_id', None), 'actor_bool': ('actor_id', True),
        'actor_zero': ('actor_id', 0), 'raw_request': ('request_id', str(uuid4())),
        'snapshot_empty': ('decision_snapshot', '{}'), 'event_null': ('event_ref', None),
        'event_empty': ('event_ref', ''), 'event_malformed': ('event_ref', 'invalid'),
        'alert_ref': ('alertRef', str(uuid4())), 'numeric_alert': ('operational_alert_id', 999999),
        'action': ('action', 'apply'), 'type_invalid': ('event_type', 'invalid'),
        'type_mismatch': ('event_type', 'V2_SELECTIVE_REVIEW_DECIDED'),
        'time_naive': ('created_at', '2026-01-01T12:00:00'), 'time_invalid': ('created_at', 'invalid'),
        'reason_empty': ('reason', ''), 'reason_mismatch': ('reason', 'Different reason'),
    }
    if damage in values:
        key, value = values[damage]; e[key] = value
    elif damage in ('actor_missing', 'event_missing', 'type_missing', 'time_missing'):
        e.pop({'actor_missing':'actor_id','event_missing':'event_ref','type_missing':'event_type','time_missing':'created_at'}[damage])
    elif damage.startswith('duplicate_'):
        key = {'duplicate_event':'event_ref','duplicate_request':'request_id','duplicate_id':'id'}[damage]
        e[key] = unbound.review_events[0][key]
    elif damage in ('at_decision','before_decision','at_cutoff','after_cutoff'):
        at = unbound.decisions[0].decision_at if 'decision' in damage else unbound.run.protocol.registration.outcome_cutoff
        at += timedelta(seconds=-1 if damage=='before_decision' else 1 if damage=='after_cutoff' else 0)
        e['created_at'] = at.isoformat()
    elif damage == 'original_request_missing':
        payload['request'].pop('request_id')
    elif damage == 'payload_alert': payload['alertRef'] = str(uuid4())
    elif damage == 'payload_action': payload['action'] = 'apply'
    elif damage == 'payload_reason': payload['request']['reason'] = 'Different request reason'
    elif damage == 'snapshot_alert': snapshot['inputs']['alert']['operationalAlertRef'] = str(uuid4())
    elif damage == 'snapshot_numeric_alert': snapshot['inputs']['alert']['id'] = 999999
    elif damage == 'snapshot_triage_identity': snapshot['inputs']['triage']['operationalAlertId'] = 999999
    elif damage == 'snapshot_stage': snapshot['inputs']['triage']['workflowStage'] = 'assessment'
    elif damage == 'snapshot_route': snapshot['inputs']['triage']['handlingRoute'] = 'tier2_candidate'
    else:
        key,value = {'snapshot_disposition':('disposition','no_immediate_review'),
            'snapshot_source':('decisionSource','selective_review_policy'), 'snapshot_codes':('reasonCodes',[]),
            'snapshot_policy':('policyVersion','incorrect-version'),
            'snapshot_explanation':('explanation','Different explanation')}[damage]
        snapshot['result'][key] = value
    e['request_payload'] = json.dumps(payload)
    if damage != 'snapshot_empty': e['decision_snapshot'] = json.dumps(snapshot)
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(unbound)


@pytest.mark.parametrize('key', ['event_ref','request_id'])
@pytest.mark.parametrize('form', ['upper','braces','compact'])
def test_global_uuid_variants(unbound, key, form):
    value = unbound.review_events[0][key]
    unbound.review_events[-1][key] = value.upper() if form=='upper' else '{'+value+'}' if form=='braces' else UUID(value).hex
    with pytest.raises(ArchiveIntegrityError): report(unbound)


@pytest.mark.parametrize('boundary', ['at_decision','at_cutoff','after_cutoff'])
def test_genuine_outside_window_override_is_not_a_recall(collection, boundary):
    path, items, admin, run, clock = collection
    with closing(db.connect(path)) as conn:
        apply(conn, items, run)
        if boundary != 'at_decision':
            clock[0] = run.protocol.registration.outcome_cutoff + timedelta(seconds=boundary=='after_cutoff')
        override(conn, items)
        finish(conn, admin, run, clock)
        a = export_connection(conn, run.run_ref)
    r = report(a)
    assert r['recalls'] == 0 and r['persistedDecisionCount'] == 1


def test_unrelated_future_snapshot_not_reinterpreted(unbound):
    before = c.canonical(report(unbound))
    e = dict(unbound.review_events[-1])
    e.update(id=999999, event_ref=str(uuid4()), request_id=str(uuid4()),
        alertRef=str(uuid4()), created_at=(unbound.run.closed_at+timedelta(days=1)).isoformat(),
        decision_snapshot='{"futureVersion":"unknown"}')
    e['request_payload'] = json.dumps({'request':{}, 'alertRef':e['alertRef'], 'action':'require_review'})
    unbound.review_events.append(e)
    assert c.canonical(report(unbound)) == before
    e['event_ref'] = unbound.review_events[0]['event_ref']
    with pytest.raises(ArchiveIntegrityError): report(unbound)
