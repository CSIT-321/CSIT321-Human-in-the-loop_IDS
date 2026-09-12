"""The OpenAPI 3.1 document for the demo API (plan step S10a).

**Hand-authored paths, generated schemas.** The plan says "hand-authored OpenAPI", and the reason is
sound: FastAPI generates OpenAPI *from* handlers, so a generated document cannot exist before S10b
and S11 would have nothing to build against. But hand-typing the *schemas* would be a second copy of
the Pydantic models, free to drift from them — the precise failure this project has already paid for
once in its planning documents. So the split is:

* **paths, parameters, responses, role rules** — written here, by hand, because they are decisions;
* **schemas** — derived from the models with ``model_json_schema``, because they are consequences.

``tests/test_api_contract.py`` checks that every path references a schema that exists and that every
model is reachable, so neither half can rot quietly.

**When S10b lands**, FastAPI will generate its own document from the handlers. That generated
document must match this one; a difference is the handlers failing to implement the contract, not
the contract being out of date.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from apps.api.contract import alerts as a
from apps.api.contract import operations as o
from apps.api.contract.common import (
    MAX_PAGE_SIZE,
    QUEUE_ORDER,
    ROLE_HEADER,
    ErrorResponse,
    PageInfo,
    QueueQuery,
)

OPENAPI_VERSION = "3.1.0"
API_VERSION = "0.1.0"
SCHEMA_REF = "#/components/schemas/{model}"

#: Every model that appears on the wire. Listed explicitly rather than discovered, so adding a
#: model to the API is a deliberate act.
MODELS: tuple[type[BaseModel], ...] = (
    ErrorResponse,
    PageInfo,
    a.AlertSummary,
    a.AlertDetail,
    a.FlowPanel,
    a.SignaturePanel,
    a.RuleMatchPanel,
    a.MlPanel,
    a.ShapFeature,
    a.EvidencePanel,
    a.FamilyPanel,
    a.FeedbackRequest,
    a.FeedbackResponse,
    a.FeedbackRecord,
    a.FeedbackHistory,
    a.FamilyEffect,
    a.ScoreAdjustment,
    a.GuardrailInterventionOut,
    o.DashboardSummary,
    o.QueueBandCount,
    o.DetectionRunRequest,
    o.DetectionRunSummary,
    o.AuditEntryOut,
    o.GuardrailConfig,
    o.GuardrailSetting,
    o.GuardrailConfigUpdate,
    o.EvaluationScenarioOut,
    o.EvaluationComparison,
    o.EvaluationDetectionMetrics,
    o.ArmResultOut,
    o.MovementGroup,
    o.ClassMetrics,
    o.PrecisionAtK,
    o.SaturationMetrics,
    o.SignatureOverridePreservation,
)

DESCRIPTION = f"""
The demo API for the Human-in-the-Loop IDS dashboard (FYP-26-S3-13).

**Deliberately narrow.** Only the endpoints the demo path exercises; the remaining TDM surface is
S18. Adding endpoints "while we're here" is on the plan's anti-pattern list.

**Authentication is a stub.** Send `{ROLE_HEADER}: security_analyst | system_admin | evaluator`.
Real JWT/bcrypt with RBAC is S18. The stub is enforced only where a role genuinely gates an action,
so `PUT /api/config/guardrails` refuses anything but `system_admin`.

**Queue ordering is fixed by contract**: `{QUEUE_ORDER}`. Feedback moves an alert between queue
*bands*, never across evidence classes, so a client that re-sorts by `evidenceClass` will hide the
re-ranking the system exists to perform.

**Alerts are identified by `alertRef` (UUID).** Row ids are never exposed.

