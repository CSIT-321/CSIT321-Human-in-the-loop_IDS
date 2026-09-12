"""Database rows to wire shapes (plan step S10b).

The handlers stay thin because everything interesting happens here. Three things are worth knowing
before changing anything in this file:

**The empty states are content, not absence.** An alert with no matched rule gets
`"No rule matched (ML-only alert)."`, not an empty panel — S12 renders those strings, and a blank
panel reads as a loading bug. `signature_only = 0` on corrected data, so the ML-only empty state is
the *common* case, not an edge one.

**A guardrail explains itself in words.** `maximum_negative_adjustment_capped` means nothing to an
analyst; "the maximum reduction of 30 limited this change" does. The wire carries both: the code for
a client to switch on, and a sentence for it to show. Making guardrails visible is the point.

**An alert with no verdict still has an adjustment chain** — the identity one: requested 0, applied
0, score unchanged. Returning `null` would force the screen to special-case its commonest path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from apps.api.contract import alerts as ca
from apps.api.contract import operations as co
from apps.api.contract.common import Actor
from packages.contracts import models as m
from packages.detection.feedback.service import FEEDBACK_EFFECTS

#: A guardrail's code, as a sentence an analyst can read. `{value}` is the configured setting.
GUARDRAIL_TEXT: dict[str, str] = {
    "maximum_negative_adjustment_capped":
        "The maximum reduction of {value} limited this change.",
    "maximum_increase_capped":
        "The maximum increase of {value} limited this change.",
    "critical_alert_floor":
        "This alert is Critical, so its score was held at the floor of {value}.",
    "infiltration_alert_floor":
        "Infiltration alerts are held at a floor of {value}.",
    "signature_ml_disagreement_review_preserved":
        "A signature rule and the model disagree, so this alert stays flagged for review.",
    "signature_override_feedback_immune":
        "A precision-1.000 rule fired and the model disputes it. Feedback cannot change this "
        "alert's score; it has been routed to the administrator instead.",
    "score_range_clamped":
        "Scores are bounded to 0-100, so the change was clamped at {value}.",
    "non_finite_adjustment_rejected":
        "The requested change was not a finite number and was rejected.",
}

#: What each category means, taken from the engine rather than restated.
CATEGORY_TEXT = {name: effect.meaning for name, effect in FEEDBACK_EFFECTS.items()}


def _number(value: float) -> str:
    """Render a score the way the UI does: no trailing `.0` on a whole number."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _text(intervention: m.GuardrailIntervention) -> str:
    template = GUARDRAIL_TEXT.get(intervention.code, "A guardrail adjusted this change.")
    return template.format(value=_number(intervention.configured_value))


def actor(user: m.User | None, user_id: int | None = None) -> Actor:
    if user is None:
        return Actor(user_id=user_id)
    return Actor(user_id=user.id, display_name=user.display_name, role=user.role)


# --------------------------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------------------------


def alert_summary(alert: m.Alert, flow: m.FlowRecord, *, has_feedback: bool) -> ca.AlertSummary:
    return ca.AlertSummary(
        alert_ref=alert.alert_ref,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        detection_score=alert.detection_score,
        combined_score=alert.combined_score,
        severity=alert.severity,
        confidence=alert.confidence,
        queue_class=alert.queue_class,
        queue_priority=alert.queue_priority,
        evidence_class=alert.evidence_class,
        attack_category=alert.attack_category,
        status=alert.status,
        requires_review=alert.requires_review,
        is_critical=alert.is_critical,
        has_feedback=has_feedback,
        matched_rule_ids=[match.rule_id for match in alert.signature_rules or []],
        src_ip=flow.src_ip,
        dst_ip=flow.dst_ip,
        dst_port=flow.dst_port,
        protocol=flow.protocol,
    )


# --------------------------------------------------------------------------------------------
# The four evidence panels
# --------------------------------------------------------------------------------------------


def flow_panel(flow: m.FlowRecord) -> ca.FlowPanel:
    return ca.FlowPanel(
        src_ip=flow.src_ip, dst_ip=flow.dst_ip, src_port=flow.src_port, dst_port=flow.dst_port,
        protocol=flow.protocol, duration_seconds=flow.duration, packets=flow.packets,
        bytes=flow.bytes, source_record_id=flow.source_record_id, features=flow.flow_features)


