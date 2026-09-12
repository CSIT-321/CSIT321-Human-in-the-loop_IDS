"""The demo API's route handlers (plan step S10b).

Thin on purpose: every handler is a read through ``pipeline.store`` and a mapping through
``apps.api.mappers``. Business logic living in a handler is business logic that cannot be tested
without HTTP.

**The one exception, and it is deliberate.** ``POST /api/alerts/{alertRef}/feedback`` calls
``feedback.service.submit_feedback``, which invokes the guardrails and the family learning in a
single transaction. The plan's anti-pattern list marks that path **never delegated**, and this
module is where the line sits: everything else here is mechanical, that one is not.

**A blocked adjustment is a 200, not an error.** When a guardrail refuses a change the verdict was
still recorded and the score was still protected — that is the system working. A 4xx would tell the
analyst their action failed, when it was heard and bounded. The refusal travels in
``action: rejected`` with the guardrail's own explanation, which is what the screen shows.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from apps.api.contract import alerts as ca
from apps.api.contract import operations as co
from apps.api.contract.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page, PageInfo
from apps.api.deps import ApiError, demo_role_stub, get_connection, not_found, require_role
from apps.api.mappers import (
    alert_summary,
    audit_entry,
    detection_run,
    evidence_panel,
    family_panel,
    feedback_record,
    flow_panel,
    guardrail_setting,
    ml_panel,
    score_adjustment,
    signature_panel,
)
from packages.contracts import db
from packages.contracts import models as m
from packages.detection.feedback.service import current_feedback, submit_feedback
from packages.detection.pipeline import store

HITL = Path(__file__).resolve().parents[2]
EVALUATION_RUNS = HITL / "evaluation" / "three-arm" / "runs"

router = APIRouter()

Conn = Annotated[sqlite3.Connection, Depends(get_connection)]
Role = Annotated[str, Depends(demo_role_stub)]
AdminOnly = Depends(require_role("system_admin"))


def guardrail_values(conn: sqlite3.Connection) -> dict[str, float]:
    """The live guardrail settings, so an intervention's configured value is looked up rather than
    inferred from the delta - which produced "held at the floor of 29.89" when the floor is 70."""
    return {entry.config_key: entry.config_value for entry in store.guardrail_settings(conn)}


def _page(items: list[Any], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"items": items,
            "page": PageInfo(total=total, limit=limit, offset=offset, returned=len(items))}


# --------------------------------------------------------------------------------------------
# The analyst queue
# --------------------------------------------------------------------------------------------


@router.get("/api/alerts", response_model=Page[ca.AlertSummary], tags=["alerts"],
            operation_id="listAlerts")
def list_alerts(
    conn: Conn,
    role: Role,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    sort: str = Query("queue"),
    direction: str = Query("desc"),
    queue_class: list[str] | None = Query(None, alias="queueClass"),
    evidence_class: list[str] | None = Query(None, alias="evidenceClass"),
    severity: list[str] | None = Query(None),
    status_filter: list[str] | None = Query(None, alias="status"),
    attack_category: list[str] | None = Query(None, alias="attackCategory"),
    requires_review: bool | None = Query(None, alias="requiresReview"),
    min_score: float | None = Query(None, alias="minScore"),
    max_score: float | None = Query(None, alias="maxScore"),
    search: str | None = Query(None, max_length=200),
    run_id: int | None = Query(None, alias="runId"),
) -> dict[str, Any]:
    """The ranked queue, in the contract's order unless an inspection sort overrides it."""
    try:
        rows, total = store.queue_page(
            conn, limit=limit, offset=offset, sort=sort, direction=direction,
            queue_class=queue_class, evidence_class=evidence_class, severity=severity,
            status=status_filter, attack_category=attack_category,
            requires_review=requires_review, min_score=min_score, max_score=max_score,
            search=search, run_id=run_id)
    except ValueError as error:  # an unknown sort key or filter: refused, never ignored
        raise ApiError(400, "VALIDATION_FAILED", str(error)) from error

    judged = store.has_feedback(conn, [alert.id for alert, _ in rows])
    items = [alert_summary(alert, flow, has_feedback=alert.id in judged) for alert, flow in rows]
    return _page(items, total, limit, offset)


def _load_alert(conn: sqlite3.Connection, alert_ref: str) -> m.Alert:
    alert = store.alert_by_ref(conn, alert_ref)
    if alert is None:
        raise not_found("alert", alert_ref)
    return alert


@router.get("/api/alerts/{alertRef}", response_model=ca.AlertDetail, tags=["alerts"],
            operation_id="getAlert")
