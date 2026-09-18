"""S10a — the API contract, before a single handler exists.

The plan's verification for S10a is "contract test per endpoint; role stub blocks analyst from
`PUT /api/config/guardrails`". The latency requirement (NFR-04, p95 < 2s) belongs to S10b, which is
where code actually runs; asserting it here would be theatre.

What these tests protect:

* **every endpoint the plan lists exists**, so S10b has a complete target and S11 a complete client;
* **the document and the models cannot drift** — every `$ref` resolves, every model is reachable,
  and the committed `openapi.json` matches what the models generate;
* **the queue's order is the contract's**, cited rather than restated (`deviations.md` C13);
* **ground truth cannot leak through the API** — the first component that could expose it;
* **the guardrail story is representable**, because a response carrying only the final score would
  make the project's safety claim invisible;
* **`duplicate` is not a feedback category**, because the approved documents say it is.
"""

from __future__ import annotations

import json
from typing import Any, get_args

import pytest

from apps.api.contract import alerts as a
from apps.api.contract import operations as o
from apps.api.contract.common import (
    MAX_PAGE_SIZE,
    QUEUE_ORDER,
    ErrorResponse,
    QueueQuery,
)
from apps.api.contract.openapi import MODELS, openapi_document
from packages.contracts import db
from packages.contracts import models as m
from scripts.build_openapi import TARGET, rendered

#: Every endpoint the plan's S10a task list names. `GET /api/evaluation/*` is expanded to the
#: three concrete endpoints S14 needs.
REQUIRED_OPERATIONS = {
    # S18a: sign-in. The one operation without an Authorization parameter, plus the session check.
    ("/api/auth/login", "post"),
    ("/api/auth/me", "get"),
    ("/api/alerts", "get"),
    # S7b made visible: the queue grouped by similar-alert family. Declared here because
    # this is a deliberate addition to the demo surface, not an endpoint added in passing.
    ("/api/alerts/families", "get"),
    ("/api/alerts/{alertRef}", "get"),
    ("/api/alerts/{alertRef}/feedback", "post"),
    ("/api/alerts/{alertRef}/score-adjustment", "get"),
    ("/api/alerts/{alertRef}/feedback-history", "get"),
    ("/api/dashboard/summary", "get"),
    ("/api/detection/run", "post"),
    ("/api/audit-log", "get"),
    ("/api/config/guardrails", "get"),
    ("/api/config/guardrails", "put"),
    ("/api/evaluation/scenarios", "get"),
    ("/api/evaluation/runs", "get"),  # S14: the runs are files, so the evaluator needs a listing
    # Console rebuild: triage (B1, B2), breakdowns (B4), entity view (B5).
    ("/api/alerts/{alertRef}/status", "post"),
    ("/api/alerts/{alertRef}/assign", "post"),
    ("/api/alerts/{alertRef}/notes", "get"),
    ("/api/alerts/{alertRef}/notes", "post"),
    ("/api/dashboard/breakdowns", "get"),
    ("/api/entities/ip/{ip}", "get"),
    ("/api/admin/reports/ips", "get"),
    ("/api/admin/reports/ip/{ip}", "get"),
    ("/api/evaluation/runs/{runId}", "get"),
    ("/api/evaluation/runs/{runId}/detection", "get"),
}


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return openapi_document()


