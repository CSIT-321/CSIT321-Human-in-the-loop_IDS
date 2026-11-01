"""Historical decisions may learn only from evidence that existed at that instant."""
from contextlib import closing
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from packages.contracts import db, models as m
from packages.evaluation.temporal_fixture import SCENARIOS, synthetic_archive
from packages.evaluation.temporal_review import TemporalArchive, evaluate_temporal, memory_at, render_markdown, timestamp
from packages.evaluation.temporal_source import load_database
from test_api import client, database
from test_selective_review import alerts, teach


def changed(archive, **updates):
    return TemporalArchive.model_validate({**archive.model_dump(), **updates})


@pytest.mark.parametrize('scenario,deferred,unsafe,recalls,unknown', [
    ('safe_learning', 3, 0, 0, 0), ('conflict', 2, 1, 2, 0),
    ('leakage_trap', 3, 1, 3, 0), ('unknown_context', 0, 0, 0, 3),
])
def test_scenario_metrics(scenario, deferred, unsafe, recalls, unknown):
    archive = synthetic_archive(scenario)
    report = evaluate_temporal(archive)
    metrics = report['metrics']
    assert metrics['totalEligibleAlerts'] == metrics['baselineImmediateReviews'] == 3
    assert metrics['selectiveImmediateReviews'] == 3-deferred
    assert metrics['noImmediateReviewCount'] == deferred
    assert metrics['workloadReductionRate'] == pytest.approx(deferred/3)
    assert metrics['maliciousOrSuspiciousIncorrectlyDeferred'] == unsafe
    assert metrics['expectedOrFalsePositiveSafelyDeferred'] == deferred-unsafe
    assert metrics['unsafeDeferralRate'] == (unsafe/deferred if deferred else None)
    assert metrics['conflictTriggeredRecalls'] == recalls
    assert metrics['unknownSafetyContextBlockedCount'] == unknown
    assert metrics['unknownSafetyContextBlockedPercent'] == 100*unknown/3
    assert report['memoryMetrics']['candidateLessonsCreated'] == 1
    assert report['memoryMetrics']['lessonsReachingActivation'] == 1
    assert report['memoryMetrics']['activationTiming'][0]['supportingAlertsBeforeActivation'] == 3
    assert report['memoryMetrics']['activationTiming'][0]['secondsToActivation'] == 300
    assert all(r['inputs']['triage']['operationalPriority'] == 85 for r in report['decisions'])
    for groups in report['breakdowns'].values():
        assert sum(g['totalEligibleAlerts'] for g in groups.values()) == 3


def test_future_contradiction_does_not_rewrite_past_decisions():
    safe = evaluate_temporal(synthetic_archive('safe_learning'))
    trap = evaluate_temporal(synthetic_archive('leakage_trap'))
    for before, after in zip(safe['decisions'], trap['decisions']):
        for key in ('inputs', 'disposition', 'reasonCodes', 'policySnapshot'):
            assert before[key] == after[key]
    assert trap['metrics']['maliciousOrSuspiciousIncorrectlyDeferred'] == 1
    conflict = evaluate_temporal(synthetic_archive('conflict'))
    assert conflict['decisions'][2]['disposition'] == 'must_review'
    assert 'MEMORY_CONFLICT' in conflict['decisions'][2]['reasonCodes']


def test_review_activation_and_conflict_strict_timestamp_boundaries():
    archive = synthetic_archive('conflict')
    review = archive.supports[2]
    assert memory_at(archive, review.available_at)[0].support_count == 2
    assert memory_at(archive, review.available_at+timedelta(microseconds=1))[0].support_count == 3
    activation = archive.activations[0]
    assert memory_at(archive, activation.available_at)[0].status == 'eligible_for_activation'
    assert memory_at(archive, activation.available_at+timedelta(microseconds=1))[0].status == 'active'
    conflict = archive.supports[-1]
    assert memory_at(archive, conflict.available_at)[0].conflict_count == 0
    assert memory_at(archive, conflict.available_at+timedelta(microseconds=1))[0].conflict_count == 1