def get_alert(alertRef: str, conn: Conn, role: Role) -> ca.AlertDetail:  # noqa: N803
    """One alert and its four evidence panels. An unflagged alert is a valid response, not a 404."""
    alert = _load_alert(conn, alertRef)
    flow = store.flow_for_alert(conn, alert.id)
    if flow is None:
        raise not_found("flow for alert", alertRef)
    run = store.latest_run(conn)
    events = store.feedback_for_alert(conn, alert.id)
    latest = events[-1] if events else None
    users = store.users_by_id(conn, [e.user_id for e in events])
    family = store.family_by_key(conn, alert.family_key)

    return ca.AlertDetail(
        alert=alert_summary(alert, flow, has_feedback=bool(events)),
        flow=flow_panel(flow),
        signature=signature_panel(alert),
        ml=ml_panel(alert, model_version=run.model_version if run else None),
        evidence=evidence_panel(
            alert, fusion_scheme=(run.fusion_weights or {}).get("scheme") if run else None),
        family=family_panel(alert, family, store.family_size(conn, alert.family_key)),
        feedback_count=len(events),
        current_feedback=(feedback_record(latest, alert, users.get(latest.user_id),
                                          guardrail_values(conn)) if latest else None))


# --------------------------------------------------------------------------------------------
# Feedback — the write path. Never delegated: it invokes the guardrails.
# --------------------------------------------------------------------------------------------


def _acting_user(conn: sqlite3.Connection, role: str) -> int:
    """The demo's stand-in for a signed-in user.

    S18 replaces this with a real principal. Until then a verdict still needs an actor, because
    `feedback_events.user_id` is a foreign key and the audit trail records *who* — an unattributed
    verdict would break NFR-02 for the sake of a stub.
    """
    row = conn.execute("SELECT id FROM users WHERE role = ? ORDER BY id LIMIT 1",
                       (role,)).fetchone()
    if row is not None:
        return int(row["id"])
    with conn:
        return db.insert(conn, m.User(
            username=f"demo-{role}", password_hash="not-a-login-account",
            display_name=f"Demo {role.replace('_', ' ')}",
            email=f"{role}@demo.local", role=role))


@router.post("/api/alerts/{alertRef}/feedback", response_model=ca.FeedbackResponse,
             tags=["alerts", "feedback"], operation_id="submitFeedback")
def post_feedback(alertRef: str, body: ca.FeedbackRequest, conn: Conn,  # noqa: N803
                  role: Role) -> ca.FeedbackResponse:
    """Record one analyst verdict: guardrails, family learning and audit, in one transaction."""
    alert = _load_alert(conn, alertRef)
    user_id = _acting_user(conn, role)
    try:
        result = submit_feedback(conn, alert_id=alert.id, user_id=user_id,
                                 category=body.category, note=body.note)
    except ValueError as error:
        raise ApiError(400, "VALIDATION_FAILED", str(error)) from error

    flow = store.flow_for_alert(conn, alert.id)
    users = store.users_by_id(conn, [user_id])
    learning = result.learning
    return ca.FeedbackResponse(
        alert=alert_summary(result.alert, flow, has_feedback=True),
        feedback=feedback_record(result.feedback, result.alert, users.get(user_id),
                                 guardrail_values(conn)),
        family=ca.FamilyEffect(
            family_key=learning.after.family_key if learning else alert.family_key,
            gate_open=learning.after.gate_open if learning else False,
            gate_reason=(learning.after.gate_reason if learning else
                         "This alert does not teach a family (invariant I3)."),
            members_moved=learning.members_moved if learning else 0,
            guardrail_interventions=learning.guardrail_interventions if learning else {}),
        audit_event_ids=[entry.id for entry in result.audit if entry.id is not None])


@router.get("/api/alerts/{alertRef}/score-adjustment", response_model=ca.ScoreAdjustment,
            tags=["alerts", "feedback"], operation_id="getScoreAdjustment")
def get_score_adjustment(alertRef: str, conn: Conn, role: Role) -> ca.ScoreAdjustment:  # noqa: N803
    alert = _load_alert(conn, alertRef)
    return score_adjustment(alert, current_feedback(conn, alert.id),
                            settings=guardrail_values(conn))


@router.get("/api/alerts/{alertRef}/feedback-history", response_model=ca.FeedbackHistory,
            tags=["alerts", "feedback"], operation_id="getFeedbackHistory")
def get_feedback_history(alertRef: str, conn: Conn, role: Role) -> ca.FeedbackHistory:  # noqa: N803
    alert = _load_alert(conn, alertRef)
    events = store.feedback_for_alert(conn, alert.id)
    users = store.users_by_id(conn, [e.user_id for e in events])
    settings = guardrail_values(conn)
    records = [feedback_record(event, alert, users.get(event.user_id), settings)
               for event in events]
    return ca.FeedbackHistory(alert_ref=alert.alert_ref, events=records,
                              effective=records[-1] if records else None)


