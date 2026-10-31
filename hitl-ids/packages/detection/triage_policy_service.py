"""Explicit local V2 policy application; no legacy writes or network mutation endpoint."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import sqlite3

from packages.contracts import db, models as m
from packages.contracts.operational_v2 import OperationalTriageStateV2, POLICY_BAND_STORAGE
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.triage_policy import (
    TriageContext, TriagePolicy, TriagePolicyResult, evaluate_triage, load_triage_policy,
)


class StaleTriageState(ValueError):
    """Caller must reread state and explicitly decide whether to reapply."""


@dataclass(frozen=True)
class PolicyApplication:
    state: OperationalTriageStateV2
    result: TriagePolicyResult
    audit_id: int
    applied: bool


def _json(model) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), sort_keys=True, allow_nan=False)


def apply_triage_policy(conn: sqlite3.Connection, operational_id: int, *, actor_id: int,
                        expected_state: OperationalTriageStateV2, context: TriageContext | None = None,
                        policy: TriagePolicy | None = None, now: datetime | None = None) -> PolicyApplication:
    """Apply under a write lock, auditing the exact source context/config/result and before/after.

    A trusted local caller supplies the actor; active analyst/admin authorization is checked here.
    Any future HTTP caller must bind actor_id to its authenticated principal. No HTTP mutation
    endpoint is provided. Changed context requires fresh expected state. Exact retry of the last
    application is a no-op only while its entire resulting state is still current.
    """
    if conn.in_transaction:
        raise ValueError("policy application requires a connection outside a transaction")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise ValueError("foreign keys must be enabled")
    policy = TriagePolicy.model_validate((policy or load_triage_policy()).model_dump())
    context = TriageContext.model_validate((context or TriageContext()).model_dump())
    expected_state = OperationalTriageStateV2.model_validate(expected_state.model_dump())
    if expected_state.operational_alert_id != operational_id:
        raise ValueError("expected state belongs to another V2 alert")
    policy_json, context_json = _json(policy), _json(context)
    try:
        conn.execute("BEGIN IMMEDIATE")
        actor = db.get(conn, m.User, actor_id)
        if actor is None or actor.status != "active" or actor.role not in ("security_analyst", "system_admin"):
            raise PermissionError("policy application requires an active analyst or administrator")
        alert = read_projection(conn, operational_id)
        before = read_triage(conn, operational_id)
        result = evaluate_triage(alert, context, policy)
        result_json, before_json = _json(result), _json(before)
        prior_config = conn.execute("SELECT policy_snapshot FROM operational_triage_policy_audit "
                                    "WHERE policy_version=? LIMIT 1", (policy.version,)).fetchone()
        if prior_config is not None and prior_config[0] != policy_json:
            raise ValueError("changed policy configuration requires a new policy version")
        latest = conn.execute("SELECT * FROM operational_triage_policy_audit WHERE operational_alert_id=? "
                              "ORDER BY id DESC LIMIT 1", (operational_id,)).fetchone()
        if latest is not None and all((
            latest["policy_snapshot"] == policy_json, latest["context_snapshot"] == context_json,
            latest["result_snapshot"] == result_json, latest["after_state"] == before_json,
        )):
            conn.commit()
            return PolicyApplication(before, result, latest["id"], False)
        if before != expected_state:
            raise StaleTriageState("V2 triage state changed; reread before applying policy")
        if ((before.handling_route, before.workflow_stage) not in
                (("unassigned", "staged"), ("tier1_review", "triage"))
                or before.decision_source not in ("system_policy", "legacy_projection")):
            raise ValueError("policy cannot overwrite analyst decisions or advanced workflow transitions")
        moment = now or m.utc_now()
        if moment.tzinfo is None:
            raise ValueError("policy application time must be timezone-aware")
        moment = moment.astimezone(UTC)
        if moment <= before.updated_at:
            moment = before.updated_at + timedelta(microseconds=1)
        after = OperationalTriageStateV2(
            operational_alert_id=operational_id, operational_priority=result.final_operational_priority,
            priority_band=result.priority_band, priority_band_scheme="p1_p4",
            handling_route=result.handling_route, workflow_stage=result.workflow_stage,
            review_required=result.review_required, review_reason=" ".join(result.review_reasons),
            tier2_recommended=result.tier2_recommended,
            tier2_recommendation_reasons=result.tier2_recommendation_reasons,
            decision_source=result.decision_source, triage_policy_version=result.policy_version,
            updated_at=moment)
        values = after.model_dump(mode="json", exclude={"operational_alert_id"})
        values["priority_band"] = POLICY_BAND_STORAGE[after.priority_band]
        values["tier2_recommendation_reasons"] = json.dumps(values["tier2_recommendation_reasons"])
        values["updated_at"] = db.format_timestamp(after.updated_at)
        assignments = ", ".join(f"{name}=?" for name in values)
        conn.execute(f"UPDATE operational_triage_state_v2 SET {assignments} WHERE operational_alert_id=?",
                     [*values.values(), operational_id])
        audit = conn.execute(
            "INSERT INTO operational_triage_policy_audit (operational_alert_id, actor_id, policy_version, "
            "policy_snapshot, context_snapshot, result_snapshot, before_state, after_state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (operational_id, actor_id, policy.version, policy_json, context_json, result_json,
             before_json, _json(after), db.format_timestamp(moment)))
        persisted = read_triage(conn, operational_id)
        if persisted != after:
            raise ValueError("triage storage round-trip mismatch")
        conn.commit()
        return PolicyApplication(persisted, result, audit.lastrowid, True)
    except Exception:
        conn.rollback()
        raise
