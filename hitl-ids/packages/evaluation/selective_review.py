"""Read-only counterfactual; evaluation labels never enter policy inputs."""
from packages.detection.selective_review import current_snapshot


def evaluate_counterfactual(conn,labels=None):
    labels=labels or {}
    allowed={'confirmed_malicious','suspicious','expected_activity','false_positive'}
    if any(value not in allowed for value in labels.values()):raise ValueError('unsupported evaluation label')
    refs=[r[0] for r in conn.execute('SELECT operational_alert_ref FROM operational_alerts_v2 ORDER BY id')]
    if set(labels)-set(refs):raise ValueError('evaluation label references an unknown V2 alert')
    deferred=malicious=safe=conflicts=eligible=sampled=0
    for ref in refs:
        snapshot=current_snapshot(conn,ref)
        result=snapshot.result
        eligible+=(snapshot.inputs.triage.handling_route,snapshot.inputs.triage.workflow_stage)==('tier1_review','triage')
        no_review=result.disposition=='no_immediate_review'
        deferred+=no_review
        malicious+=no_review and labels.get(ref) in ('confirmed_malicious','suspicious')
        safe+=no_review and labels.get(ref) in ('expected_activity','false_positive')
        conflicts+='MEMORY_CONFLICT' in result.reason_codes
        sampled+='DETERMINISTIC_AUDIT_SAMPLE' in result.reason_codes
    return dict(dataBasis='Counterfactual on current stored memory/context, not a temporal backtest or measured workload benefit.',
        totalAlerts=len(refs),eligibleAlerts=eligible,baselineImmediateReview=len(refs),
        selectiveImmediateReview=len(refs)-deferred,noImmediateReview=deferred,
        immediateReviewReductionRate=deferred/eligible if eligible else 0,
        maliciousIncorrectlyDeferred=malicious,expectedOrFalsePositiveSafelyDeferred=safe,
        labelledAlerts=len(labels),unlabelledAlerts=len(refs)-len(labels),conflictsForcingReview=conflicts,
        sampledForReview=sampled)
