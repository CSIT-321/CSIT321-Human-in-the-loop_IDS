"""Pure projections and opt-in V2 persistence. Never writes the legacy workflow."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Literal

from packages.contracts import db, models as m
from packages.contracts.canonical import CanonicalAlert
from packages.contracts.operational_v2 import (
    ExternalSourceProvenanceV2, LegacySourceProvenanceV2,
    OperationalAlertV2, OperationalTriageStateV2,
    POLICY_BAND_STORAGE,
)
from packages.detection.pipeline import store


def _projection(canonical: CanonicalAlert, **source) -> OperationalAlertV2:
    fields = canonical.model_dump(exclude={"detector_severity", "confidence", "evidence_class",
                                           "structured_evidence", "provenance", "source_record_reference",
                                           "original_detector_fields"})
    return OperationalAlertV2(
        **fields, **source, operational_alert_ref=canonical.canonical_alert_id,
        native_severity=canonical.detector_severity, detector_confidence=canonical.confidence,
        detector_evidence=canonical)


def project_legacy(alert: m.Alert, canonical: CanonicalAlert) -> OperationalAlertV2:
    """Keep detector confidence separate from the legacy fused confidence; copy neither score to triage."""
    if alert.id is None:
        raise ValueError("legacy projection requires a persisted source alert")
    if canonical.canonical_alert_id != alert.alert_ref:
        raise ValueError("legacy and canonical identities do not match")
    if alert.detector is not None and alert.detector != canonical:
        raise ValueError("projection must use the existing detector snapshot")
    if canonical.structured_evidence.get("detectionScore") != alert.detection_score:
        raise ValueError("canonical detection score must match the legacy source")
    return _projection(
        canonical, source_kind="legacy_flow_alert", legacy_alert_id=alert.id,
        source_provenance=LegacySourceProvenanceV2(
            dataset_id=alert.dataset_id, run_id=alert.run_id, legacy_alert_ref=alert.alert_ref,
            detection_score=alert.detection_score, legacy_fusion_confidence=alert.confidence))


def project_external(inbox: Mapping[str, Any]) -> OperationalAlertV2:
    """Project an immutable accepted inbox row; its policy score remains a proposal only."""
    row = dict(inbox)
    if row["import_status"] != "staged":
        raise ValueError("only staged external evidence can be projected")
    canonical = CanonicalAlert.model_validate_json(row["canonical_snapshot"])
    expected = {
        "canonical_alert_id": str(canonical.canonical_alert_id), "detector_source": canonical.detector_source,
        "raw_reference": canonical.source_record_reference, "occurred_at": canonical.occurred_at,
        "occurred_at_timezone_offset": canonical.occurred_at_timezone_offset,
        "native_severity": canonical.detector_severity, "confidence": canonical.confidence,
        "detection_title": canonical.detection_title, "detection_category": canonical.detection_category,
        "source_ip": canonical.source_ip, "destination_ip": canonical.destination_ip,
        "source_port": canonical.source_port, "destination_port": canonical.destination_port,
        "protocol": canonical.protocol, "sensor_id": canonical.provenance.get("sensorId"),
    }
    if any(row.get(name) != value for name, value in expected.items()):
        raise ValueError("inbox columns disagree with canonical snapshot")
    return _projection(
        canonical, source_kind="external_nids_alert", external_inbox_id=row["id"],
        source_provenance=ExternalSourceProvenanceV2(
            sensor_id=row["sensor_id"], raw_reference=row["raw_reference"],
            admission_policy_version=row["admission_policy_version"],
            admission_decision=row["admission_decision"], admission_reason=row["admission_reason"],
            proposed_operational_priority=row["proposed_operational_priority"],
            proposed_evidence_class=row["proposed_evidence_class"], review_required=row["review_required"],
            learning_eligible=row["learning_eligible"], evaluation_eligible=row["evaluation_eligible"]))


SourceKind = Literal["legacy_flow_alert", "external_nids_alert"]


def preview_source(conn: sqlite3.Connection, source_kind: SourceKind, source_id: int) -> OperationalAlertV2:
    """Read-only projection, including the existing read-only canonical fallback for old alerts."""
    if source_kind == "legacy_flow_alert":
        alert = db.get(conn, m.Alert, source_id)
        if alert is None:
            raise LookupError(f"legacy alert {source_id} does not exist")
        flow = store.flow_for_alert(conn, source_id)
        if flow is None:
            raise LookupError(f"legacy alert {source_id} has no flow")
        return project_legacy(alert, store.detector_for_alert(conn, alert, flow))
    if source_kind == "external_nids_alert":
        row = conn.execute("SELECT * FROM external_alert_inbox WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise LookupError(f"external inbox record {source_id} does not exist")
        return project_external(row)
    raise ValueError("unsupported V2 source kind")


def read_projection(conn: sqlite3.Connection, operational_id: int) -> OperationalAlertV2:
    row = conn.execute("SELECT * FROM operational_alerts_v2 WHERE id=?", (operational_id,)).fetchone()
    if row is None:
        raise LookupError(f"operational V2 alert {operational_id} does not exist")
    values = dict(row)
    for name in ("native_severity", "detector_evidence", "source_provenance"):
        values[name] = json.loads(values[name])
    return OperationalAlertV2.model_validate(values)


def read_triage(conn: sqlite3.Connection, operational_id: int) -> OperationalTriageStateV2:
    row = conn.execute("SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?",
                       (operational_id,)).fetchone()
    if row is None:
        raise LookupError(f"operational V2 alert {operational_id} has no triage state")
    values = dict(row)
    values["tier2_recommendation_reasons"] = json.loads(values["tier2_recommendation_reasons"])
    if values.get("priority_band_scheme") == "p1_p4" and values["priority_band"] is not None:
        labels = {storage: band for band, storage in POLICY_BAND_STORAGE.items()}
        if values["priority_band"] not in labels:
            raise ValueError("invalid P1-P4 storage label")
        values["priority_band"] = labels[values["priority_band"]]
    return OperationalTriageStateV2.model_validate(values)


def materialize_source(conn: sqlite3.Connection, source_kind: SourceKind, source_id: int) -> OperationalAlertV2:
    """Explicit service call only. Atomically persist evidence and dormant triage; no auto-backfill.

    Repeated calls return the immutable existing record, never resetting triage. A conflicting
    projection fails clearly. Source reads and duplicate checks share the transaction lock.
    """
    if conn.in_transaction:
        raise ValueError("V2 materialization requires a connection outside a transaction")
    try:
        conn.execute("BEGIN IMMEDIATE")
        projected = preview_source(conn, source_kind, source_id)
        column = "legacy_alert_id" if source_kind == "legacy_flow_alert" else "external_inbox_id"
        existing = conn.execute(f"SELECT id FROM operational_alerts_v2 WHERE {column}=?", (source_id,)).fetchone()
        if existing is not None:
            saved = read_projection(conn, existing["id"])
            if saved.model_dump(exclude={"id"}) != projected.model_dump(exclude={"id"}):
                raise ValueError("source projection conflicts with immutable V2 evidence")
            read_triage(conn, existing["id"])
            conn.commit()
            return saved
        row = projected.model_dump(mode="json", exclude={"id"})
        for name in ("native_severity", "detector_evidence", "source_provenance"):
            row[name] = json.dumps(row[name], sort_keys=True, allow_nan=False)
        cursor = conn.execute(f"INSERT INTO operational_alerts_v2 ({', '.join(row)}) "
                              f"VALUES ({', '.join('?' for _ in row)})", list(row.values()))
        operational_id = cursor.lastrowid
        triage = OperationalTriageStateV2(
            operational_alert_id=operational_id,
            decision_source="legacy_projection" if source_kind == "legacy_flow_alert" else "system_policy")
        state = triage.model_dump(mode="json")
        state["updated_at"] = db.format_timestamp(triage.updated_at)
        state["tier2_recommendation_reasons"] = json.dumps(state["tier2_recommendation_reasons"])
        conn.execute(f"INSERT INTO operational_triage_state_v2 ({', '.join(state)}) "
                     f"VALUES ({', '.join('?' for _ in state)})", list(state.values()))
        saved = read_projection(conn, operational_id)
        conn.commit()
        return saved
    except Exception:
        conn.rollback()
        raise
