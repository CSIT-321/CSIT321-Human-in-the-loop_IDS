"""Official frozen evidence is joined strictly and served read-only to privileged roles."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api import final_v3_records as evidence
from apps.api.main import create_app
from packages.contracts import db


def test_projection_matches_official_frozen_population():
    projection = evidence.load_projection()
    summary = projection.summary
    assert (summary.total, summary.learning, summary.holdout, summary.primary,
            summary.unknown, summary.drift) == (200, 40, 160, 140, 10, 10)
    assert (summary.primaryBaselineImmediateReview, summary.primaryAdaptiveImmediateReview,
            summary.primaryReviewReduction, summary.primarySafeDeferrals,
            summary.primaryUnsafeDeferrals) == (140, 103, 37, 37, 0)
    assert summary.primaryReviewReductionRate == pytest.approx(37 / 140)
    assert (summary.allHoldoutInitialDeferrals, summary.allHoldoutUnsafeDeferrals,
            summary.postContradictionUnsafeDeferrals, summary.postContradictionPopulation,
            summary.unknownFormalTier2Cases) == (39, 2, 0, 8, 10)
    assert len(projection.records) == 200
    assert len({row.alertRef for row in projection.records}) == 200
    assert len(projection.memory) == 20
    assert [row.index for row in projection.records if row.deferralClassification == "unsafe"] == [191, 196]
    assert all(row.baselineDisposition is None and row.adaptiveDisposition is None
               for row in projection.records[:40])
    assert all(row.baselineDisposition is not None and row.adaptiveDisposition is not None
               for row in projection.records[40:])


@pytest.mark.parametrize("mutation", ["duplicate_index", "duplicate_ref", "missing_result"])
def test_strict_join_rejects_mismatched_frozen_identity(monkeypatch, mutation):
    original = evidence._read

    def changed(path, *, lines=False):
        value = original(path, lines=lines)
        if path.name == "workload-structure.json" and mutation == "duplicate_index":
            value = copy.deepcopy(value)
            value[1]["index"] = value[0]["index"]
        if path.name == "workload-structure.json" and mutation == "duplicate_ref":
            value = copy.deepcopy(value)
            value[1]["alertRef"] = value[0]["alertRef"]
        if path.name == "records.json" and mutation == "missing_result":
            value = value[:-1]
        return value

    monkeypatch.setattr(evidence, "_read", changed)
    with pytest.raises(evidence.ArtifactMismatch):
        evidence.load_projection()


def test_malformed_artifact_is_controlled_failure(tmp_path):
    malformed = tmp_path / "records.json"
    malformed.write_text("{ not JSON", encoding="utf-8")
    with pytest.raises(evidence.ArtifactUnavailable):
        evidence._read(malformed)


def test_evaluation_api_roles_filters_and_no_database_writes(tmp_path):
    operational = tmp_path / "operational.db"
    with db.connect(operational) as conn:
        db.create_schema(conn)
    client = TestClient(create_app(operational))
    headers = {}
    for role, username, password in (("admin", "admin", "admin-demo"),
                                      ("evaluator", "evaluator", "evaluator-demo"),
                                      ("analyst", "g.ang", "analyst-demo")):
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200
        headers[role] = {"Authorization": f"Bearer {login.json()['token']}"}
    original_hash = hashlib.sha256(operational.read_bytes()).hexdigest()
    for role in ("admin", "evaluator"):
        summary = client.get("/api/evaluation/final-v3-1", headers=headers[role])
        assert summary.status_code == 200, summary.text
        assert summary.json()["total"] == 200
        records = client.get("/api/evaluation/final-v3-1/records?phase=holdout&deferral=unsafe",
                             headers=headers[role])
        assert records.status_code == 200, records.text
        assert [item["index"] for item in records.json()["items"]] == [191, 196]
        assert records.json()["total"] == 2
        detail = client.get("/api/evaluation/final-v3-1/records/191", headers=headers[role])
        assert detail.status_code == 200
        assert detail.json()["deferralClassification"] == "unsafe"
        impact = client.get("/api/evaluation/final-v3-1/memory-impact", headers=headers[role])
        assert impact.status_code == 200
        assert len(impact.json()["items"]) == 20
    for route in ("/api/evaluation/final-v3-1", "/api/evaluation/final-v3-1/records",
                  "/api/evaluation/final-v3-1/records/191", "/api/evaluation/final-v3-1/memory-impact"):
        assert client.get(route, headers=headers["analyst"]).status_code == 403
    assert hashlib.sha256(operational.read_bytes()).hexdigest() == original_hash