def test_activation_same_time_as_alert_is_not_available():
    archive = synthetic_archive('safe_learning')
    at = timestamp(archive.alerts[3].occurred_at)
    event = archive.activations[0].model_copy(update={'available_at': at, 'valid_from': at})
    report = evaluate_temporal(changed(archive, activations=[event]))
    assert report['decisions'][0]['disposition'] == 'must_review'
    assert report['decisions'][1]['disposition'] == 'no_immediate_review'


def test_future_lesson_and_future_activation_are_not_projected_backwards():
    archive = synthetic_archive('safe_learning')
    delayed = archive.activations[0].model_copy(update={'available_at': archive.holdout_end, 'valid_from': archive.holdout_end})
    report = evaluate_temporal(changed(archive, activations=[delayed]))
    assert report['metrics']['noImmediateReviewCount'] == 0
    assert memory_at(archive, timestamp(archive.lessons[0].created_at)) == []


def test_expiry_at_boundary_and_metrics():
    archive = synthetic_archive('safe_learning')
    expiry = timestamp(archive.alerts[4].occurred_at)
    event = archive.activations[0].model_copy(update={'expires_at': expiry})
    report = evaluate_temporal(changed(archive, activations=[event]))
    assert [r['disposition'] for r in report['decisions']] == ['no_immediate_review', 'must_review', 'must_review']
    assert report['memoryMetrics']['expiredLessonCount'] == 1


def test_policy_effective_and_available_time_both_enforced():
    archive = synthetic_archive('safe_learning')
    first = archive.policies[0]
    at = timestamp(archive.alerts[4].occurred_at)
    config = first.configuration.model_copy(update={'version': 'synthetic-stricter-v2', 'minimum_support': 4})
    period = first.model_copy(update={'effective_at': at, 'available_at': at, 'configuration': config})
    report = evaluate_temporal(changed(archive, policies=[first, period]))
    assert [r['disposition'] for r in report['decisions']] == ['no_immediate_review', 'must_review', 'must_review']
    delayed = period.model_copy(update={'available_at': archive.holdout_end})
    assert evaluate_temporal(changed(archive, policies=[first, delayed]))['metrics']['noImmediateReviewCount'] == 3
    assert evaluate_temporal(changed(archive, policies=[]))['metrics']['noImmediateReviewCount'] == 0


def test_future_context_never_fills_historical_unknowns():
    archive = synthetic_archive('safe_learning')
    contexts = [e.model_copy(update={'available_at': e.available_at+timedelta(microseconds=1)}) for e in archive.contexts]
    report = evaluate_temporal(changed(archive, contexts=contexts))
    assert report['metrics']['unknownSafetyContextBlockedPercent'] == 100
    assert report['metrics']['noImmediateReviewCount'] == 0


def test_missing_historical_state_excluded_and_no_current_state_fallback():
    archive = synthetic_archive('safe_learning')
    report = evaluate_temporal(changed(archive, states=[]))
    assert report['excludedAlerts'] == 3 and report['metrics']['totalEligibleAlerts'] == 0
    assert report['metrics']['workloadReductionRate'] == 0
    assert report['metrics']['unsafeDeferralRate'] is None


def test_truth_labels_never_enter_decision_inputs_and_missing_labels_not_safe():
    archive = synthetic_archive('safe_learning')
    report = evaluate_temporal(archive)
    unlabelled = evaluate_temporal(changed(archive, outcomes=[]))
    assert [r['inputs'] for r in report['decisions']] == [r['inputs'] for r in unlabelled['decisions']]
    assert unlabelled['metrics']['noImmediateReviewCount'] == 3
    assert unlabelled['metrics']['unsafeDeferralRate'] is None
    assert unlabelled['metrics']['expectedOrFalsePositiveSafelyDeferred'] == 0
    late = [e.model_copy(update={'available_at': archive.holdout_end}) for e in archive.outcomes]
    assert evaluate_temporal(changed(archive, outcomes=late))['metrics']['labelledDeferredAlerts'] == 0


