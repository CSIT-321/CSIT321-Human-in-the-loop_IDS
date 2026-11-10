"""The second analyst account receives Tier 2 cases only (2026-11-11).

The scope lives on the account (users.queue_scope), not in the token and not in the
client: the list query and the summary both read it, and a direct read of a Tier 1
alert is refused.
"""
import pytest

from tests.test_operational_workspaces import _client


@pytest.fixture()
def prepared(tmp_path):
    client, operational, tokens = _client(tmp_path)
    response = client.post("/api/admin/workspaces/v3-1-replay/prepare", headers=tokens["admin"],
                           json={"reason": "Tier 2 scope test"})
    assert response.status_code == 200, response.text
    login = client.post("/api/auth/login", json={"username": "t2.ang", "password": "tier2-demo"})
    assert login.status_code == 200, login.text
    tier2 = {"Authorization": f"Bearer {login.json()['token']}"}
    return client, tokens, tier2


def test_tier2_account_lists_only_tier2_cases(prepared):
    client, tokens, tier2 = prepared
    page = client.get("/api/v2/alerts?limit=200&handlingRoute=tier1_review", headers=tier2).json()
    routes = {item["state"]["handlingRoute"] for item in page["items"]}
    assert routes <= {"tier2_case"}
    assert page["page"]["total"] == client.get("/api/v2/alerts/summary", headers=tier2).json()["totalAlerts"]


def test_tier2_account_summary_counts_the_scope(prepared):
    client, tokens, tier2 = prepared
    summary = client.get("/api/v2/alerts/summary", headers=tier2).json()
    admin = client.get("/api/v2/alerts/summary", headers=tokens["admin"]).json()
    assert summary["totalAlerts"] == summary["tier2Cases"]
    assert summary["tier1Review"] == 0
    assert admin["totalAlerts"] >= summary["totalAlerts"]


def test_tier2_account_cannot_read_a_tier1_alert(prepared):
    client, tokens, tier2 = prepared
    page = client.get("/api/v2/alerts?limit=200", headers=tokens["admin"]).json()
    outside = [item for item in page["items"] if item["state"]["handlingRoute"] != "tier2_case"]
    if not outside:
        pytest.skip("the prepared workload has no non-Tier-2 item")
    ref = outside[0]["operationalAlertRef"]
    assert client.get(f"/api/v2/alerts/{ref}/triage-state", headers=tier2).status_code == 404
    assert client.get(f"/api/v2/alerts/{ref}/triage-state", headers=tokens["admin"]).status_code == 200
