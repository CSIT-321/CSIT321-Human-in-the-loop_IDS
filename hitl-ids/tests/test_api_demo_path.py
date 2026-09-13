"""Contract additions the interface needed (plan steps S12 and S14), driven over HTTP.

* **`sourceRecordId` on every queue row, and search that finds it.** The S16 narrative names its
  alerts `AL-00478` and `AL-03086`; the public `alertRef` is a UUID nobody can read aloud. Without
  this an analyst could not find the demo's centrepiece in a 5,000-row queue.
* **`GET /api/evaluation/runs`.** The three-arm results are committed files, not database rows, so
  the evaluator had no way to discover a run id without a terminal.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from apps.api.deps import get_connection
from test_api import client, database, rows  # noqa: F401  (shared fixtures)


def test_every_queue_row_names_its_source_record(client):  # noqa: F811
    for item in rows(client, limit=20):
        assert item["sourceRecordId"].startswith("AL-")


def test_search_finds_an_alert_by_its_source_record_id(client):  # noqa: F811
    target = rows(client, limit=1)[0]["sourceRecordId"]
    found = rows(client, search=target, limit=50)
    assert found and all(target in item["sourceRecordId"] for item in found)


def test_an_unjudged_alert_reports_its_band_unchanged(client):  # noqa: F811
    """The identity chain once read "corroborated → tier2_candidate" for an alert nobody had
    touched, because "before" was the evidence class rather than detection's band."""
    for item in rows(client, limit=30):
        chain = client.get(f"/api/alerts/{item['alertRef']}/score-adjustment").json()
        assert chain["queueClassBefore"] == chain["queueClassAfter"] == item["queueClass"]


def test_a_verdict_reports_the_band_the_alert_left(client):  # noqa: F811
    """A dismissal that withdraws a Tier 2 marker must show the move, not "unchanged"."""
    top = rows(client, limit=1)[0]
    response = client.post(f"/api/alerts/{top['alertRef']}/feedback",
                           json={"category": "mark_false_positive"})
    assert response.status_code == 200, response.text
    chain = response.json()["feedback"]["adjustment"]
    assert chain["queueClassBefore"] == top["queueClass"]
    assert chain["queueClassAfter"] == response.json()["alert"]["queueClass"]


def test_the_committed_evaluation_runs_are_listed_newest_first(client):  # noqa: F811
    response = client.get("/api/evaluation/runs")
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    assert body["page"]["total"] == len(items) >= 1
    run_ids = [item["runId"] for item in items]
    assert run_ids == sorted(run_ids, reverse=True)
    first = items[0]
    assert len(first["arms"]) == 3
    # A listed run must be one the detail endpoint can open.
    assert client.get(f"/api/evaluation/runs/{first['runId']}").status_code == 200


def test_a_request_connection_may_cross_worker_threads(database):  # noqa: F811
    """FastAPI may open the connection, run the handler and close it on different threads.

    The browser e2e run returned a 500 on the demo's centrepiece alert because SQLite refused a
    connection used off the thread that created it. Deterministic version of that interleaving.
    """
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database_path=database)))
    dependency = get_connection(request)
    connection = next(dependency)
    seen: list[object] = []

    def use() -> None:
        seen.append(connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])

    worker = threading.Thread(target=use)
    worker.start()
    worker.join()
    closer = threading.Thread(target=lambda: next(dependency, None))
    closer.start()
    closer.join()
    assert seen and isinstance(seen[0], int) and seen[0] > 0


def test_concurrent_reads_of_one_alert_all_succeed(client):  # noqa: F811
    """What the alert page does on open: detail, adjustment and history at once, repeatedly."""
    ref = rows(client, limit=1)[0]["alertRef"]
    paths = [f"/api/alerts/{ref}", f"/api/alerts/{ref}/score-adjustment",
             f"/api/alerts/{ref}/feedback-history"] * 8
    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(lambda path: client.get(path).status_code, paths))
    assert codes == [200] * len(paths)


def test_the_guardrail_log_carries_the_sentence_the_analyst_saw():
    """The administrator's log once showed a dash where the explanation belongs: the audit record
    stores the intervention's code and value, and the sentence was only ever built for the analyst.
    Found by the browser e2e run at the S16 narrative's administrator step."""
    from apps.api.mappers import audit_entry
    from packages.contracts import models as m

    stored = {"outcome": {
        "action": "capped", "requested_delta": -30.0, "actual_delta": -29.89,
        "score_before": 99.89, "score_after": 70.0, "requires_review": True,
        "interventions": [{"code": "critical_alert_floor", "configured_value": 70.0,
                           "original_value": 69.89, "applied_value": 70.0}]}}
    entry = m.AuditEntry(event_type="GUARDRAIL_INTERVENTION", actor_id=1, alert_id=1,
                         feedback_id=1, details=stored)

    out = audit_entry(entry, None, alert_ref="8f22e741-c776-4999-b347-17a0c42aca6a")
    intervention = out.details["outcome"]["interventions"][0]
    assert intervention["explanation"] == (
        "This alert is Critical, so its score was held at the floor of 70.")
    # The stored record is not modified: the sentence is added to the response only.
    assert "explanation" not in stored["outcome"]["interventions"][0]


def test_a_guardrail_detail_it_cannot_parse_is_returned_unchanged():
    from apps.api.mappers import audit_entry
    from packages.contracts import models as m

    odd = {"outcome": {"interventions": [{"code": "not_a_real_code"}]}}
    out = audit_entry(m.AuditEntry(event_type="GUARDRAIL_REJECTION", actor_id=1, alert_id=1,
                                   feedback_id=1, details=odd), None)
    assert out.details == odd