# --------------------------------------------------------------------------------------------
# Dashboard, runs, audit, guardrails
# --------------------------------------------------------------------------------------------


@router.get("/api/dashboard/summary", response_model=co.DashboardSummary, tags=["dashboard"],
            operation_id="getDashboardSummary")
def dashboard_summary(conn: Conn, role: Role) -> co.DashboardSummary:
    run = store.latest_run(conn)
    counts = store.dashboard_counts(conn)
    return co.DashboardSummary(
        generated_at=m.utc_now(), run_id=run.id if run else None,
        total_alerts=counts["total_alerts"],
        by_queue_class=[co.QueueBandCount(**band) for band in counts["by_queue_class"]],
        by_evidence_class=counts["by_evidence_class"], by_severity=counts["by_severity"],
        by_attack_category=counts["by_attack_category"],
        requires_review=counts["requires_review"], tier2_candidates=counts["tier2_candidates"],
        feedback_events=counts["feedback_events"],
        guardrail_interventions=counts["guardrail_interventions"],
        alerts_moved_by_feedback=counts["alerts_moved_by_feedback"])


@router.post("/api/detection/run", response_model=co.DetectionRunSummary,
             status_code=status.HTTP_202_ACCEPTED, tags=["detection"],
             operation_id="startDetectionRun", dependencies=[AdminOnly])
def start_detection_run(conn: Conn,
                        body: co.DetectionRunRequest | None = None) -> co.DetectionRunSummary:
    """Detection is an offline batch (D3), never inline in a request.

    The demo ships with its database already built, so this reports the existing run rather than
    launching a 21-second job inside an HTTP request. Running detection on demand belongs to S18,
    behind a task queue.
    """
    run = store.latest_run(conn)
    if run is None:
        raise ApiError(409, "CONFLICT",
                       "No detection run exists. Build one with: "
                       "python scripts/run_detection.py")
    return detection_run(
        run,
        by_evidence=store.counts_by(conn, "evidence_class", run_id=run.id),
        by_queue=store.counts_by(conn, "queue_class", run_id=run.id))


def _alert_refs(conn: sqlite3.Connection, alert_ids: list[int | None]) -> dict[int, str]:
    ids = sorted({int(i) for i in alert_ids if i is not None})
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id, alert_ref FROM alerts WHERE id IN ({', '.join('?' * len(ids))})", ids)
    return {int(row["id"]): str(row["alert_ref"]) for row in rows}


@router.get("/api/audit-log", response_model=Page[co.AuditEntryOut], tags=["audit"],
            operation_id="listAuditLog")
