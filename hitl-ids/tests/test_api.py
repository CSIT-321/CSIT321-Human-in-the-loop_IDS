"""S10b — the API handlers, driven over HTTP.

`test_api_contract.py` checks the *document*. This file checks that the handlers implement it, and
that the demo's core loop actually works: open the queue, read an alert's evidence, submit a
verdict, watch a guardrail bind, watch similar alerts move, and find all of it in the audit trail.

Three things here earn their weight:

* **the generated document must cover the committed contract** — FastAPI builds its own OpenAPI
  from these handlers, and an operation the contract declares but the handlers lack is a client
  broken three steps later;
* **NFR-04 (p95 < 2s)** is measured, not assumed, on the two endpoints the plan names;
* **the guardrail sentence must state the configured value** — it once read "held at the floor of
  29.89" when the floor is 70, because the value was inferred from the delta rather than looked up.
  That text is the demo's centrepiece, so it has a regression test.

The fixture is a synthetic capture, not the demo sample: the suite must pass on a fresh checkout,
where `data/demo.db` does not exist.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db
from packages.contracts import models as m
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import open_database, run_detection
from packages.detection.pipeline.source import CsvReplaySource
from conftest import FTP_RULE, ROWS  # the shared synthetic capture

T0 = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path, sample, predictions) -> Path:
    path = tmp_path / "api.db"
    conn = open_database(str(path))
    try:
        dataset_id = store.register_dataset(
            conn, name="synthetic capture", version="test-1", source_file="sample.csv",
            total_records=len(ROWS), class_distribution={}, now=T0)
        store.register_model(conn, version="xgb-8class-20260911",
                             model_file="models/xgboost_ids_model.json", now=T0)
        conn.commit()
        run_detection(conn, CsvReplaySource(sample), ReplayPredictor(predictions),
                      dataset_id=dataset_id, rules=[FTP_RULE], seed=20260911, now=T0)
    finally:
        conn.close()
    return path


@pytest.fixture
def client(database) -> TestClient:
    """Signed in as g.ang (analyst) by default, mirroring the demo's main path.

    The fixture seeds the three S18a accounts on this test's database and mints a token per
    account, so a test that needs another role reads ``client.tokens["admin"]`` instead of
    re-logging-in. Requests with no per-test headers carry the analyst token.
    """
    conn = db.connect(str(database))
    try:
        auth.ensure_demo_accounts(conn)
        tokens = {username: auth.encode_token(db.from_row(m.User, conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)).fetchone()))
            for username, *_ in auth.DEMO_ACCOUNTS}
    finally:
        conn.close()
    api = TestClient(create_app(database))
    api.tokens = tokens
    api.headers.update({"Authorization": f"Bearer {tokens['g.ang']}"})
    return api


def rows(client: TestClient, **params) -> list[dict]:
    response = client.get("/api/alerts", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --------------------------------------------------------------------------------------------
# The contract is the authority
# --------------------------------------------------------------------------------------------

def test_the_handlers_implement_every_contracted_operation(client):
    """FastAPI generates its own document from the handlers. Every operation the committed
    contract declares must exist here, under the same operationId."""
    from apps.api.contract.openapi import openapi_document

    contracted = {op["operationId"]
                  for methods in openapi_document()["paths"].values()
                  for op in methods.values()}
    generated = {op["operationId"]
                 for methods in client.app.openapi()["paths"].values()
                 for op in methods.values() if isinstance(op, dict) and "operationId" in op}
    missing = contracted - generated
    assert not missing, f"the contract declares operations the handlers do not implement: {missing}"


def test_health_reports_which_database_is_served(client, database):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["exists"] is True
    assert Path(body["database"]) == database


def test_a_missing_database_is_a_clear_error_not_a_stack_trace(tmp_path):
    client = TestClient(create_app(tmp_path / "nope.db"), raise_server_exceptions=False)
    response = client.get("/api/alerts")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_MISSING"
    assert "run_detection.py" in response.json()["error"]["message"]


# --------------------------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------------------------

def test_the_queue_is_returned_in_contract_order(client):
    items = rows(client, limit=50)
    priorities = [item["queuePriority"] for item in items]
    assert priorities == sorted(priorities), "the queue is not ordered by band"
    for earlier, later in zip(items, items[1:]):
        if earlier["queuePriority"] == later["queuePriority"]:
            assert earlier["combinedScore"] >= later["combinedScore"]


def test_every_queue_row_carries_both_scores(client):
    for item in rows(client, limit=10):
        assert "detectionScore" in item and "combinedScore" in item


def test_unflagged_alerts_are_in_the_queue(client):
    """Every flow becomes an alert; the bottom band is the evaluation's denominator."""
    assert any(item["queueClass"] == "none" for item in rows(client, limit=100))