**Every flow becomes an alert**, including flows no detector flagged. They are the queue's bottom
band and the evaluation's denominator.
""".strip()


def _schemas() -> dict[str, Any]:
    """Component schemas for every wire model, with $refs pointing into components."""
    components: dict[str, Any] = {}
    for model in MODELS:
        schema = model.model_json_schema(ref_template=SCHEMA_REF, by_alias=True)
        components.update(schema.pop("$defs", {}))
        components[model.__name__] = schema
    return dict(sorted(components.items()))


def _ref(model: type[BaseModel] | str) -> dict[str, str]:
    name = model if isinstance(model, str) else model.__name__
    return {"$ref": SCHEMA_REF.format(model=name)}


def _json(model: type[BaseModel] | str) -> dict[str, Any]:
    return {"content": {"application/json": {"schema": _ref(model)}}}


def _page_of(model: type[BaseModel]) -> dict[str, Any]:
    """The pagination envelope, inlined per item type: OpenAPI has no generics."""
    return {"content": {"application/json": {"schema": {
        "type": "object",
        "required": ["items", "page"],
        "properties": {"items": {"type": "array", "items": _ref(model)}, "page": _ref(PageInfo)},
    }}}}


def _errors(*codes: int) -> dict[str, Any]:
    text = {
        400: "Validation failed", 403: "Role not permitted", 404: "Not found",
        409: "Conflict", 422: "Guardrail rejected the request",
    }
    return {str(code): {"description": text[code], **_json(ErrorResponse)} for code in codes}


def _query_parameters(model: type[BaseModel]) -> list[dict[str, Any]]:
    """Flatten a query model into OpenAPI ``parameters``.

    Query models are deliberately **not** component schemas: a client generator turns `parameters`
    into function arguments and never dereferences a body schema for them, so emitting one would
    be dead weight. Deriving them from the model is still what keeps them from drifting.
    """
    schema = model.model_json_schema(ref_template=SCHEMA_REF, by_alias=True)
    schema.pop("$defs", None)
    required = set(schema.get("required", []))
    return [
        {"name": name, "in": "query", "required": name in required,
         "description": spec.get("description"), "schema": spec}
        for name, spec in schema["properties"].items()
    ]


ROLE_PARAMETER = {
    "name": ROLE_HEADER, "in": "header", "required": False,
    "description": "Role-switch stub (S18 replaces this with a real principal)",
    "schema": {"type": "string", "enum": ["security_analyst", "system_admin", "evaluator"]},
}

ALERT_REF = {
    "name": "alertRef", "in": "path", "required": True,
    "description": "The alert's public UUID",
    "schema": {"type": "string", "format": "uuid"},
}

RUN_ID = {"name": "runId", "in": "path", "required": True,
          "schema": {"type": "string"},
          "description": "Evaluation run id, e.g. 20260912T032022Z"}


def _paths() -> dict[str, Any]:
    return {
        "/api/alerts": {
            "get": {
                "operationId": "listAlerts",
                "summary": "The ranked analyst queue",
                "description": f"Ordered by `{QUEUE_ORDER}` unless `sort` overrides it. "
                               f"`sort=queue` is the contract order and what the demo shows; the "
                               f"other keys are inspection tools, not alternative rankings. "
                               f"Maximum page size {MAX_PAGE_SIZE}.",
                "tags": ["alerts"],
                "parameters": [ROLE_PARAMETER, *_query_parameters(QueueQuery)],
                "responses": {"200": {"description": "A page of the queue",
                                      **_page_of(a.AlertSummary)}, **_errors(400)},
            }
        },
        "/api/alerts/{alertRef}": {
            "get": {
                "operationId": "getAlert",
                "summary": "One alert: flow, signature, model and combined evidence",
                "description": "An alert no detector flagged is a valid response, not a 404.",
                "tags": ["alerts"],
                "parameters": [ROLE_PARAMETER, ALERT_REF],
                "responses": {"200": {"description": "The alert and its four evidence panels",
                                      **_json(a.AlertDetail)}, **_errors(404)},
            }
        },
        "/api/alerts/{alertRef}/feedback": {
            "post": {
                "operationId": "submitFeedback",
                "summary": "Record an analyst verdict",
                "description": "Invokes the guardrails and the family learning in one transaction. "
                               "The response carries the full adjustment chain so the caller can "
                               "show what bound the change. A rejected adjustment is a 200 with "
                               "`action: rejected`, not an error — the verdict was recorded and the "
                               "score was protected.",
                "tags": ["alerts", "feedback"],
                "parameters": [ROLE_PARAMETER, ALERT_REF],
                "requestBody": {"required": True, **_json(a.FeedbackRequest)},
                "responses": {"200": {"description": "The verdict, its adjustment and its family "
                                                     "effect", **_json(a.FeedbackResponse)},
                              **_errors(400, 404, 422)},
            }
        },
        "/api/alerts/{alertRef}/score-adjustment": {
            "get": {
                "operationId": "getScoreAdjustment",
                "summary": "The current adjustment chain for one alert",
                "tags": ["alerts", "feedback"],
                "parameters": [ROLE_PARAMETER, ALERT_REF],
                "responses": {"200": {"description": "original, requested, bound, actual, final",
                                      **_json(a.ScoreAdjustment)}, **_errors(404)},
            }
        },
        "/api/alerts/{alertRef}/feedback-history": {
            "get": {
                "operationId": "getFeedbackHistory",
                "summary": "Every verdict on one alert, oldest first",
                "description": "Append-only. An amendment is a new record citing the one it "
                               "supersedes; `effective` names the verdict currently in force.",
                "tags": ["alerts", "feedback"],
                "parameters": [ROLE_PARAMETER, ALERT_REF],
                "responses": {"200": {"description": "The verdict history",
                                      **_json(a.FeedbackHistory)}, **_errors(404)},
            }
        },
        "/api/dashboard/summary": {
            "get": {
                "operationId": "getDashboardSummary",
                "summary": "Queue composition and feedback activity",
                "tags": ["dashboard"],
                "parameters": [ROLE_PARAMETER],
                "responses": {"200": {"description": "Summary counts",
                                      **_json(o.DashboardSummary)}},
            }
        },
        "/api/detection/run": {
            "post": {
                "operationId": "startDetectionRun",
                "summary": "Start a batch detection run",
                "description": "Detection is an offline batch (D3), never inline in a request.",
                "tags": ["detection"],
                "parameters": [ROLE_PARAMETER],
                "requestBody": {"required": False, **_json(o.DetectionRunRequest)},
                "responses": {"202": {"description": "The run was accepted",
                                      **_json(o.DetectionRunSummary)},
                              **_errors(400, 403, 409)},
                "x-required-role": "system_admin",
            }
        },
        "/api/audit-log": {
            "get": {
                "operationId": "listAuditLog",
                "summary": "The append-only audit trail",
                "tags": ["audit"],
                "parameters": [ROLE_PARAMETER, *_query_parameters(o.AuditQuery)],
                "responses": {"200": {"description": "A page of audit entries",
                                      **_page_of(o.AuditEntryOut)}, **_errors(400, 403)},
            }
        },
        "/api/config/guardrails": {
            "get": {
                "operationId": "getGuardrailConfig",
                "summary": "Current guardrail settings",
                "tags": ["config"],
                "parameters": [ROLE_PARAMETER],
                "responses": {"200": {"description": "The settings",
                                      **_json(o.GuardrailConfig)}},
            },
            "put": {
                "operationId": "updateGuardrailConfig",
                "summary": "Change guardrail settings (system_admin only)",
                "description": "A rationale is required: the audit entry records why, not just "
                               "what. An analyst role receives 403.",
                "tags": ["config"],
                "parameters": [ROLE_PARAMETER],
                "requestBody": {"required": True, **_json(o.GuardrailConfigUpdate)},
                "responses": {"200": {"description": "The updated settings",
                                      **_json(o.GuardrailConfig)}, **_errors(400, 403)},
                "x-required-role": "system_admin",
            },
        },
        "/api/evaluation/scenarios": {
            "get": {
                "operationId": "listEvaluationScenarios",
                "summary": "Pre-registered evaluation scenarios",
                "tags": ["evaluation"],
                "parameters": [ROLE_PARAMETER],
                "responses": {"200": {"description": "A page of scenarios",
                                      **_page_of(o.EvaluationScenarioOut)}},
            }
        },
        "/api/evaluation/runs/{runId}": {
            "get": {
                "operationId": "getEvaluationRun",
                "summary": "Three-arm comparison for one evaluation run",
                "description": "Deltas may be negative and must be rendered as measured.",
                "tags": ["evaluation"],
                "parameters": [ROLE_PARAMETER, RUN_ID],
                "responses": {"200": {"description": "Arms, deltas and what the guardrails "
                                                     "prevented",
                                      **_json(o.EvaluationComparison)}, **_errors(404)},
            }
        },
        "/api/evaluation/runs/{runId}/detection": {
            "get": {
                "operationId": "getEvaluationDetectionMetrics",
                "summary": "Per-class detection metrics for one evaluation run",
                "description": "Identical across all three arms by construction — feedback never "
                               "changes the detection decision.",
                "tags": ["evaluation"],
                "parameters": [ROLE_PARAMETER, RUN_ID],
                "responses": {"200": {"description": "Per-class metrics, saturation and I3",
                                      **_json(o.EvaluationDetectionMetrics)}, **_errors(404)},
            }
        },
    }


def openapi_document() -> dict[str, Any]:
    """The whole contract, as a single OpenAPI 3.1 document."""
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "HITL IDS demo API",
            "version": API_VERSION,
            "description": DESCRIPTION,
        },
        "servers": [{"url": "http://localhost:8000", "description": "Local demo"}],
        "tags": [
            {"name": "alerts", "description": "The analyst queue and one alert's evidence"},
            {"name": "feedback", "description": "Verdicts, guardrails and family learning"},
            {"name": "dashboard", "description": "Queue composition"},
            {"name": "detection", "description": "Batch runs"},
            {"name": "audit", "description": "The append-only trail"},
            {"name": "config", "description": "Guardrail settings (admin)"},
            {"name": "evaluation", "description": "S15's three-arm results"},
        ],
        "paths": _paths(),
        "components": {"schemas": _schemas()},
    }