def signature_panel(alert: m.Alert) -> ca.SignaturePanel:
    matches = alert.signature_rules or []
    if not matches:
        return ca.SignaturePanel(
            note="No rule matched (ML-only alert)." if alert.evidence_class == "ml_only"
            else "No rule matched, and the model did not flag this flow.")
    return ca.SignaturePanel(
        matched=[
            ca.RuleMatchPanel(
                rule_id=match.rule_id, name=match.name, severity=match.severity,
                attack_category=match.attack_category,
                matched_conditions=[
                    {"feature": condition.feature, "expected": condition.expected,
                     "observed": condition.observed}
                    for condition in match.matched_conditions])
            for match in matches],
        rule_set_version=matches[0].version,
        severity_score=alert.signature_severity)


def ml_panel(alert: m.Alert, *, model_version: str | None = None) -> ca.MlPanel:
    explanation = alert.shap_attributions
    if alert.ml_predicted_class is None and explanation is None:
        return ca.MlPanel(note="The model did not return a prediction for this flow.")

    def features(items: Any) -> list[ca.ShapFeature]:
        return [
            ca.ShapFeature(
                feature_name=item.feature_name, feature_value=item.feature_value,
                shap_contribution=item.shap_contribution, direction=item.direction)
            for item in (items or [])]

    check = explanation.additivity_check if explanation is not None else None
    return ca.MlPanel(
        predicted_class=alert.ml_predicted_class,
        probability=alert.ml_probability,
        model_version=model_version,
        explanation_status=explanation.status if explanation is not None else None,
        top_supporting=features(explanation.top_supporting_features if explanation else None),
        top_opposing=features(explanation.top_opposing_features if explanation else None),
        base_value=explanation.base_value if explanation is not None else None,
        raw_margin=explanation.raw_model_margin if explanation is not None else None,
        additivity_passed=check.passed if check is not None else None,
        note=None if explanation is not None else
        "The model predicted a class but returned no explanation for this flow.")


def evidence_panel(alert: m.Alert, *, fusion_scheme: str | None = None) -> ca.EvidencePanel:
    return ca.EvidencePanel(
        evidence_class=alert.evidence_class,
        queue_class=alert.queue_class,
        explanation=alert.explanation,
        fusion_scheme=fusion_scheme,
        agreement=alert.evidence_class == "corroborated",
        tier2_candidate=alert.queue_class == "tier2_candidate")


def family_panel(alert: m.Alert, family: m.AlertFamily | None, members: int) -> ca.FamilyPanel:
    if family is None:
        return ca.FamilyPanel(
            family_key=alert.family_key, members=members,
            gate_reason=("No verdict has been recorded for this family yet."
                         if alert.family_key else None),
            note=(None if alert.family_key else
                  "This alert is not part of a similar-alert family."))
    note = None
    if family.gate_open and (family.applied_adjustment or family.applied_offset):
        note = ("Similar alerts have been judged, so this alert carries its family's learned "
                "adjustment even where it has no verdict of its own.")
    return ca.FamilyPanel(
        family_key=family.family_key, members=members, gate_open=family.gate_open,
        gate_reason=family.gate_reason, dominant_category=family.dominant_category,
        agreement_ratio=family.agreement_ratio,
        applied_adjustment=family.applied_adjustment, applied_offset=family.applied_offset,
        note=note)


# --------------------------------------------------------------------------------------------
# Feedback and the adjustment chain
# --------------------------------------------------------------------------------------------


#: Which `guardrail_config` setting each intervention code is *about*.
#:
#: ``feedback_events`` stores only the codes, so the configured value has to be looked up rather
#: than inferred. Inferring it from the delta produces sentences like "held at the floor of 29.89"
#: when the floor is 70 — a wrong number in the one piece of text the demo exists to show.
CODE_CONFIG_KEY: dict[str, str] = {
    "critical_alert_floor": "critical_alert_floor",
    "infiltration_alert_floor": "infiltration_alert_floor",
    "maximum_negative_adjustment_capped": "max_feedback_reduction",
    "maximum_increase_capped": "max_feedback_increase",
}


def _interventions(event: m.FeedbackEvent,
                   settings: Mapping[str, float] | None = None) -> list[m.GuardrailIntervention]:
    """Rebuild the interventions from the stored reason codes.

    ``settings`` is the live ``guardrail_config``; without it the configured value cannot be
    recovered and is reported as 0 rather than guessed. The audit entry holds the full outcome and
    remains the administrator's source of truth — this is the analyst's readable version.
    """
    if not event.guardrail_reason:
        return []
    settings = settings or {}
    out: list[m.GuardrailIntervention] = []
    for raw in event.guardrail_reason.split(";"):
        code = raw.strip()
        if not code:
            continue
        if code in CODE_CONFIG_KEY:
            configured = float(settings.get(CODE_CONFIG_KEY[code], 0.0))
        elif code == "score_range_clamped":
            configured = round(event.original_score + event.actual_delta, 2)
        elif code == "signature_override_feedback_immune":
            configured = event.original_score
        else:
            configured = 0.0
        out.append(m.GuardrailIntervention(code=code, configured_value=configured))
    return out


