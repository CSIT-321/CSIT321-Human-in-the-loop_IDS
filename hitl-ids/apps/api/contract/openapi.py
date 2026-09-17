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
from apps.api.contract import auth as au
from apps.api.contract import operations as o
from apps.api.contract.common import (
    MAX_PAGE_SIZE,
    QUEUE_ORDER,
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
    au.LoginRequest,
    au.LoginResponse,
    au.MeResponse,
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
    a.StatusChangeRequest,
    a.AssignRequest,
    a.TriageResponse,
    a.NoteRequest,
    a.NoteOut,
    a.AlertNotes,
    o.DashboardSummary,
    o.DashboardBreakdowns,
    o.TopValue,
    o.TimeBucket,
    o.EntityIp,
    o.IpReportSummary,
    o.IpAttackBehaviour,
    o.IpTargetHost,
    o.IpDestinationPort,
    o.IpReportTimelineRow,
    o.IpReportRecommendation,
    o.IpSecurityReport,
    o.SourceIpOverviewRow,
    o.SourceIpOverviewPage,
    o.QueueBandCount,
    o.DetectionRunRequest,
    o.DetectionRunSummary,
    o.AuditEntryOut,
    o.GuardrailConfig,
    o.GuardrailSetting,
    o.GuardrailConfigUpdate,
    o.EvaluationScenarioOut,
    o.EvaluationRunOut,
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

**Authentication is real (S18a).** `POST /api/auth/login` with one of the three seeded accounts
returns a JWT bearer token; send it as `Authorization: Bearer <token>` on every other request. No
token, a forged token or an expired one is a 401. The role gates only where a role genuinely gates
an action, so `PUT /api/config/guardrails` refuses anything but `system_admin`.

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
        400: "Validation failed", 401: "Not signed in, or the token expired",
        403: "Role not permitted", 404: "Not found",
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


#: Every protected operation carries this. Optional in the document only so a generated client's
#: call sites stay token-free — the console's session middleware stamps the header on every
#: request (``apps/web/src/api/client.ts``), and API consumers who manage headers themselves get a
#: 401 with the standard envelope if they forget.
AUTH_PARAMETER = {
    "name": "Authorization", "in": "header", "required": False,
    "description": "`Bearer <token>` from POST /api/auth/login",
    "schema": {"type": "string", "example": "Bearer eyJhbGciOiJIUzI1NiJ9..."},
}

ALERT_REF = {
    "name": "alertRef", "in": "path", "required": True,
    "description": "The alert's public UUID",
    "schema": {"type": "string", "format": "uuid"},
}

IP_PATH = {"name": "ip", "in": "path", "required": True,
           "description": "An IPv4 or IPv6 address", "schema": {"type": "string"}}

TOP_LIMIT = {"name": "limit", "in": "query", "required": False,
             "description": "How many top values to return per list",
             "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}

REPORT_FROM_DATE = {
    "name": "fromDate", "in": "query", "required": False,
    "description": "Inclusive lower bound on recorded flow capture date (YYYY-MM-DD)",
    "schema": {"type": "string", "format": "date"},
}

REPORT_TO_DATE = {
    "name": "toDate", "in": "query", "required": False,
    "description": "Inclusive upper bound on recorded flow capture date (YYYY-MM-DD)",
    "schema": {"type": "string", "format": "date"},
}

RUN_ID = {"name": "runId", "in": "path", "required": True,
          "schema": {"type": "string"},
          "description": "Evaluation run id, e.g. 20260912T032022Z"}


def _paths() -> dict[str, Any]:
    paths = {
        "/api/auth/login": {
            "post": {
                "operationId": "login",
                "summary": "Sign in and receive a bearer token",
                "description": "One of the three seeded accounts — one per role, so a view is a "
                               "person, not a hat. The response's role comes from the account; a "
                               "client cannot choose it. A wrong username, a wrong password and a "
                               "disabled account all answer the same 401.",
                "tags": ["auth"],
                "requestBody": {"required": True, **_json(au.LoginRequest)},
                "responses": {"200": {"description": "The token and the account it names",
                                      **_json(au.LoginResponse)},
                              **_errors(401)},
            }
        },
        "/api/auth/me": {
            "get": {
                "operationId": "getCurrentUser",
                "summary": "The signed-in account",
                "description": "Who the token says is calling — the session check.",
                "tags": ["auth"],
                "parameters": [AUTH_PARAMETER],
                "responses": {"200": {"description": "The account named by the token",
                                      **_json(au.MeResponse)},
                              **_errors(401)},
            }
        },
        "/api/alerts": {
            "get": {
                "operationId": "listAlerts",
                "summary": "The ranked analyst queue",
                "description": f"Ordered by `{QUEUE_ORDER}` unless `sort` overrides it. "
                               f"`sort=queue` is the contract order and what the demo shows; the "
                               f"other keys are inspection tools, not alternative rankings. "
                               f"Maximum page size {MAX_PAGE_SIZE}.",
                "tags": ["alerts"],
                "parameters": [AUTH_PARAMETER, *_query_parameters(QueueQuery)],
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
                "parameters": [AUTH_PARAMETER, ALERT_REF],
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
                "parameters": [AUTH_PARAMETER, ALERT_REF],
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
                "parameters": [AUTH_PARAMETER, ALERT_REF],
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
                "parameters": [AUTH_PARAMETER, ALERT_REF],
                "responses": {"200": {"description": "The verdict history",
                                      **_json(a.FeedbackHistory)}, **_errors(404)},
            }
        },
        "/api/alerts/{alertRef}/status": {
            "post": {
                "operationId": "changeAlertStatus",
                "summary": "Claim, work, resolve, dismiss, release or reopen an alert",
                "description": "Workflow, not judgement: never moves a score or invokes a guardrail. "
                               "Working an alert makes the caller its owner when it has none. A "
                               "refused transition is a 409. Writes an ALERT_STATUS_CHANGE audit "
                               "entry.",
                "tags": ["alerts", "triage"],
                "parameters": [AUTH_PARAMETER, ALERT_REF],
                "requestBody": {"required": True, **_json(a.StatusChangeRequest)},
                "responses": {"200": {"description": "The alert after the change",
                                      **_json(a.TriageResponse)},
                              **_errors(400, 403, 404, 409)},
                "x-required-role": "security_analyst | system_admin",
            }
        },
        "/api/alerts/{alertRef}/assign": {
            "post": {
                "operationId": "assignAlert",
                "summary": "Assign an alert to the caller, or unassign it",
                "tags": ["alerts", "triage"],
                "parameters": [AUTH_PARAMETER, ALERT_REF],
                "requestBody": {"required": True, **_json(a.AssignRequest)},
                "responses": {"200": {"description": "The alert after the change",
                                      **_json(a.TriageResponse)},
                              **_errors(400, 403, 404, 409)},
                "x-required-role": "security_analyst | system_admin",
            }
        },
        "/api/alerts/{alertRef}/notes": {
            "get": {
                "operationId": "listAlertNotes",
                "summary": "The alert's notes thread, oldest first",
                "tags": ["alerts", "triage"],
                "parameters": [AUTH_PARAMETER, ALERT_REF],
                "responses": {"200": {"description": "The thread", **_json(a.AlertNotes)},
                              **_errors(404)},
            },
            "post": {
                "operationId": "addAlertNote",
                "summary": "Add a note to the alert",
                "description": "Append-only: a correction is a new note.",
                "tags": ["alerts", "triage"],
                "parameters": [AUTH_PARAMETER, ALERT_REF],
                "requestBody": {"required": True, **_json(a.NoteRequest)},
                "responses": {"200": {"description": "The stored note", **_json(a.NoteOut)},
                              **_errors(400, 403, 404)},
                "x-required-role": "security_analyst | system_admin",
            },
        },
        "/api/dashboard/breakdowns": {
            "get": {
                "operationId": "getDashboardBreakdowns",
                "summary": "Top talkers, verdict and status mix, guardrail actions, capture-time "
                           "histogram",
                "description": "Recorded flows: the histogram is capture time, not a live rate.",
                "tags": ["dashboard"],
                "parameters": [AUTH_PARAMETER, TOP_LIMIT],
                "responses": {"200": {"description": "Breakdowns",
                                      **_json(o.DashboardBreakdowns)}, **_errors(400)},
            }
        },
        "/api/entities/ip/{ip}": {
            "get": {
                "operationId": "getIpEntity",
                "summary": "Everything the recorded flows say about one IP address",
                "tags": ["entities"],
                "parameters": [AUTH_PARAMETER, IP_PATH, TOP_LIMIT],
                "responses": {"200": {"description": "The address's alerts, peers and ports",
                                      **_json(o.EntityIp)}, **_errors(400, 404)},
            }
        },
        "/api/admin/reports/ip/{ip}": {
            "get": {
                "operationId": "getAdminIpSecurityReport",
                "summary": "A read-only security report for one source IP",
                "description": "Uses recorded flow capture time and the latest effective analyst "
                               "verdict per alert. It never uses hidden ground truth and performs "
                               "no blocking action.",
                "tags": ["reports"],
                "parameters": [AUTH_PARAMETER, IP_PATH, REPORT_FROM_DATE, REPORT_TO_DATE],
                "responses": {
                    "200": {"description": "Source-IP activity, verdicts and advisory",
                            **_json(o.IpSecurityReport)},
                    **_errors(400, 403),
                },
                "x-required-role": "system_admin",
            }
        },
        "/api/admin/reports/ips": {
            "get": {
                "operationId": "getAdminSourceIpOverview",
                "summary": "Paginated security overview of recorded source IPs",
                "description": "Source-only aggregation over recorded flow capture time and the "
                               "latest effective analyst verdict. Destination-only appearances "
                               "and hidden ground truth are excluded.",
                "tags": ["reports"],
                "parameters": [AUTH_PARAMETER, *_query_parameters(o.SourceIpOverviewQuery)],
                "responses": {
                    "200": {"description": "Sortable source-IP alert and verdict counts",
                            **_json(o.SourceIpOverviewPage)},
                    **_errors(400, 403),
                },
                "x-required-role": "system_admin",
            }
        },
        "/api/dashboard/summary": {
            "get": {
                "operationId": "getDashboardSummary",
                "summary": "Queue composition and feedback activity",
                "tags": ["dashboard"],
                "parameters": [AUTH_PARAMETER],
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
                "parameters": [AUTH_PARAMETER],
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
                "parameters": [AUTH_PARAMETER, *_query_parameters(o.AuditQuery)],
                "responses": {"200": {"description": "A page of audit entries",
                                      **_page_of(o.AuditEntryOut)}, **_errors(400, 403)},
            }
        },
        "/api/config/guardrails": {
            "get": {
                "operationId": "getGuardrailConfig",
                "summary": "Current guardrail settings",
                "tags": ["config"],
                "parameters": [AUTH_PARAMETER],
                "responses": {"200": {"description": "The settings",
                                      **_json(o.GuardrailConfig)}},
            },
            "put": {
                "operationId": "updateGuardrailConfig",
                "summary": "Change guardrail settings (system_admin only)",
                "description": "A rationale is required: the audit entry records why, not just "
                               "what. An analyst role receives 403.",
                "tags": ["config"],
                "parameters": [AUTH_PARAMETER],
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
                "parameters": [AUTH_PARAMETER],
                "responses": {"200": {"description": "A page of scenarios",
                                      **_page_of(o.EvaluationScenarioOut)}},
            }
        },
        "/api/evaluation/runs": {
            "get": {
                "operationId": "listEvaluationRuns",
                "summary": "Committed three-arm evaluation runs, newest first",
                "description": "Read from evaluation/three-arm/runs/, not from a database: each arm "
                               "runs against its own database copy.",
                "tags": ["evaluation"],
                "parameters": [AUTH_PARAMETER],
                "responses": {"200": {"description": "A page of runs",
                                      **_page_of(o.EvaluationRunOut)}},
            }
        },
        "/api/evaluation/runs/{runId}": {
            "get": {
                "operationId": "getEvaluationRun",
                "summary": "Three-arm comparison for one evaluation run",
                "description": "Deltas may be negative and must be rendered as measured.",
                "tags": ["evaluation"],
                "parameters": [AUTH_PARAMETER, RUN_ID],
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
                "parameters": [AUTH_PARAMETER, RUN_ID],
                "responses": {"200": {"description": "Per-class metrics, saturation and I3",
                                      **_json(o.EvaluationDetectionMetrics)}, **_errors(404)},
            }
        },
    }
    # Every operation except login can answer 401 — a missing or expired sign-in is a fact of every
    # protected path, not a per-path decision, so it is stamped once here rather than repeated in
    # the literal above.
    for path, operations in paths.items():
        if path == "/api/auth/login":
            continue
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["responses"]["401"] = _errors(401)["401"]
    return paths


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
            {"name": "auth", "description": "Sign-in and the current session"},
            {"name": "alerts", "description": "The analyst queue and one alert's evidence"},
            {"name": "feedback", "description": "Verdicts, guardrails and family learning"},
            {"name": "dashboard", "description": "Queue composition"},
            {"name": "detection", "description": "Batch runs"},
            {"name": "audit", "description": "The append-only trail"},
            {"name": "config", "description": "Guardrail settings (admin)"},
            {"name": "reports", "description": "Read-only administrator security reports"},
            {"name": "evaluation", "description": "S15's three-arm results"},
        ],
        "paths": _paths(),
        "components": {"schemas": _schemas()},
    }
