"""Explicitly synthetic timeline fixtures. Not connected to production admission or policy config."""
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from packages.contracts.operational_v2 import ExternalSourceProvenanceV2, OperationalTriageStateV2
from packages.detection.adapters.operational_v2 import _projection
from packages.detection.adapters.suricata import SuricataEveAdapter, SuricataOutput
from packages.detection.selective_review_policy import load_policy
from packages.detection.triage_memory import MemoryLesson, context_for, load_config
from packages.detection.triage_policy import TriageContext
from packages.evaluation.temporal_review import TemporalArchive


SCENARIOS = ('safe_learning', 'conflict', 'leakage_trap', 'unknown_context')


def synthetic_archive(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('unknown synthetic scenario')
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    moment = lambda minutes: origin + timedelta(minutes=minutes)
    alerts, states, contexts, supports, outcomes = [], [], [], [], []
    safe = TriageContext(asset_criticality='low', repeated_campaign=False, correlated_alert_count=1,
        response_required=False, known_malicious_indicator=False, analyst_escalated=False,
        unresolved_by_tier1=False, evidence_conflict=False, confirmed_malicious=False)
    # Fixed references intentionally fall outside the unchanged V1 10% sample.
    references = ('temporal:1', 'temporal:2', 'temporal:3', 'temporal:7', 'temporal:8', 'temporal:9')
    for index, minute in enumerate((0, 2, 4, 8, 10, 14), 1):
        event = dict(event_type='alert', timestamp=moment(minute).isoformat(), src_ip='10.0.0.50', dest_ip='10.0.0.30',
            src_port=44445, dest_port=22, proto='TCP', flow_id=index,
            alert=dict(signature='SYNTHETIC authorised scanner', signature_id=900001, category='Synthetic SSH scan', severity=1))
        canonical = SuricataEveAdapter().adapt(SuricataOutput(event, references[index-1], sensor_id='temporal-demo'))
        alert = _projection(canonical, id=index, source_kind='external_nids_alert', external_inbox_id=index,
            source_provenance=ExternalSourceProvenanceV2(sensor_id='temporal-demo', raw_reference=references[index-1],
                admission_policy_version='synthetic', admission_decision='hold_for_review', admission_reason='SYNTHETIC fixture only',
                proposed_operational_priority=85, proposed_evidence_class='external_rule', review_required=True,
                learning_eligible=False, evaluation_eligible=False))
        alerts.append(alert)
        state = OperationalTriageStateV2(operational_alert_id=index, operational_priority=85, priority_band='P1',
            priority_band_scheme='p1_p4', handling_route='tier1_review', workflow_stage='triage', updated_at=moment(minute))
        states.append(dict(alert_ref=alert.operational_alert_ref, available_at=moment(minute), state=state))
        contexts.append(dict(alert_ref=alert.operational_alert_ref, available_at=moment(minute), audit_id=index,
            context=TriageContext() if scenario=='unknown_context' and index>=4 else safe))
    config = load_config()
    context = context_for(alerts[0])
    lesson = MemoryLesson(lesson_ref=uuid5(NAMESPACE_URL, 'temporal-demo-lesson'), outcome='expected_activity',
        human_reason='SYNTHETIC authorised scanner confirmed by humans', context_snapshot=context, scope='exact',
        scope_fields=sorted(key for key, value in context.model_dump(by_alias=True).items() if value is not None),
        source_operational_alert_ref=alerts[0].operational_alert_ref, source_case_ref=None, created_by_actor_id=1,
        created_at=moment(1).isoformat(), configuration=config)
    for index, minute in enumerate((1, 3, 5)):
        supports.append(dict(event_id=f'review:{index}', lesson_ref=lesson.lesson_ref, alert_ref=alerts[index].operational_alert_ref,
            available_at=moment(minute), outcome='expected_activity', relation='support'))
        outcomes.append({key: value for key, value in supports[-1].items() if key not in ('lesson_ref', 'relation')})
    for index, minute in ((3, 11), (4, 12), (5, 15)):
        malicious = scenario in ('conflict', 'leakage_trap') and index==4
        if malicious and scenario=='leakage_trap':
            minute = 16
        outcome = 'confirmed_malicious' if malicious else 'expected_activity'
        outcomes.append(dict(event_id=f'holdout:{index}', alert_ref=alerts[index].operational_alert_ref,
            available_at=moment(minute), outcome=outcome))
        if malicious:
            supports.append(dict(event_id='contradiction', lesson_ref=lesson.lesson_ref, alert_ref=alerts[index].operational_alert_ref,
                available_at=moment(minute), outcome=outcome, relation='conflict'))
    return TemporalArchive(data_basis='synthetic/demo', provenance='Deterministic synthetic scenario: '+scenario,
        holdout_start=moment(7), holdout_end=moment(20), alerts=alerts, states=states, contexts=contexts,
        policies=[dict(effective_at=moment(-1), available_at=moment(-1), configuration=load_policy())], lessons=[lesson],
        supports=supports, outcomes=outcomes,
        activations=[dict(lesson_ref=lesson.lesson_ref, available_at=moment(6), action='activate', actor_id=1,
            reason='Explicit synthetic human activation after three reviews', valid_from=moment(6), expires_at=moment(6)+timedelta(days=30))])