def test_holdout_start_inclusive_end_exclusive_with_prior_learning():
    archive = synthetic_archive('safe_learning')
    report = evaluate_temporal(changed(archive, holdout_start=timestamp(archive.alerts[4].occurred_at),
        holdout_end=timestamp(archive.alerts[5].occurred_at)))
    assert report['totalHoldoutAlerts'] == 1 and report['metrics']['noImmediateReviewCount'] == 1


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_replay_deterministic_under_input_reordering_and_does_not_mutate(scenario):
    archive = synthetic_archive(scenario)
    before = archive.model_dump_json()
    first = evaluate_temporal(archive)
    values = archive.model_dump()
    reordered = TemporalArchive.model_validate({k: list(reversed(v)) if isinstance(v, list) else v for k, v in values.items()})
    assert first == evaluate_temporal(reordered) == evaluate_temporal(archive)
    assert archive.model_dump_json() == before
    assert 'not real-world production evidence' in render_markdown(first)


@pytest.mark.parametrize('case', ['duplicate_alert', 'duplicate_review', 'same_time_activation', 'backdated_activation', 'changed_policy_version', 'naive_time'])
def test_invalid_or_ambiguous_history_rejected(case):
    archive = synthetic_archive('safe_learning')
    data = archive.model_dump()
    if case == 'duplicate_alert': data['alerts'].append(data['alerts'][0])
    if case == 'duplicate_review': data['supports'].append(data['supports'][0])
    if case == 'same_time_activation':
        data['activations'][0]['available_at'] = data['supports'][2]['available_at']
    if case == 'backdated_activation':
        data['activations'][0]['valid_from'] = data['activations'][0]['available_at']-timedelta(seconds=1)
    if case == 'changed_policy_version':
        second = {**data['policies'][0], 'effective_at': archive.holdout_start,
            'configuration': {**data['policies'][0]['configuration'], 'minimum_support': 4}}
        data['policies'].append(second)
    if case == 'naive_time': data['holdout_start'] = '2026-01-01T00:07:00'
    with pytest.raises(ValueError): TemporalArchive.model_validate(data)


def test_database_empty_export_is_read_only_and_does_not_create_missing_db(tmp_path):
    source = tmp_path/'history.db'
    with closing(db.connect(source)) as conn:
        db.create_schema(conn)
    before = sha256(source.read_bytes()).hexdigest()
    demo = synthetic_archive('safe_learning')
    archive = load_database(source, demo.policies, demo.holdout_start, demo.holdout_end)
    assert evaluate_temporal(archive)['metrics']['totalEligibleAlerts'] == 0
    assert sha256(source.read_bytes()).hexdigest() == before
    with pytest.raises(sqlite3.OperationalError):
        load_database(tmp_path/'absent.db', [], demo.holdout_start, demo.holdout_end)
    assert not (tmp_path/'absent.db').exists()


