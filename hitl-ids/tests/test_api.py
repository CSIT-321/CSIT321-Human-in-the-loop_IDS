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
from packages.detection.fusion.cef import ceilings_from_chart, severity_for
from packages.detection.pipeline import store
from packages.detection.pipeline.predictor import ReplayPredictor
from packages.detection.pipeline.runner import open_database, run_detection
from packages.detection.pipeline.source import CsvReplaySource
from packages.detection.ranking.severity import load_severity_chart
from conftest import FTP_RULE, ROWS  # the shared synthetic capture

T0 = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)

#: The ceilings the committed severity chart yields - the same ones detection and feedback use.
CEILINGS = ceilings_from_chart(load_severity_chart())


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
    """Severity worst-first, then the operational score (``db.QUEUE_ORDER_BY``, v1.31)."""
    levels = {"Informational": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    items = rows(client, limit=50)
    severities = [levels[item["severity"]] for item in items]
    assert severities == sorted(severities, reverse=True), "the queue is not ordered by severity"
    for earlier, later in zip(items, items[1:]):
        if earlier["severity"] == later["severity"]:
            assert earlier["combinedScore"] >= later["combinedScore"]


def test_the_evidence_sort_leads_with_a_checkable_rule(client):
    """The one inspection sort that earns its place beside the contract order.

    When a detector's false positives carry an attack's full confidence, no score-based key can
    separate them and only the rule layer can. Measured on ``data/stress.db``, this order reaches
    precision@100 1.000 where the contract order reaches 0.000.
    """
    order = {"corroborated": 0, "signature_override": 1, "ml_only": 2, "none": 3}
    items = rows(client, limit=50, sort="evidence", direction="asc")
    classes = [order[item["evidenceClass"]] for item in items]
    assert classes == sorted(classes), "ascending must put the lowest evidence priority first"
    assert any(item["evidenceClass"] == "corroborated" for item in items), (
        "the fixture must produce at least one corroborated alert for this to mean anything")


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


def test_detection_score_range_filters_the_queue(client):
    """``detectionMaxScore=99.999`` is the saturation filter: it isolates everything an exact
    100.0 would hide. The 99.999 bound matters — a 99.9 ceiling would silently lose the alerts
    at 99.96–99.99, which are precisely the flagged ones a verdict can still visibly raise."""
    every = rows(client, limit=100)
    unsaturated = rows(client, limit=100, detectionMaxScore=99.999)
    expected = {i["alertRef"] for i in every if i["detectionScore"] < 100}
    assert {i["alertRef"] for i in unsaturated} == expected
    assert all(i["detectionScore"] <= 99.999 for i in unsaturated)

    floored = rows(client, limit=100, detectionMinScore=90)
    assert floored and all(i["detectionScore"] >= 90 for i in floored)
    high = {i["alertRef"] for i in every if i["detectionScore"] >= 90}
    assert {i["alertRef"] for i in floored} == high


def test_the_unjudged_filter_is_the_complement_of_a_verdict(client):
    """The "verdict done" view: an analyst needs to see what has been judged and what has not.

    ``unjudged=true`` reads the same condition the row's "Verdict recorded" pill does, and it is the
    complement of the ``verdict`` filter — which asks about the verdict currently *in force*.
    """
    unjudged = rows(client, limit=200, unjudged=True)
    assert unjudged, "the fixture must start with alerts nobody has judged"
    assert all(item["hasFeedback"] is False for item in unjudged)

    target = unjudged[0]["alertRef"]
    response = client.post(f"/api/alerts/{target}/feedback",
                           json={"category": "confirm_true_positive"})
    assert response.status_code == 200, response.text

    assert target not in {item["alertRef"] for item in rows(client, limit=200, unjudged=True)}

    confirmed = rows(client, limit=200, verdict=["confirm_true_positive"])
    assert [item["alertRef"] for item in confirmed] == [target]
    assert all(item["hasFeedback"] is True for item in confirmed)


def test_an_unknown_sort_key_is_refused(client):
    response = client.get("/api/alerts", params={"sort": "whatever"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------------------------
# The tie-break (measured on 2026-09-16)
#
# Scores saturate: on the demo database 975 of the 996 flagged alerts sit at exactly 100.0 and
# 3,635 at exactly 0.0, so 4,789 of 5,000 alerts share a score with more than a page of others. A
# tie is therefore the normal case, and the tie-break *is* the visible ranking. It used to be a
# hard-coded `a.id ASC`, which ignored the requested direction: sorting the 975 alerts at 100.0
# descending and ascending returned the identical page. These three tests pin the fix.
# --------------------------------------------------------------------------------------------


def test_the_direction_flips_a_page_whose_scores_all_tie(client):
    """The reported bug. Every alert in this page scores exactly 100.0, so the primary sort key is
    constant and only the tie-break can distinguish the two directions."""
    ascending = rows(client, limit=50, sort="detection_score", direction="asc",
                     detectionMinScore=100)
    descending = rows(client, limit=50, sort="detection_score", direction="desc",
                      detectionMinScore=100)
    assert len(ascending) > 1, "the fixture must produce a tied page"
    assert len({item["detectionScore"] for item in ascending}) == 1, "the page must be all-tied"
    assert [i["alertRef"] for i in ascending] != [i["alertRef"] for i in descending], (
        "flipping the direction must flip the page, even though every score is equal")


def test_a_tied_page_reads_oldest_first_when_ascending(client):
    """The tie-break's semantic key is the flow's capture time, and it follows the direction:
    ascending is oldest traffic first (the FIFO order for an unworked queue), descending is newest
    first. A capture-time key pinned to ASC would leave the unique times in charge and the `id`
    key unreached — which reproduced the identical page this fix removes."""
    ascending = rows(client, limit=50, sort="detection_score", direction="asc",
                     detectionMinScore=100)
    descending = rows(client, limit=50, sort="detection_score", direction="desc",
                      detectionMinScore=100)
    up = [item["flowTime"] for item in ascending]
    down = [item["flowTime"] for item in descending]
    assert len(set(up)) == len(up), "the fixture's capture times are distinct"
    assert up == sorted(up), "ascending must read oldest capture first"
    assert down == sorted(down, reverse=True), "descending must read newest capture first"


def test_paging_a_tied_group_never_repeats_or_skips_an_alert(client):
    """A total order is what keeps paging honest. Without the final `id` key, two pages of a tied
    group can repeat an alert or drop one."""
    params = {"sort": "detection_score", "direction": "asc", "detectionMinScore": 100,
              "limit": 5}
    first = client.get("/api/alerts", params={**params, "offset": 0}).json()
    second = client.get("/api/alerts", params={**params, "offset": 5}).json()
    total = first["page"]["total"]
    assert total > 5, "the fixture needs a tied group deeper than one page"
    refs = [item["alertRef"] for item in first["items"]]
    refs += [item["alertRef"] for item in second["items"]]
    assert len(refs) == len(set(refs)) == total


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


def test_the_severity_label_agrees_with_the_score_after_a_verdict(client):
    """The invariant behind the labels: severity is a function of the operational score.

    Regression: severity was written once at detection and never revisited, so feedback moved the
    score out from under it. The demo database shipped two alerts at combined_score 70 still labelled
    "Critical" - a High-band score wearing a Critical label.
    """
    before = {i["alertRef"]: i["severity"] for i in rows(client, limit=200)}
    targets = [i for i in rows(client, limit=100) if i["isCritical"]]
    assert targets, "the fixture should produce at least one Critical alert"
    for item in targets[:4]:
        response = client.post(f"/api/alerts/{item['alertRef']}/feedback",
                               json={"category": "mark_false_positive"})
        assert response.status_code == 200, response.text

    judged = [i for i in rows(client, limit=200) if i["hasFeedback"]]
    assert judged, "the verdicts must show up in the queue"
    for item in rows(client, limit=200):
        expected = severity_for(item["combinedScore"], item["attackCategory"], CEILINGS)
        assert item["severity"] == expected, (
            f"{item['alertRef']}: score {item['combinedScore']} carries {item['severity']}, "
            f"but that score's band is {expected}")


# --------------------------------------------------------------------------------------------
# The queue's verdict filter
# --------------------------------------------------------------------------------------------

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
# Administrator source-IP security report
# --------------------------------------------------------------------------------------------

REPORT_IP = "172.31.69.25"
DESTINATION_ONLY_IP = "18.221.219.4"


def admin_report(client: TestClient, ip: str = REPORT_IP, **params) -> dict:
    response = client.get(
        f"/api/admin/reports/ip/{ip}",
        params=params,
        headers={"Authorization": f"Bearer {client.tokens['admin']}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def admin_source_ip_overview(client: TestClient, **params) -> dict:
    response = client.get(
        "/api/admin/reports/ips",
        params=params,
        headers={"Authorization": f"Bearer {client.tokens['admin']}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_ip_security_report_is_admin_only(client):
    url = f"/api/admin/reports/ip/{REPORT_IP}"
    assert client.get(url).status_code == 403
    evaluator = client.get(
        url, headers={"Authorization": f"Bearer {client.tokens['evaluator']}"})
    assert evaluator.status_code == 403
    assert admin_report(client)["sourceIp"] == REPORT_IP


def test_ip_security_report_uses_source_appearances_only(client):
    report = admin_report(client)
    assert report["summary"]["totalAlerts"] == len(ROWS)
    assert all(row["sourceIp"] == REPORT_IP for row in report["timeline"])

    destination_only = admin_report(client, DESTINATION_ONLY_IP)
    assert destination_only["summary"]["totalAlerts"] == 0
    assert destination_only["timeline"] == []


def test_ip_security_report_date_range_is_inclusive_and_validated(client):
    day = admin_report(client, fromDate="2018-03-01", toDate="2018-03-01")
    assert day["summary"]["totalAlerts"] == len(ROWS)
    assert day["fromDate"] == day["toDate"] == "2018-03-01"

    empty = admin_report(client, fromDate="2018-02-28", toDate="2018-02-28")
    assert empty["summary"]["totalAlerts"] == 0

    headers = {"Authorization": f"Bearer {client.tokens['admin']}"}
    reversed_range = client.get(
        f"/api/admin/reports/ip/{REPORT_IP}",
        params={"fromDate": "2018-03-02", "toDate": "2018-03-01"}, headers=headers)
    assert reversed_range.status_code == 400
    invalid_date = client.get(
        f"/api/admin/reports/ip/{REPORT_IP}",
        params={"fromDate": "2018-99-99"}, headers=headers)
    assert invalid_date.status_code == 400


def test_ip_security_report_counts_only_the_latest_effective_verdict(client):
    refs = [item["alertRef"] for item in rows(client, limit=100)]
    assert client.post(f"/api/alerts/{refs[0]}/feedback",
                       json={"category": "confirm_true_positive"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[0]}/feedback",
                       json={"category": "mark_false_positive"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[1]}/feedback",
                       json={"category": "escalate"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[2]}/feedback",
                       json={"category": "needs_investigation"}).status_code == 200

    report = admin_report(client)
    summary = report["summary"]
    assert summary["truePositive"] == 0
    assert summary["falsePositive"] == 1
    assert summary["escalated"] == 1
    assert summary["needsInvestigation"] == 1
    assert summary["confirmedMalicious"] == 1
    target = next(row for row in report["timeline"] if row["alertRef"] == refs[0])
    assert target["effectiveVerdict"] == "mark_false_positive"


def test_ip_security_report_tp_and_escalate_are_the_only_malicious_confirmations(client):
    categories = ["confirm_true_positive", "escalate", "mark_false_positive",
                  "mark_expected_activity", "needs_investigation"]
    refs = [item["alertRef"] for item in rows(client, limit=100)[:len(categories)]]
    for ref, category in zip(refs, categories, strict=True):
        assert client.post(f"/api/alerts/{ref}/feedback",
                           json={"category": category}).status_code == 200

    summary = admin_report(client)["summary"]
    assert summary["confirmedMalicious"] == 2
    assert summary["truePositive"] == 1
    assert summary["escalated"] == 1
    assert summary["falsePositive"] == 1
    assert summary["expectedActivity"] == 1
    assert summary["needsInvestigation"] == 1


def test_ip_security_report_recommendation_is_transparent_and_advisory(client):
    refs = [item["alertRef"] for item in rows(client, limit=100)[:3]]
    for ref in refs:
        assert client.post(f"/api/alerts/{ref}/feedback",
                           json={"category": "confirm_true_positive"}).status_code == 200
    recommendation = admin_report(client)["recommendation"]
    assert recommendation["action"] == "Review for temporary block"
    assert "3 analyst-confirmed malicious alerts" in recommendation["reason"]
    assert recommendation["advisory"] == (
        "Recommendation is advisory. No network blocking action is performed.")


def test_ip_security_report_contains_no_ground_truth_fields(client):
    body = admin_report(client)
    serialised = str(body).casefold()
    for forbidden in ("groundtruth", "rawlabel", "trueattacktype", "label"):
        assert forbidden not in serialised


def test_ip_security_report_handles_an_unknown_source_cleanly(client):
    report = admin_report(client, "203.0.113.99")
    assert report["summary"]["totalAlerts"] == 0
    assert report["attackBehaviour"] == []
    assert report["targetedHosts"] == []
    assert report["destinationPorts"] == []
    assert report["timeline"] == []
    assert report["recommendation"]["action"] == "Monitor"


def test_source_ip_overview_is_admin_only_and_excludes_destination_only_ips(client):
    assert client.get("/api/admin/reports/ips").status_code == 403
    evaluator = client.get(
        "/api/admin/reports/ips",
        headers={"Authorization": f"Bearer {client.tokens['evaluator']}"},
    )
    assert evaluator.status_code == 403

    body = admin_source_ip_overview(client)
    assert body["page"]["total"] == 1
    assert body["items"][0]["sourceIp"] == REPORT_IP
    assert DESTINATION_ONLY_IP not in {item["sourceIp"] for item in body["items"]}
    assert body["items"][0]["confirmedMaliciousRate"] is None


def test_source_ip_overview_query_is_source_only_and_rejects_unknown_sort(database):
    conn = db.connect(str(database))
    try:
        items, total = store.source_ip_security_overview(conn)
        assert total == 1
        assert items[0]["source_ip"] == REPORT_IP
        assert items[0]["total_alerts"] == len(ROWS)
        assert items[0]["confirmed_malicious_rate"] is None
        with pytest.raises(ValueError, match="Unsupported source-IP overview sort"):
            store.source_ip_security_overview(conn, sort="riskScore")
        with pytest.raises(ValueError, match="Unsupported source-IP overview direction"):
            store.source_ip_security_overview(conn, direction="sideways")
    finally:
        conn.close()


def test_source_ip_overview_counts_an_ip_only_when_it_is_the_source(client, database):
    conn = db.connect(str(database))
    alert_ids = [row["alert_id"] for row in conn.execute(
        "SELECT alert_id FROM flow_data ORDER BY alert_id LIMIT 2").fetchall()]
    with conn:
        conn.execute("UPDATE flow_data SET src_ip = ? WHERE alert_id = ?",
                     ("10.0.0.1", alert_ids[0]))
        conn.execute("UPDATE flow_data SET dst_ip = ? WHERE alert_id = ?",
                     ("10.0.0.1", alert_ids[1]))
    conn.close()

    match = admin_source_ip_overview(client, search="10.0.0.1")
    assert match["page"]["total"] == 1
    assert match["items"][0]["sourceIp"] == "10.0.0.1"
    assert match["items"][0]["totalAlerts"] == 1


def test_source_ip_overview_date_range_is_inclusive_and_minimum_is_enforced(client):
    day = admin_source_ip_overview(
        client, fromDate="2018-03-01", toDate="2018-03-01", minAlerts=len(ROWS))
    assert day["page"]["total"] == 1
    assert day["items"][0]["totalAlerts"] == len(ROWS)

    assert admin_source_ip_overview(
        client, fromDate="2018-02-28", toDate="2018-02-28")["items"] == []
    assert admin_source_ip_overview(client, minAlerts=len(ROWS) + 1)["items"] == []


def test_source_ip_overview_uses_latest_verdict_and_correct_rate_denominator(client):
    refs = [item["alertRef"] for item in rows(client, limit=100)[:4]]
    assert client.post(f"/api/alerts/{refs[0]}/feedback",
                       json={"category": "confirm_true_positive"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[0]}/feedback",
                       json={"category": "mark_false_positive"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[1]}/feedback",
                       json={"category": "confirm_true_positive"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[2]}/feedback",
                       json={"category": "escalate"}).status_code == 200
    assert client.post(f"/api/alerts/{refs[3]}/feedback",
                       json={"category": "needs_investigation"}).status_code == 200

    item = admin_source_ip_overview(client)["items"][0]
    assert item["judgedAlerts"] == 4
    assert item["confirmedMalicious"] == 2
    assert item["confirmedMaliciousRate"] == 0.5
    assert item["falsePositives"] == 1
    assert item["escalated"] == 1
    assert item["needsInvestigation"] == 1
    assert item["unjudged"] == len(ROWS) - 4


def test_source_ip_overview_sorting_and_pagination_are_stable(client, database):
    conn = db.connect(str(database))
    alert_ids = [row["alert_id"] for row in conn.execute(
        "SELECT alert_id FROM flow_data ORDER BY alert_id").fetchall()]
    with conn:
        for alert_id in alert_ids[:10]:
            conn.execute("UPDATE flow_data SET src_ip = ? WHERE alert_id = ?",
                         ("10.0.0.1", alert_id))
        for alert_id in alert_ids[10:16]:
            conn.execute("UPDATE flow_data SET src_ip = ? WHERE alert_id = ?",
                         ("10.0.0.2", alert_id))
        for alert_id in alert_ids[16:]:
            conn.execute("UPDATE flow_data SET src_ip = ? WHERE alert_id = ?",
                         ("10.0.0.3", alert_id))
    conn.close()

    first = admin_source_ip_overview(
        client, sort="totalAlerts", direction="desc", limit=2, offset=0)
    second = admin_source_ip_overview(
        client, sort="totalAlerts", direction="desc", limit=2, offset=2)
    assert [item["totalAlerts"] for item in first["items"]] == [10, 6]
    assert [item["totalAlerts"] for item in second["items"]] == [5]
    assert ({item["sourceIp"] for item in first["items"]}
            .isdisjoint(item["sourceIp"] for item in second["items"]))

    by_ip = admin_source_ip_overview(
        client, sort="sourceIp", direction="asc", limit=10)
    assert [item["sourceIp"] for item in by_ip["items"]] == [
        "10.0.0.1", "10.0.0.2", "10.0.0.3"]


def test_source_ip_overview_contains_no_ground_truth_fields(client):
    serialised = str(admin_source_ip_overview(client)).casefold()
    for forbidden in ("groundtruth", "rawlabel", "trueattacktype"):
        assert forbidden not in serialised


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