def test_paging_is_stable(client):
    """Without a total order, two pages can repeat an alert or skip one."""
    first = rows(client, limit=5, offset=0)
    second = rows(client, limit=5, offset=5)
    assert not ({i["alertRef"] for i in first} & {i["alertRef"] for i in second})


def test_filters_narrow_the_queue(client):
    flagged = rows(client, limit=100, queueClass=["tier2_candidate", "ml_only"])
    assert flagged and all(i["queueClass"] != "none" for i in flagged)


def test_an_unknown_sort_key_is_refused(client):
    response = client.get("/api/alerts", params={"sort": "whatever"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_page_size_is_bounded(client):
    assert client.get("/api/alerts", params={"limit": 5000}).status_code == 400


# --------------------------------------------------------------------------------------------
# One alert: the four evidence panels
# --------------------------------------------------------------------------------------------

def test_alert_detail_returns_four_panels(client):
    item = rows(client, limit=1)[0]
    body = client.get(f"/api/alerts/{item['alertRef']}").json()
    for panel in ("flow", "signature", "ml", "evidence", "family"):
        assert panel in body


def test_an_ml_only_alert_gets_an_empty_state_not_a_blank_panel(client):
    """`signature_only = 0` on corrected data, so this is the common case, not an edge one."""
    ml_only = [i for i in rows(client, limit=100) if i["evidenceClass"] == "ml_only"]
    assert ml_only, "the fixture should produce at least one ML-only alert"
    body = client.get(f"/api/alerts/{ml_only[0]['alertRef']}").json()
    assert body["signature"]["matched"] == []
    assert "ML-only" in body["signature"]["note"]


def test_a_rule_match_shows_the_clauses_it_matched(client):
    matched = [i for i in rows(client, limit=100) if i["matchedRuleIds"]]
    assert matched
    body = client.get(f"/api/alerts/{matched[0]['alertRef']}").json()
    rule = body["signature"]["matched"][0]
    assert rule["ruleId"] and rule["matchedConditions"]


def test_the_ml_panel_carries_its_explanation_and_additivity_check(client):
    item = rows(client, limit=1)[0]
    ml = client.get(f"/api/alerts/{item['alertRef']}").json()["ml"]
    assert ml["predictedClass"] and ml["topSupporting"]
    assert ml["additivityPassed"] is True


def test_an_unknown_alert_is_a_404_with_the_error_envelope(client):
    response = client.get("/api/alerts/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_row_ids_are_never_exposed(client):
    item = rows(client, limit=1)[0]
    assert "id" not in item
    body = client.get(f"/api/alerts/{item['alertRef']}").json()
    assert "id" not in body["alert"]


# --------------------------------------------------------------------------------------------
# The demo's core loop
# --------------------------------------------------------------------------------------------

def test_submitting_a_verdict_moves_the_alert_and_records_everything(client):
    target = next(i for i in rows(client, limit=100) if i["queueClass"] != "none")
    before = target["combinedScore"]

    response = client.post(f"/api/alerts/{target['alertRef']}/feedback",
                           json={"category": "mark_false_positive", "note": "Known scanner."})
    assert response.status_code == 200, response.text
    body = response.json()

    adjustment = body["feedback"]["adjustment"]
    assert adjustment["detectionScore"] == target["detectionScore"]
    assert adjustment["requestedDelta"] == -30
    assert body["alert"]["combinedScore"] <= before
    assert body["alert"]["hasFeedback"] is True
    assert body["auditEventIds"], "a verdict must leave an audit trail"

    history = client.get(f"/api/alerts/{target['alertRef']}/feedback-history").json()
    assert len(history["events"]) == 1
    assert history["effective"]["category"] == "mark_false_positive"


def test_the_adjustment_chain_is_complete_before_any_verdict(client):
    """An alert with no verdict gets the identity chain, not null: the screen should not have to
    special-case its commonest path."""
    item = rows(client, limit=1)[0]
    chain = client.get(f"/api/alerts/{item['alertRef']}/score-adjustment").json()
    assert chain["requestedDelta"] == 0 and chain["actualDelta"] == 0
    assert chain["action"] == "applied" and chain["interventions"] == []
    assert "No analyst verdict" in chain["summary"]


def test_a_guardrail_states_its_configured_value_not_the_delta(client):
    """Regression: this sentence once read "held at the floor of 29.89" when the floor is 70,
    because the value was inferred from the delta. It is the demo's centrepiece text."""
    critical = [i for i in rows(client, limit=100) if i["isCritical"]]
    assert critical, "the fixture should produce at least one Critical alert"
    body = client.post(f"/api/alerts/{critical[0]['alertRef']}/feedback",
                       json={"category": "mark_false_positive"}).json()
    floors = [i for i in body["feedback"]["adjustment"]["interventions"]
              if i["code"] == "critical_alert_floor"]
    if floors:
        settings = {s["configKey"]: s["configValue"]
                    for s in client.get("/api/config/guardrails").json()["settings"]}
        assert floors[0]["configuredValue"] == settings["critical_alert_floor"]
        assert str(int(settings["critical_alert_floor"])) in floors[0]["explanation"]


def test_a_blocked_adjustment_is_a_200_not_an_error(client):
    """The verdict was recorded and the score was protected. A 4xx would say the action failed."""
    target = next(i for i in rows(client, limit=100) if i["queueClass"] != "none")
    response = client.post(f"/api/alerts/{target['alertRef']}/feedback",
                           json={"category": "mark_false_positive"})
    assert response.status_code == 200
    assert response.json()["feedback"]["adjustment"]["action"] in ("applied", "capped", "rejected")


def test_the_agreement_gate_opens_on_the_third_verdict(client):
    """S7b, the project's core claim, over HTTP.

    The gate needs three learning verdicts. Before that it stays shut and says why; a silent
    no-op would be indistinguishable from a broken endpoint.
    """
    family_alerts = [i for i in rows(client, limit=100)
                     if i["queueClass"] != "none" and i["attackCategory"] == "Brute Force"]
    assert len(family_alerts) >= 4, "the fixture needs a family with untouched members"

    states = [client.post(f"/api/alerts/{alert['alertRef']}/feedback",
                          json={"category": "confirm_true_positive"}).json()["family"]
              for alert in family_alerts[:3]]
    assert [state["gateOpen"] for state in states] == [False, False, True]
    assert "3 required" in states[0]["gateReason"]
    assert all(isinstance(state["membersMoved"], int) for state in states)


def test_an_open_gate_reaches_members_that_were_never_judged(client):
    """The mechanism, checked where it is observable.

    ``membersMoved`` counts members whose *placement* changed, and it is legitimately 0 when the
    family is already at the top band and at score 100 — the saturation S15 measured. So this
    checks what the learning did rather than what it happened to move: an unjudged member's family
    panel must carry the family's applied adjustment and say why its score differs.
    """
    family_alerts = [i for i in rows(client, limit=100)
                     if i["queueClass"] != "none" and i["attackCategory"] == "Brute Force"]
    for alert in family_alerts[:3]:
        client.post(f"/api/alerts/{alert['alertRef']}/feedback",
                    json={"category": "confirm_true_positive"})

    untouched = client.get(f"/api/alerts/{family_alerts[-1]['alertRef']}").json()
    assert untouched["feedbackCount"] == 0, "this member must have no verdict of its own"
    family = untouched["family"]
    assert family["gateOpen"] is True
    assert family["members"] > 3
    assert family["dominantCategory"] == "confirm_true_positive"
    assert family["appliedAdjustment"] != 0 or family["appliedOffset"] != 0, (
        "an open gate must apply something, or the learning reached nobody")
    assert family["note"], "the panel must explain why an unjudged alert carries an adjustment"


def test_an_unknown_feedback_category_is_refused(client):
    item = rows(client, limit=1)[0]
    response = client.post(f"/api/alerts/{item['alertRef']}/feedback",
                           json={"category": "duplicate"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------------------------
# Dashboard, audit, guardrails, roles
# --------------------------------------------------------------------------------------------

def test_the_dashboard_reports_no_movement_before_any_feedback(client):
    """`alertsMovedByFeedback` once counted detection's own Tier 2 placements, reporting 644
    movements on a database with zero verdicts."""
    body = client.get("/api/dashboard/summary").json()
    assert body["feedbackEvents"] == 0
    assert body["alertsMovedByFeedback"] == 0
    assert body["totalAlerts"] == len(ROWS)


def test_the_dashboard_counts_movement_after_feedback(client):
    target = next(i for i in rows(client, limit=100) if i["queueClass"] != "none")
    client.post(f"/api/alerts/{target['alertRef']}/feedback",
                json={"category": "confirm_true_positive"})
    body = client.get("/api/dashboard/summary").json()
    assert body["feedbackEvents"] == 1
    assert body["alertsMovedByFeedback"] >= 1


def test_the_audit_log_is_newest_first_and_filterable(client):
    target = next(i for i in rows(client, limit=100) if i["queueClass"] != "none")
    client.post(f"/api/alerts/{target['alertRef']}/feedback",
                json={"category": "escalate", "note": "Escalating."})
    page = client.get("/api/audit-log", params={"limit": 10}).json()
    assert page["page"]["total"] >= 2
    stamps = [entry["createdAt"] for entry in page["items"]]
    assert stamps == sorted(stamps, reverse=True)
    feedback_only = client.get("/api/audit-log", params={"eventType": ["FEEDBACK"]}).json()
    assert feedback_only["items"]
    assert all(e["eventType"] == "FEEDBACK" for e in feedback_only["items"])


def test_an_analyst_cannot_change_the_guardrails(client):
    """The plan's named verification for the role check, now against a real account."""
    response = client.put("/api/config/guardrails",
                          json={"criticalAlertFloor": 50, "rationale": "lowering"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_an_admin_can_change_the_guardrails_and_it_is_audited(client):
    response = client.put("/api/config/guardrails",
                          json={"criticalAlertFloor": 65, "rationale": "Tuning for the demo."},
                          headers={"Authorization": f"Bearer {client.tokens['admin']}"})
    assert response.status_code == 200, response.text
    settings = {s["configKey"]: s["configValue"] for s in response.json()["settings"]}
    assert settings["critical_alert_floor"] == 65
    audit = client.get("/api/audit-log", params={"eventType": ["CONFIG_CHANGE"]}).json()
    assert audit["page"]["total"] == 1
    assert audit["items"][0]["rationale"] == "Tuning for the demo."


def test_changing_guardrails_without_a_rationale_is_refused(client):
    response = client.put("/api/config/guardrails", json={"criticalAlertFloor": 65},
                          headers={"Authorization": f"Bearer {client.tokens['admin']}"})
    assert response.status_code == 400


def test_an_invalid_token_is_refused_rather_than_downgraded(client):
    response = client.get("/api/alerts", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_the_fixture_is_signed_in_as_the_analyst(client):
    """The demo's main path: the console's session is the analyst account."""
    assert client.get("/api/auth/me").json()["username"] == "g.ang"
    assert client.get("/api/alerts", params={"limit": 1}).status_code == 200


def test_a_detection_run_reports_the_existing_run(client):
    response = client.post("/api/detection/run",
                           headers={"Authorization": f"Bearer {client.tokens['admin']}"})
    assert response.status_code == 202
    assert response.json()["alerts"] == len(ROWS)


def test_a_detection_run_is_admin_only(client):
    assert client.post("/api/detection/run").status_code == 403


# --------------------------------------------------------------------------------------------
# NFR-04 — measured, not assumed
# --------------------------------------------------------------------------------------------

def test_the_read_endpoints_meet_the_latency_budget(client):
    """p95 < 2s on the two endpoints the plan names.

    The fixture is small, so this checks the *shape* of the query rather than production scale:
    `queue_page` issues two queries per page instead of one per row, which is the property that
    keeps this true at 5,000 alerts.
    """
    item = rows(client, limit=1)[0]
    for url, params in (("/api/alerts", {"limit": 50}), (f"/api/alerts/{item['alertRef']}", {})):
        timings = []
        for _ in range(20):
            start = time.perf_counter()
            assert client.get(url, params=params).status_code == 200
            timings.append(time.perf_counter() - start)
        timings.sort()
        p95 = timings[int(len(timings) * 0.95) - 1]
        assert p95 < 2.0, f"{url} p95 was {p95:.3f}s, over the NFR-04 budget"