def _summary(event: m.FeedbackEvent | None,
             interventions: list[ca.GuardrailInterventionOut]) -> str:
    if event is None:
        return "No analyst verdict has been recorded, so the score is as detection produced it."
    meaning = CATEGORY_TEXT.get(event.category, event.category)
    asked = f"{event.requested_delta:+g}"
    applied = f"{event.actual_delta:+g}"
    head = f"The alert was {meaning}, requesting {asked} points"
    reason = interventions[0].explanation if interventions else ""
    if event.guardrail_action == "rejected":
        return f"{head}. The change was rejected. {reason}".strip()
    if event.guardrail_action == "capped":
        return f"{head}; {applied} was applied. {reason or 'A guardrail bound the change.'}"
    return f"{head}, and {applied} was applied. No guardrail intervened."


def score_adjustment(alert: m.Alert, event: m.FeedbackEvent | None, *,
                     queue_class_before: str | None = None,
                     settings: Mapping[str, float] | None = None) -> ca.ScoreAdjustment:
    """The chain S12 draws. An alert with no verdict gets the identity chain, never null."""
    before = queue_class_before or alert.evidence_class
    if event is None:
        return ca.ScoreAdjustment(
            detection_score=alert.detection_score, score_before=alert.detection_score,
            requested_delta=0.0, actual_delta=0.0, score_after=alert.combined_score,
            action="applied", interventions=[], requires_review=alert.requires_review,
            queue_class_before=before, queue_class_after=alert.queue_class,
            summary=_summary(None, []))

    interventions = [
        ca.GuardrailInterventionOut(
            code=item.code, configured_value=item.configured_value,
            original_value=item.original_value, applied_value=item.applied_value,
            explanation=_text(item))
        for item in _interventions(event, settings)]
    return ca.ScoreAdjustment(
        detection_score=event.original_score,
        score_before=event.original_score,
        requested_delta=event.requested_delta,
        actual_delta=event.actual_delta,
        score_after=round(event.original_score + event.actual_delta, 2),
        action=event.guardrail_action,
        interventions=interventions,
        requires_review=alert.requires_review,
        queue_class_before=before,
        queue_class_after=alert.queue_class,
        summary=_summary(event, interventions))


def feedback_record(event: m.FeedbackEvent, alert: m.Alert, user: m.User | None,
                    settings: Mapping[str, float] | None = None) -> ca.FeedbackRecord:
    return ca.FeedbackRecord(
        feedback_ref=event.id or 0, category=event.category, note=event.note,
        actor=actor(user, event.user_id), created_at=event.created_at,
        adjustment=score_adjustment(alert, event, settings=settings),
        amended_from=event.amended_from_id)


# --------------------------------------------------------------------------------------------
# Admin and evaluator
# --------------------------------------------------------------------------------------------


def audit_entry(entry: m.AuditEntry, user: m.User | None,
                alert_ref: str | None = None) -> co.AuditEntryOut:
    details = dict(entry.details or {})
    return co.AuditEntryOut(
        event_id=entry.id or 0, event_type=entry.event_type, actor=actor(user, entry.actor_id),
        created_at=entry.created_at, alert_ref=alert_ref,
        rationale=details.get("rationale"), details=details or None)


def guardrail_setting(entry: m.GuardrailConfigEntry) -> co.GuardrailSetting:
    return co.GuardrailSetting(config_key=entry.config_key, config_value=entry.config_value,
                               description=entry.description, updated_at=entry.updated_at)


def detection_run(run: m.DetectionRun, *, by_evidence: dict[str, int] | None = None,
                  by_queue: dict[str, int] | None = None) -> co.DetectionRunSummary:
    return co.DetectionRunSummary(
        run_id=run.id or 0, status=run.status, dataset_id=run.dataset_id,
        model_version=run.model_version, rule_set_version=run.rule_set_version, seed=run.seed,
        started_at=run.started_at, completed_at=run.completed_at,
        flows=run.alert_count or 0, alerts=run.alert_count or 0,
        by_evidence_class=by_evidence or {}, by_queue_class=by_queue or {})