def test_populated_database_export_uses_events_not_final_memory(database, alerts, monkeypatch):
    # Windows can return the same wall-clock tick for the last support and activation.
    # Supply a forward-only fixture clock; keep the strict temporal validation intact.
    clock = [m.utc_now()]
    def next_tick():
        clock[0] += timedelta(milliseconds=1)
        return clock[0]
    with monkeypatch.context() as fixture_clock:
        fixture_clock.setattr(m, 'utc_now', next_tick)
        with closing(db.connect(database)) as conn:
            teach(conn, alerts)
            before = list(conn.iterdump())
    digest = sha256(Path(database).read_bytes()).hexdigest()
    demo = synthetic_archive('safe_learning')
    real_connect = sqlite3.connect
    opened = []

    def checked_connect(source_uri, **kwargs):
        assert source_uri.endswith('?mode=ro') and kwargs['uri'] is True
        conn = real_connect(source_uri, **kwargs)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('CREATE TABLE forbidden_write (id INTEGER)')
        opened.append(source_uri)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr('packages.evaluation.temporal_source.sqlite3.connect', checked_connect)
        archive = load_database(database, demo.policies, '2000-01-01T00:00:00Z', '2100-01-01T00:00:00Z')
    assert opened and len(archive.lessons) == 1 and len(archive.supports) == 3 and len(archive.activations) == 1
    report = evaluate_temporal(archive)
    # Recorded network timestamps precede operational admission. Never backfill later state or active memory.
    assert report['metrics']['noImmediateReviewCount'] == 0
    assert report['excludedAlerts'] >= len(alerts[1])
    assert sha256(Path(database).read_bytes()).hexdigest() == digest
    with closing(db.connect(database)) as conn:
        assert list(conn.iterdump()) == before


def test_stale_context_sampling_and_human_override_remain_v1_behavior():
    archive = synthetic_archive('safe_learning')
    stale = [e.model_copy(update={'available_at': e.available_at-timedelta(hours=25)}) for e in archive.contexts]
    assert evaluate_temporal(changed(archive, contexts=stale))['metrics']['noImmediateReviewCount'] == 0
    period = archive.policies[0]
    sampled = period.model_copy(update={'configuration': period.configuration.model_copy(update={'version': 'synthetic-sample-all', 'audit_sample_percent': 100})})
    report = evaluate_temporal(changed(archive, policies=[sampled]))
    assert all(r['disposition'] == 'recommended_review' for r in report['decisions'])
    override = dict(alert_ref=archive.alerts[3].operational_alert_ref, available_at=archive.holdout_start)
    assert evaluate_temporal(changed(archive, overrides=[override]))['decisions'][0]['disposition'] == 'must_review'


def test_truth_at_alert_time_not_used_and_later_malicious_truth_never_erased():
    archive = synthetic_archive('safe_learning')
    target = archive.alerts[3]
    truth = next(e for e in archive.outcomes if e.alert_ref == target.operational_alert_ref)
    outcomes = [e for e in archive.outcomes if e != truth]
    tied = truth.model_copy(update={'available_at': timestamp(target.occurred_at)})
    report = evaluate_temporal(changed(archive, outcomes=[*outcomes, tied]))
    assert report['decisions'][0]['laterOutcome'] is None
    assert report['decisions'][0]['disposition'] == 'no_immediate_review'
    contradiction = truth.model_copy(update={'event_id': 'ambiguous', 'outcome': 'confirmed_malicious'})
    report = evaluate_temporal(changed(archive, outcomes=[*archive.outcomes, contradiction]))
    assert report['decisions'][0]['ambiguousTruth'] and report['decisions'][0]['laterOutcome'] == 'confirmed_malicious'
    benign = truth.model_copy(update={'event_id': 'later-benign', 'available_at': truth.available_at+timedelta(minutes=1)})
    report = evaluate_temporal(changed(archive, outcomes=[*archive.outcomes, contradiction, benign]))
    assert report['metrics']['maliciousOrSuspiciousIncorrectlyDeferred'] == 1


def test_cli_formats_and_explicit_policy_history_required(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, '-B', str(root/'scripts/evaluate_temporal_review.py')]
    result = subprocess.run([*command, '--synthetic', 'leakage_trap'], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['metrics']['maliciousOrSuspiciousIncorrectlyDeferred'] == 1
    markdown = subprocess.run([*command, '--synthetic', 'safe_learning', '--format', 'markdown'], capture_output=True, text=True, check=True)
    assert 'Temporal Holdout' in markdown.stdout
    missing = subprocess.run([*command, '--database', str(tmp_path/'missing.db')], capture_output=True, text=True)
    assert missing.returncode == 2 and '--policy-history' in missing.stderr