def list_audit_log(
    conn: Conn,
    role: Role,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: list[str] | None = Query(None, alias="eventType"),
    actor_id: int | None = Query(None, alias="actorId"),
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> dict[str, Any]:
    entries, total = store.audit_page(conn, limit=limit, offset=offset, event_type=event_type,
                                      actor_id=actor_id, since=since, until=until)
    users = store.users_by_id(conn, [entry.actor_id for entry in entries])
    refs = _alert_refs(conn, [entry.alert_id for entry in entries])
    items = [audit_entry(entry, users.get(entry.actor_id), refs.get(entry.alert_id))
             for entry in entries]
    return _page(items, total, limit, offset)


@router.get("/api/config/guardrails", response_model=co.GuardrailConfig, tags=["config"],
            operation_id="getGuardrailConfig")
def get_guardrail_config(conn: Conn, role: Role) -> co.GuardrailConfig:
    return co.GuardrailConfig(
        settings=[guardrail_setting(entry) for entry in store.guardrail_settings(conn)])


@router.put("/api/config/guardrails", response_model=co.GuardrailConfig, tags=["config"],
            operation_id="updateGuardrailConfig", dependencies=[AdminOnly])
def update_guardrail_config(body: co.GuardrailConfigUpdate, conn: Conn,
                            role: Role) -> co.GuardrailConfig:
    """Change guardrail settings. Admin only, and the rationale is recorded, not just the value."""
    changes = body.model_dump(exclude={"rationale"}, exclude_none=True)
    if not changes:
        raise ApiError(400, "VALIDATION_FAILED", "No setting was supplied")
    known = {entry.config_key for entry in store.guardrail_settings(conn)}
    unknown = set(changes) - known
    if unknown:
        raise ApiError(400, "VALIDATION_FAILED", f"Unknown guardrail settings: {sorted(unknown)}",
                       {"allowed": sorted(known)})

    actor_id = _acting_user(conn, role)
    now = m.utc_now()
    with conn:
        for key, value in changes.items():
            conn.execute("UPDATE guardrail_config SET config_value = ?, updated_at = ? "
                         "WHERE config_key = ?", (float(value), db.format_timestamp(now), key))
        db.insert(conn, m.AuditEntry(
            event_type="CONFIG_CHANGE", actor_id=actor_id, created_at=now,
            details={"changes": changes, "rationale": body.rationale}))
    return get_guardrail_config(conn, role)


# --------------------------------------------------------------------------------------------
# Evaluation — S15's results, read from the committed run records
# --------------------------------------------------------------------------------------------


@router.get("/api/evaluation/scenarios", response_model=Page[co.EvaluationScenarioOut],
            tags=["evaluation"], operation_id="listEvaluationScenarios")
def list_scenarios(conn: Conn, role: Role, limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
                   offset: int = Query(0, ge=0)) -> dict[str, Any]:
    total = int(conn.execute("SELECT COUNT(*) AS n FROM evaluation_scenarios").fetchone()["n"])
    rows = conn.execute("SELECT * FROM evaluation_scenarios ORDER BY id LIMIT ? OFFSET ?",
                        (limit, offset))
    items = []
    for row in rows:
        scenario = db.from_row(m.EvaluationScenario, row)
        config = scenario.metrics_config or {}
        items.append(co.EvaluationScenarioOut(
            scenario_id=scenario.id or 0, name=scenario.name,
            guardrails_active=scenario.guardrails_active, dataset_id=scenario.dataset_id,
            model_version=scenario.model_version, rule_set_version=scenario.rule_set_version,
            preregistration=config.get("preregistration", {}),
            sequence_digest=config.get("sequence_digest"),
            sequence_length=len(scenario.feedback_sequence),
            created_at=scenario.created_at))
    return _page(items, total, limit, offset)


def _results(run_id: str) -> dict[str, Any]:
    """One evaluation run's committed record.

    The three-arm results live in `evaluation/three-arm/runs/`, not in the demo database: each arm
    runs against its *own* copy of the database, so no single database holds the comparison. The
    run directory is the record, and it is committed.
    """
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ApiError(400, "VALIDATION_FAILED", f"Invalid run id {run_id!r}")
    path = EVALUATION_RUNS / run_id / "results.json"
    if not path.exists():
        raise not_found("evaluation run", run_id)
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/evaluation/runs/{runId}", response_model=co.EvaluationComparison,
            tags=["evaluation"], operation_id="getEvaluationRun")
def get_evaluation_run(runId: str, role: Role) -> co.EvaluationComparison:  # noqa: N803
    """The three arms and their deltas. Deltas may be negative; render them as measured."""
    results = _results(runId)
    return co.EvaluationComparison(
        run_id=results["run_id"], commit=results.get("commit"),
        preregistration=results.get("preregistration", {}),
        sequence_digest=results.get("sequence_digest"),
        sequence_length=results.get("sequence_length", 0),
        detection_metrics_identical_across_arms=results[
            "detection_metrics_identical_across_arms"],
        arms=[co.ArmResultOut(**arm) for arm in results.get("arms", [])],
        deltas=results.get("deltas", {}),
        movement={
            name: ({group: co.MovementGroup(**values) for group, values in block.items()}
                   if block else None)
            for name, block in (results.get("movement") or {}).items()},
        guardrails_prevented=results.get("guardrails_prevented", {}))


@router.get("/api/evaluation/runs/{runId}/detection",
            response_model=co.EvaluationDetectionMetrics, tags=["evaluation"],
            operation_id="getEvaluationDetectionMetrics")
def get_evaluation_detection(runId: str, role: Role) -> co.EvaluationDetectionMetrics:  # noqa: N803
    """Per-class metrics. Identical across all three arms by construction."""
    results = _results(runId)
    arms = results.get("full_metrics", {})
    if not arms:
        raise not_found("detection metrics for evaluation run", runId)
    metrics = next(iter(arms.values()))
    detection, queue, safety = metrics["detection"], metrics["queue"], metrics["safety"]
    return co.EvaluationDetectionMetrics(
        alerts=detection["alerts"], attacks=detection["attacks"],
        macro_f1=detection["macro_f1"],
        per_class={name: co.ClassMetrics(**values)
                   for name, values in detection["per_class"].items()},
        flagged_vs_benign=co.ClassMetrics(**detection["flagged_vs_benign"]),
        precision_at=[co.PrecisionAtK(k=int(k), **values) for k, values in
                      sorted(queue["precision_at"].items(), key=lambda kv: int(kv[0]))],
        saturation=co.SaturationMetrics(**queue["saturation"]),
        signature_override=co.SignatureOverridePreservation(**safety["signature_override"]))
