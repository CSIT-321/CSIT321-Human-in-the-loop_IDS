"""Source-database identity constraints also apply to imported recorded archives."""
from contextlib import closing
from datetime import timedelta
import json
from uuid import uuid4

import pytest

from packages.contracts import db
from packages.detection import prospective_collection as c
from packages.evaluation.prospective_recorded import evaluate_recorded, export_connection, ArchiveIntegrityError
from test_api import client, database
from test_selective_review import alerts
from test_prospective_collection import collection, apply, finish


@pytest.fixture
def archive(collection):
    path, items, admin, run, clock = collection
    with closing(db.connect(path)) as conn:
        apply(conn, items, run)
        clock[0] += timedelta(seconds=1)
        apply(conn, items, run)
        clock[0] += timedelta(seconds=1)
        apply(conn, items, run, 'require_review')
        finish(conn, admin, run, clock)
        result = export_connection(conn, run.run_ref)
    assert result.run.decision_count == len(result.decisions) == len(result.review_events) == 3
    return result


def report(archive):
    return evaluate_recorded(archive, now=archive.run.closed_at)


def edit_payload(archive, mutate):
    event = archive.review_events[0]
    payload = json.loads(event['request_payload'])
    mutate(payload)
    event['request_payload'] = json.dumps(payload)


def test_valid_three_event_archive_keeps_ledger_and_cohort_distinct(archive):
    result = report(archive)
    assert result['persistedDecisionCount'] == 3
    assert result['eligibleAlerts'] == result['deferredAlerts'] == result['recalls'] == 1


@pytest.mark.parametrize('field', ['id', 'event_ref', 'request_id', 'operational_alert_id',
    'actor_id', 'alertRef', 'action', 'event_type', 'created_at', 'request_payload', 'decision_snapshot', 'reason'])
@pytest.mark.parametrize('damage', ['missing', 'null', 'empty'])
def test_required_raw_fields_cannot_disappear(archive, field, damage):
    event = archive.review_events[0]
    if damage == 'missing': event.pop(field)
    else: event[field] = None if damage == 'null' else ''
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


@pytest.mark.parametrize('field,value', [
    ('id', True), ('id', '1'), ('id', 0),
    ('event_ref', 'not-a-uuid'), ('request_id', 'not-a-uuid'),
    ('actor_id', '1'), ('actor_id', 0), ('actor_id', 99999),
    ('operational_alert_id', True), ('operational_alert_id', 99999),
    ('alertRef', 'not-a-uuid'), ('alertRef', '00000000-0000-4000-8000-000000000000'),
    ('action', 'automatic_dismissal'), ('event_type', 'V2_HUMAN_REVIEW_REQUIRED'),
    ('created_at', 1234567890), ('created_at', '2026-01-01'), ('created_at', 'not-a-time'),
    ('request_payload', 'not-json'), ('request_payload', '{}'),
    ('decision_snapshot', 'not-json'), ('decision_snapshot', '{}'), ('reason', '   '),
])
def test_malformed_or_mismatched_raw_fields_rejected(archive, field, value):
    archive.review_events[0][field] = value
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


@pytest.mark.parametrize('field', ['id', 'event_ref', 'request_id'])
def test_source_global_identity_uniqueness(archive, field):
    archive.review_events[1][field] = archive.review_events[0][field]
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


@pytest.mark.parametrize('damage', ['raw_request', 'payload_request', 'missing_payload_request',
    'payload_alert', 'payload_action', 'payload_reason', 'receipt_decision', 'receipt_run'])
def test_request_identity_chain_cannot_be_spliced(archive, damage):
    if damage == 'raw_request': archive.review_events[0]['request_id'] = str(uuid4())
    elif damage == 'payload_request': edit_payload(archive, lambda p:p['request'].update(request_id=str(uuid4())))
    elif damage == 'missing_payload_request': edit_payload(archive, lambda p:p['request'].pop('request_id'))
    elif damage == 'payload_alert': edit_payload(archive, lambda p:p.update(alertRef=str(uuid4())))
    elif damage == 'payload_action': edit_payload(archive, lambda p:p.update(action='require_review'))
    elif damage == 'payload_reason': edit_payload(archive, lambda p:p['request'].update(reason='Different originating request'))
    elif damage == 'receipt_decision': edit_payload(archive, lambda p:p['collectionRecording'].update(decisionRef=str(uuid4())))
    elif damage == 'receipt_run': edit_payload(archive, lambda p:p['collectionRecording'].update(runRef=str(uuid4())))
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


@pytest.mark.parametrize('damage', ['missing_decision', 'missing_raw', 'duplicate_decision',
    'duplicate_decision_ref', 'duplicate_sidecar_event', 'hidden_count'])