def refs(node: Any) -> set[str]:
    """Every `$ref` anywhere in the document."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.add(value)
            else:
                found |= refs(value)
    elif isinstance(node, list):
        for item in node:
            found |= refs(item)
    return found


# --------------------------------------------------------------------------------------------
# The surface the plan specifies
# --------------------------------------------------------------------------------------------

def test_every_endpoint_the_plan_lists_exists(document):
    present = {(path, method) for path, methods in document["paths"].items() for method in methods}
    missing = REQUIRED_OPERATIONS - present
    assert not missing, f"the plan's S10a task list names endpoints the contract lacks: {missing}"


def test_no_endpoint_beyond_the_demo_path(document):
    """"Adding endpoints while we're here" is on the plan's anti-pattern list; the other ~25 TDM
    endpoints are S18."""
    present = {(path, method) for path, methods in document["paths"].items() for method in methods}
    assert present == REQUIRED_OPERATIONS, f"undeclared endpoints: {present - REQUIRED_OPERATIONS}"


def test_every_operation_has_a_unique_operation_id(document):
    ids = [op["operationId"] for methods in document["paths"].values() for op in methods.values()]
    assert len(ids) == len(set(ids)), "duplicate operationId; a generated client would collide"


# --------------------------------------------------------------------------------------------
# The document and the models cannot drift apart
# --------------------------------------------------------------------------------------------

def test_every_ref_resolves(document):
    schemas = document["components"]["schemas"]
    for ref in refs(document):
        assert ref.startswith("#/components/schemas/"), f"unexpected $ref target {ref}"
        name = ref.rsplit("/", 1)[-1]
        assert name in schemas, f"{ref} points at a schema that does not exist"


def test_every_declared_model_is_in_the_document(document):
    schemas = document["components"]["schemas"]
    for model in MODELS:
        assert model.__name__ in schemas, f"{model.__name__} is declared but never emitted"


def test_no_orphan_schemas(document):
    """A schema nothing references is either dead or a forgotten wiring-up."""
    schemas = set(document["components"]["schemas"])
    referenced = {ref.rsplit("/", 1)[-1] for ref in refs(document)}
    orphans = schemas - referenced
    assert not orphans, f"schemas nothing references: {sorted(orphans)}"


def test_the_committed_document_is_up_to_date():
    """The same check `scripts/build_openapi.py --check` performs. S11 generates its client from
    the committed file, so a stale one is a client built against a contract nobody agreed."""
    assert TARGET.exists(), "apps/api/openapi.json has never been built"
    assert TARGET.read_text(encoding="utf-8") == rendered(), (
        "apps/api/openapi.json is out of date - run: python scripts/build_openapi.py")


def test_the_committed_document_is_openapi_3_1():
    parsed = json.loads(TARGET.read_text(encoding="utf-8"))
    assert parsed["openapi"].startswith("3.1")
    assert parsed["info"]["title"] and parsed["info"]["version"]


# --------------------------------------------------------------------------------------------
# The decisions the contract has to carry
# --------------------------------------------------------------------------------------------

def test_the_queue_order_is_the_contract_order(document):
    """Cited, not restated. Ordering by `evidence_priority` — plan v1.0's withdrawn instruction —
    would hide the re-ranking that feedback performs."""
    assert QUEUE_ORDER == db.QUEUE_ORDER_BY
    described = document["paths"]["/api/alerts"]["get"]["description"]
    assert db.QUEUE_ORDER_BY in described
    assert QueueQuery().sort == "queue"


def test_alerts_are_identified_by_uuid_not_row_id(document):
    summary = document["components"]["schemas"]["AlertSummary"]["properties"]
    assert "alertRef" in summary
    assert "id" not in summary, "row ids must never be exposed"
    path = document["paths"]["/api/alerts/{alertRef}"]["get"]
    assert any(p["name"] == "alertRef" and p["schema"]["format"] == "uuid"
               for p in path["parameters"])


def test_both_score_columns_are_in_the_queue_row(document):
    """The dashboard's second score column is the demo's point."""
    summary = document["components"]["schemas"]["AlertSummary"]["properties"]
    assert "detectionScore" in summary and "combinedScore" in summary


def test_the_wire_is_camel_case():
    payload = QueueQuery(limit=10, queue_class=["corroborated"]).model_dump(
        by_alias=True, exclude_none=True)
    assert "queueClass" in payload and "queue_class" not in payload


def test_duplicate_is_not_a_feedback_category(document):
    """URS UC-SA-15 defines `duplicate` as a queue action — link to the original and suppress —
    not a score change. The documents' "six categories" folds the two together."""
    category = document["components"]["schemas"]["FeedbackRequest"]["properties"]["category"]
    enum = category.get("enum") or category["allOf"][0].get("enum")
    assert "duplicate" not in enum
    assert set(enum) == set(get_args(m.FeedbackCategory))
    assert len(enum) == 5


def test_the_feedback_response_can_tell_the_whole_guardrail_story(document):
    """original -> requested -> bound -> actual -> final. A response with only the final score
    would make the guardrails invisible, and they are the safety claim."""
    chain = document["components"]["schemas"]["ScoreAdjustment"]["properties"]
    for field in ("detectionScore", "scoreBefore", "requestedDelta", "actualDelta", "scoreAfter",
                  "action", "interventions", "summary"):
        assert field in chain, f"the adjustment chain cannot express {field}"


def test_a_guardrail_intervention_explains_itself(document):
    intervention = document["components"]["schemas"]["GuardrailInterventionOut"]["properties"]
    assert "code" in intervention and "explanation" in intervention


