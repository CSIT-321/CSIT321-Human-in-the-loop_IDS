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
from apps.api.contract.routing import RoutingView, RoutingResponse
from packages.detection.routing import RoutingRequest
from apps.api.contract.external_admission import ExternalAdmissionView, ExternalAdmissionResponse
from packages.detection.external_admission import AdmissionRequest, EligibilityRequest
from apps.api.contract.responses import ResponsePage
from packages.detection.triage_memory import MemoryReviewRequest,MemoryDecisionRequest,MemoryMutation,MemoryView,MemoryAudit,MemoryMatch
from packages.detection.selective_review import ReviewCommand,ReviewView,ReviewMutation,ReviewEvent,ReviewMetrics
from packages.detection.response_approval import ResponseRequest,ManualResponseRequest,ResponseDecisionRequest,ResponseMutation
from packages.detection.tier2_cases import (
    CaseView, CaseEvent, CaseMutation, CreateCaseRequest, CaseCommand, LinkCaseRequest, FindingRequest,
)
from apps.api.contract.common import (
    FAMILY_QUERY_OMITS,
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
    ReviewCommand,ReviewView,ReviewMutation,ReviewEvent,ReviewMetrics,
    MemoryReviewRequest,MemoryDecisionRequest,MemoryMutation,MemoryView,MemoryAudit,MemoryMatch,
    ResponsePage,ResponseRequest,ManualResponseRequest,ResponseDecisionRequest,ResponseMutation,
    CaseView, CaseEvent, CaseMutation, CreateCaseRequest, CaseCommand, LinkCaseRequest, FindingRequest,
    ExternalAdmissionView, ExternalAdmissionResponse, AdmissionRequest, EligibilityRequest,
    RoutingView, RoutingResponse, RoutingRequest,
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
    a.SimilarityBasis,
    a.FamilyRow,
    a.MovedMember,
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

**Alerts are addressed by UUID.** V2 routing uses the separate operational alert UUID;
V2 state/audit bodies include internal correlation ids, never legacy alert identifiers.

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
        "/api/alerts/families": {
            "get": {
                "operationId": "listAlertFamilies",
                "summary": "The queue grouped by similar-alert family",
                "description":
                    "The same queue, grouped by what the system calls similar: attack class, "
                    "destination port, protocol and matched rule must all agree (plus the "
                    "destination IP when nothing flagged the flow). Exact match, no threshold.\n\n"
                    "This is how similar-alert learning is *seen*. A verdict re-scores every "
                    "unjudged member of its family, and ungrouped those alerts are scattered "
                    "through the queue with nothing naming them as a group. Each row carries the "
                    "family's gate state and applied adjustment; `familyKey` reads the members "
                    "back through `GET /api/alerts`.\n\n"
                    "Groups are ordered by `bestRank` — their highest-ranked member's position in "
                    "the contract queue order — so this is the queue's own order, not a second "
                    "ranking. Alerts with no family are excluded.",
                "tags": ["alerts"],
                "parameters": [AUTH_PARAMETER,
                               *(parameter for parameter in _query_parameters(QueueQuery)
                                 if parameter["name"] not in FAMILY_QUERY_OMITS)],
                "responses": {"200": {"description": "A page of families",
                                      **_page_of(a.FamilyRow)}, **_errors(400)},
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
    paths['/api/v2/alerts'] = {'get': {
        'operationId': 'listV2Routing', 'summary': 'List explicitly materialized V2 alerts',
        'tags': ['V2 routing'], 'parameters': [AUTH_PARAMETER,
            {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 50}},
            {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 0, 'default': 0}}],
        'responses': {'200': {'description': 'V2 routing page', **_page_of(RoutingView)}, **_errors(400)}}}
    paths['/api/v2/alerts/{alertRef}/triage-state'] = {'get': {
        'operationId': 'getV2Routing', 'summary': 'Read V2 state and latest routing decision',
        'tags': ['V2 routing'], 'parameters': [AUTH_PARAMETER, ALERT_REF],
        'responses': {'200': {'description': 'V2 state', **_json(RoutingView)}, **_errors(400, 404)}}}
    for suffix, operation in [('admit-tier1', 'admitV2Tier1'), ('tier2/approve', 'approveV2Tier2'),
                              ('tier2/reject', 'rejectV2Tier2'), ('tier2/escalate', 'escalateV2Tier2')]:
        paths['/api/v2/alerts/{alertRef}/' + suffix] = {'post': {
            'operationId': operation, 'summary': operation, 'tags': ['V2 routing'],
            'parameters': [AUTH_PARAMETER, ALERT_REF],
            'x-required-roles': ['security_analyst', 'system_admin'],
            'requestBody': {'required': True, **_json(RoutingRequest)},
            'responses': {'200': {'description': 'Audited decision or idempotent replay', **_json(RoutingResponse)},
                          **_errors(400, 403, 404, 409)}}}
    inbox_parameter = {'name': 'inboxId', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
    paths['/api/v2/external-alerts'] = {'get': {
        'operationId': 'listExternalAdmissions', 'summary': 'Inspect staged external alerts and admission status',
        'tags': ['External admission'], 'parameters': [AUTH_PARAMETER,
            {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 200, 'default': 50}},
            {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 0, 'default': 0}}],
        'responses': {'200': {'description': 'External inbox page', **_page_of(ExternalAdmissionView)}, **_errors(400)}}}
    paths['/api/v2/external-alerts/{inboxId}'] = {'get': {
        'operationId': 'getExternalAdmission', 'summary': 'Read eligibility and operational admission',
        'tags': ['External admission'], 'parameters': [AUTH_PARAMETER, inbox_parameter],
        'responses': {'200': {'description': 'External status', **_json(ExternalAdmissionView)}, **_errors(400, 404)}}}
    for suffix, operation, request_model, response_model in [
        ('eligibility', 'reviewExternalEligibility', EligibilityRequest, ExternalAdmissionView),
        ('admit', 'admitExternalAlert', AdmissionRequest, ExternalAdmissionResponse)]:
        paths['/api/v2/external-alerts/{inboxId}/' + suffix] = {'post': {
            'operationId': operation, 'summary': operation, 'tags': ['External admission'],
            'parameters': [AUTH_PARAMETER, inbox_parameter],
            'x-required-roles': ['security_analyst', 'system_admin'],
            'requestBody': {'required': True, **_json(request_model)},
            'responses': {'200': {'description': 'Audited external admission decision', **_json(response_model)},
                          **_errors(400, 403, 404, 409)}}}
    case_ref = {'name':'caseRef','in':'path','required':True,'schema':{'type':'string','format':'uuid'}}
    paging = [
        {'name':'limit','in':'query','schema':{'type':'integer','minimum':1,'maximum':200,'default':50}},
        {'name':'offset','in':'query','schema':{'type':'integer','minimum':0,'default':0}}]
    paths['/api/v2/tier2/cases'] = {'get': {
        'operationId':'listTier2Cases','summary':'List formal Tier 2 cases','tags':['Tier 2 cases'],
        'parameters':[AUTH_PARAMETER,*paging],
        'responses':{'200':{'description':'Case page',**_page_of(CaseView)},**_errors(400)}}}
    paths['/api/v2/tier2/cases/{caseRef}'] = {'get': {
        'operationId':'getTier2Case','summary':'Read case and immutable handoff','tags':['Tier 2 cases'],
        'parameters':[AUTH_PARAMETER,case_ref],
        'responses':{'200':{'description':'Case',**_json(CaseView)},**_errors(400,404)}}}
    paths['/api/v2/tier2/cases/{caseRef}/events'] = {'get': {
        'operationId':'listTier2CaseEvents','summary':'Read immutable investigation timeline','tags':['Tier 2 cases'],
        'parameters':[AUTH_PARAMETER,case_ref,*paging,
            {'name':'action','in':'query','schema':{'anyOf':[{'type':'string','enum':['create','link','note','finding','start']},{'type':'null'}]}}],
        'responses':{'200':{'description':'Case history page',**_page_of(CaseEvent)},**_errors(400,404)}}}
    case_operations = [
        ('/api/v2/alerts/{alertRef}/tier2/case','createTier2Case',CreateCaseRequest,ALERT_REF),
        ('/api/v2/tier2/cases/{caseRef}/alerts','linkTier2CaseAlert',LinkCaseRequest,case_ref),
        ('/api/v2/tier2/cases/{caseRef}/notes','addTier2CaseNote',CaseCommand,case_ref),
        ('/api/v2/tier2/cases/{caseRef}/findings','recordTier2CaseFinding',FindingRequest,case_ref),
        ('/api/v2/tier2/cases/{caseRef}/start-investigation','startTier2Investigation',CaseCommand,case_ref)]
    for path, operation, request_model, ref in case_operations:
        paths[path] = {'post': {
            'operationId':operation,'summary':operation,'tags':['Tier 2 cases'],
            'parameters':[AUTH_PARAMETER,ref], 'x-required-roles':['security_analyst','system_admin'],
            'requestBody':{'required':True,**_json(request_model)},
            'responses':{'200':{'description':'Audited case decision',**_json(CaseMutation)},**_errors(400,403,404,409)}}}
    response_ref = {'name':'recommendationRef','in':'path','required':True,'schema':{'type':'string','format':'uuid'}}
    response_root = '/api/v2/tier2/cases/{caseRef}/responses'
    paths[response_root] = {'get': {
        'operationId':'listCaseResponses','summary':'Read proposals and immutable human decisions','tags':['Response plans'],
        'parameters':[AUTH_PARAMETER,case_ref,*paging],
        'responses':{'200':{'description':'Response plans, never execution results',**_json(ResponsePage)},**_errors(400,404)}}}
    for suffix,operation,model,parameters in [
        ('/recommend','recommendCaseResponse',ResponseRequest,[AUTH_PARAMETER,case_ref]),
        ('/manual','proposeManualCaseResponse',ManualResponseRequest,[AUTH_PARAMETER,case_ref]),
        ('/{recommendationRef}/approve','approveCaseResponse',ResponseDecisionRequest,[AUTH_PARAMETER,case_ref,response_ref]),
        ('/{recommendationRef}/reject','rejectCaseResponse',ResponseDecisionRequest,[AUTH_PARAMETER,case_ref,response_ref])]:
        paths[response_root+suffix] = {'post':{
            'operationId':operation,'summary':operation,'tags':['Response plans'],'parameters':parameters,
            'x-required-roles':['security_analyst','system_admin'],'requestBody':{'required':True,**_json(model)},
            'responses':{'200':{'description':'Recorded proposal or human decision; not executed',**_json(ResponseMutation)},
                         **_errors(400,403,404,409)}}}
    lesson_ref={'name':'lessonRef','in':'path','required':True,'schema':{'type':'string','format':'uuid'}}
    alert_ref={'name':'alertRef','in':'path','required':True,'schema':{'type':'string','format':'uuid'}}
    for path,operation,model,parameters in [
        ('/api/v2/triage-memory','listTriageMemory',MemoryView,[AUTH_PARAMETER,*paging]),
        ('/api/v2/triage-memory/{lessonRef}','getTriageMemory',MemoryView,[AUTH_PARAMETER,lesson_ref]),
        ('/api/v2/triage-memory/{lessonRef}/events','listTriageMemoryEvents',MemoryAudit,[AUTH_PARAMETER,lesson_ref,*paging]),
        ('/api/v2/alerts/{alertRef}/triage-memory/matches','matchTriageMemory',MemoryMatch,[AUTH_PARAMETER,alert_ref,*paging])]:
        paths[path]={'get':{'operationId':operation,'summary':operation,'tags':['Triage memory'],'parameters':parameters,
            'responses':{'200':{'description':'Advisory memory; human review remains required',**(_json(model) if operation=='getTriageMemory' else _page_of(model))},**_errors(400,404)}}}
    for path,operation,model,ref in [
        ('/api/v2/alerts/{alertRef}/triage-memory/candidate','recordMemoryHumanReview',MemoryReviewRequest,alert_ref),
        ('/api/v2/triage-memory/{lessonRef}/activate','activateTriageMemory',MemoryDecisionRequest,lesson_ref),
        ('/api/v2/triage-memory/{lessonRef}/reject','rejectTriageMemory',MemoryDecisionRequest,lesson_ref)]:
        paths[path]={'post':{'operationId':operation,'summary':operation,'tags':['Triage memory'],'parameters':[AUTH_PARAMETER,ref],
            'x-required-roles':['security_analyst','system_admin'],'requestBody':{'required':True,**_json(model)},
            'responses':{'200':{'description':'Immutable human memory decision',**_json(MemoryMutation)},**_errors(400,403,404,409)}}}
    for path,operation,model,parameters,paged in [
        ('/api/v2/selective-review','listSelectiveReviews',ReviewView,[AUTH_PARAMETER,*paging,{'name':'disposition','in':'query','required':False,'schema':{'type':'string','enum':['must_review','recommended_review','no_immediate_review']}}],True),
        ('/api/v2/selective-review/metrics','selectiveReviewMetrics',ReviewMetrics,[AUTH_PARAMETER],False),
        ('/api/v2/alerts/{alertRef}/selective-review','getSelectiveReview',ReviewView,[AUTH_PARAMETER,alert_ref],False),
        ('/api/v2/alerts/{alertRef}/selective-review/events','selectiveReviewHistory',ReviewEvent,[AUTH_PARAMETER,alert_ref,*paging],True)]:
        paths[path]={'get':{'operationId':operation,'summary':operation,'tags':['Selective review'],'parameters':parameters,
            'responses':{'200':{'description':'Live review disposition and immutable history',**(_page_of(model) if paged else _json(model))},**_errors(400,404)}}}
    for suffix,operation in [('evaluate','applySelectiveReview'),('require-human','requireHumanReview')]:
        paths['/api/v2/alerts/{alertRef}/selective-review/'+suffix]={'post':{'operationId':operation,'summary':operation,
            'tags':['Selective review'],'parameters':[AUTH_PARAMETER,alert_ref],'x-required-roles':['security_analyst','system_admin'],
            'requestBody':{'required':True,**_json(ReviewCommand)},'responses':{'200':{'description':'Recorded policy or human override',**_json(ReviewMutation)},**_errors(400,403,404,409)}}}
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
            {"name":"Selective review","description":"Separate review disposition, never a human verdict or closure"},
            {"name":"Triage memory","description":"Human lessons and advisory contextual matching"},
            {"name":"Response plans","description":"Recommendations and human authorization; no execution"},
            {"name":"Tier 2 cases","description":"Explicit investigation cases, not automated response"},
            {"name": "External admission", "description": "Eligibility review and atomic operational admission"},
            {"name": "V2 routing", "description": "Explicit authenticated operational routing"},
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