def test_complete_sidecar_ledger_remains_required(archive, damage):
    if damage in ('missing_decision', 'hidden_count'): archive.decisions.pop()
    if damage == 'hidden_count':
        archive = archive.model_copy(update={'run':archive.run.model_copy(update={'decision_count':2})})
    if damage == 'missing_raw': archive.review_events.pop()
    if damage == 'duplicate_decision':
        archive.decisions.append(archive.decisions[0])
        archive = archive.model_copy(update={'run':archive.run.model_copy(update={'decision_count':4})})
    if damage == 'duplicate_decision_ref':
        archive.decisions[1] = archive.decisions[1].model_copy(update={'decision_ref':archive.decisions[0].decision_ref})
    if damage == 'duplicate_sidecar_event':
        archive.decisions[1] = archive.decisions[1].model_copy(update={'review_event_id':archive.decisions[0].review_event_id})
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


def test_legacy_receipt_free_records_still_validate(archive):
    before = c.canonical(report(archive))
    for event in archive.review_events:
        payload = json.loads(event['request_payload']); payload.pop('collectionRecording')
        event['request_payload'] = json.dumps(payload)
    # In-window overrides appear in frozenInputs, so compare cohort results rather than raw provenance bytes.
    result = report(archive)
    assert result['persistedDecisionCount'] == 3 and result['eligibleAlerts'] == 1
    assert result['decisions'] == json.loads(before)['decisions']


@pytest.mark.parametrize('form', ['uppercase', 'hex', 'braces'])
def test_equivalent_run_uuid_cannot_hide_a_missing_legacy_sidecar(archive, form):
    ref = archive.run.run_ref
    text = str(ref).upper() if form == 'uppercase' else ref.hex if form == 'hex' else '{'+str(ref)+'}'
    event = archive.review_events[-1]
    payload = json.loads(event['request_payload'])
    payload['request']['collection_run_ref'] = text
    payload.pop('collectionRecording')
    event['request_payload'] = json.dumps(payload)
    assert report(archive)['persistedDecisionCount'] == 3
    archive.decisions.pop()
    archive = archive.model_copy(update={'run':archive.run.model_copy(update={'decision_count':2})})
    with pytest.raises(ArchiveIntegrityError, match='archive-integrity'):
        report(archive)


def test_unrelated_future_snapshots_are_not_reinterpreted(archive):
    before = c.canonical(report(archive))
    event = dict(archive.review_events[0]); other_run = str(uuid4()); request_id = str(uuid4())
    event.update(id=9999, event_ref=str(uuid4()), request_id=request_id,
                 created_at=(archive.run.closed_at+timedelta(seconds=1)).isoformat(),
                 decision_snapshot=json.dumps({'futurePolicyVersion': 'unrelated-v99'}))
    payload = json.loads(event['request_payload'])
    payload['request'].update(request_id=request_id, collection_run_ref=other_run)
    payload['collectionRecording'].update(runRef=other_run, decisionRef=str(uuid4()))
    event['request_payload'] = json.dumps(payload)
    archive.review_events.append(event)
    assert c.canonical(report(archive)) == before
    event['event_ref'] = archive.review_events[0]['event_ref']
    with pytest.raises(ArchiveIntegrityError, match='duplicate raw review event_ref'):
        report(archive)


def test_expired_and_closed_skipped_overrides_validate_without_inflating_count(collection):
    path, items, admin, run, clock = collection
    with closing(db.connect(path)) as conn:
        apply(conn, items, run)
        clock[0] = run.protocol.registration.holdout_end+timedelta(seconds=1)
        apply(conn, items, run, 'require_review')
        finish(conn, admin, run, clock)
        before = c.canonical(evaluate_recorded(export_connection(conn, run.run_ref), now=clock[0]))
        apply(conn, items, run, 'require_review')
        exported = export_connection(conn, run.run_ref)
    result = evaluate_recorded(exported, now=clock[0])
    assert c.canonical(result) == before
    assert result['persistedDecisionCount'] == exported.run.decision_count == 1
    assert result['eligibleAlerts'] == result['recalls'] == 1
    assert len(exported.review_events) == 3


def test_identity_error_exposed_by_http_report(collection, client, monkeypatch):
    from apps.api import collection_routes
    path, items, admin, run, clock = collection
    with closing(db.connect(path)) as conn:
        apply(conn, items, run); finish(conn, admin, run, clock)
        archive = export_connection(conn, run.run_ref)
    archive.review_events[0].pop('request_id')
    monkeypatch.setattr(collection_routes, 'export_connection', lambda conn, ref:archive)
    response = client.get(f'/api/v2/collection/runs/{run.run_ref}/report')
    assert response.status_code == 400 and response.json()['error']['code'] == 'ARCHIVE_INTEGRITY'