def test_the_family_effect_is_reportable(document):
    """S7b is the project's core claim; an API that cannot say "four similar alerts moved" cannot
    demonstrate it."""
    effect = document["components"]["schemas"]["FamilyEffect"]["properties"]
    assert "membersMoved" in effect and "gateOpen" in effect


def test_the_admin_write_is_role_gated(document):
    """The plan's named verification: an analyst account is blocked from the guardrail config."""
    put = document["paths"]["/api/config/guardrails"]["put"]
    assert put["x-required-role"] == "system_admin"
    assert "403" in put["responses"] and "401" in put["responses"]
    assert any(parameter["name"] == "Authorization" for parameter in put["parameters"])


def test_changing_guardrails_requires_a_rationale():
    """The audit entry records why, not just what (NFR-02)."""
    with pytest.raises(ValueError):
        o.GuardrailConfigUpdate(critical_alert_floor=60)  # type: ignore[call-arg]
    assert o.GuardrailConfigUpdate(critical_alert_floor=60, rationale="tuning").rationale


def test_evaluation_deltas_may_be_negative():
    """S15 measured precision@50 falling 1.000 -> 0.980. A contract that could only express
    improvement would be a contract that lies."""
    comparison = o.EvaluationComparison(
        run_id="20260912T032022Z", sequence_length=40,
        detection_metrics_identical_across_arms=True,
        deltas={"B_minus_A": {"precision_at_50": -0.02, "false_positives_in_top_50": -1.0}})
    assert comparison.deltas["B_minus_A"]["precision_at_50"] < 0


def test_signature_override_preservation_allows_a_null_rate():
    """Zero such alerts must report `null` and a note, never a flattering 100%."""
    block = o.SignatureOverridePreservation(
        alerts=0, changed=0, preservation_rate=None, note="no signature_override alert exists")
    assert block.preservation_rate is None and block.note


# --------------------------------------------------------------------------------------------
# Leakage — the API is the first component that could expose the answers
# --------------------------------------------------------------------------------------------

FORBIDDEN = frozenset({"groundTruth", "ground_truth", "attackClass", "attack_class",
                       "isAttempted", "is_attempted", "attemptedCategory", "label", "Label"})


def test_no_wire_model_exposes_ground_truth(document):
    """Ground truth is not in the schema at all (`deviations.md` A7) and must not re-enter through
    a response model. `attackCategory` is the system's *assigned* class and is allowed;
    `attackClass` is the capture's truth and is not."""
    for name, schema in document["components"]["schemas"].items():
        leaks = set(schema.get("properties", {})) & FORBIDDEN
        assert not leaks, f"{name} would leak ground truth: {sorted(leaks)}"


def test_the_flow_panel_exposes_the_join_key_but_no_label(document):
    """`sourceRecordId` is the evaluation's join key and is safe to show: an identifier, not an
    answer."""
    flow = document["components"]["schemas"]["FlowPanel"]["properties"]
    assert "sourceRecordId" in flow
    assert not set(flow) & FORBIDDEN


# --------------------------------------------------------------------------------------------
# Paging and errors
# --------------------------------------------------------------------------------------------

def test_page_size_is_bounded():
    assert QueueQuery().limit <= MAX_PAGE_SIZE
    with pytest.raises(ValueError):
        QueueQuery(limit=MAX_PAGE_SIZE + 1)


def test_list_endpoints_return_the_pagination_envelope(document):
    for path in ("/api/alerts", "/api/audit-log", "/api/evaluation/scenarios"):
        schema = (document["paths"][path]["get"]["responses"]["200"]["content"]
                  ["application/json"]["schema"])
        assert set(schema["required"]) == {"items", "page"}, f"{path} is not paginated"


def test_the_error_envelope_is_one_shape():
    error = ErrorResponse(error={"code": "NOT_FOUND", "message": "No such alert"})
    payload = error.model_dump(by_alias=True, exclude_none=True)
    assert payload == {"error": {"code": "NOT_FOUND", "message": "No such alert"}}


def test_unknown_fields_are_refused():
    """`extra="forbid"`: a client sending a field the contract does not define is a bug, and it
    should surface at the boundary rather than be silently dropped."""
    with pytest.raises(ValueError):
        a.FeedbackRequest(category="mark_false_positive", nonsense=1)  # type: ignore[call-arg]
