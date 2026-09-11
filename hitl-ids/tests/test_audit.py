"""S8 audit writer tests — the plan's verify step for the typed append-only audit trail.

    python -m pytest tests/test_audit.py

The writer is exercised against a real SQLite file (``tmp_path``), because the guarantees that
matter here — the append-only triggers, the fixed-width timestamp encoding and the foreign keys —
live in the database, not in Python.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from packages.contracts import db
from packages.contracts import models as m
from packages.detection.audit.writer import CSV_COLUMNS, AuditWriter

T0 = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
MODEL_VERSION = "xgb-8class-20260911"
RULE_SET_VERSION = "s4b-1"
HALF_SECOND = timedelta(milliseconds=500)


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path):
    connection = db.connect(tmp_path / "audit.db")
    db.create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def writer(conn) -> AuditWriter:
    return AuditWriter(conn)


def make_alert(dataset_id: int, run_id: int) -> m.Alert:
    """The cheapest valid alert: no detector flagged this flow."""
    return m.Alert(
        dataset_id=dataset_id, run_id=run_id, detection_score=50, combined_score=50,
        severity="Low", confidence=0.5, evidence_class="none", evidence_priority=0,
        explanation="no detector flagged this flow", created_at=T0, updated_at=T0)


@pytest.fixture
def graph(conn) -> dict[str, m.Contract]:
    """The foreign-key parents audit entries reference, inserted in foreign-key order.

    Mirrors ``tests/test_contracts.py``'s ``graph`` fixture: audit rows carry enforced references
    to ``users``, ``alerts`` and ``feedback_events``, so those parents must exist first.
    """
    rows: dict[str, m.Contract] = {}

    def put(key: str, model: m.Contract) -> int:
        new_id = db.insert(conn, model)
        rows[key] = model.model_copy(update={"id": new_id})
        return new_id

    analyst = put("analyst", m.User(
        username="analyst1", password_hash="$2b$12$synthetic", display_name="Analyst One",
        email="analyst1@example.test", role="security_analyst", created_at=T0))
    put("admin", m.User(
        username="admin1", password_hash="$2b$12$synthetic", display_name="Admin One",
        email="admin1@example.test", role="system_admin", created_at=T0))
    dataset = put("dataset", m.Dataset(
        name="CSE-CIC-IDS2018 corrected - demo sample", version="demo-20260911",
        source_file="data/processed/demo_sample.csv", preparation_meta={"seed": 20260911},
        total_records=5000, class_distribution={"Benign": 4000, "DoS": 200},
        created_by=analyst, created_at=T0))
    put("model", m.MlModel(
        version=MODEL_VERSION, model_type="XGBoost", model_file="models/xgboost_ids_model.json",
        status="active", created_at=T0))
    run = put("run", m.DetectionRun(
        dataset_id=dataset, model_version=MODEL_VERSION, rule_set_version=RULE_SET_VERSION,
        fusion_weights={"scheme": "evidence_class"},
        guardrail_config={key: value for key, (value, _) in m.GUARDRAIL_DEFAULTS.items()},
        status="completed", alert_count=1, started_at=T0, completed_at=T0, seed=20260911))
    put("rule", m.SignatureRule(
        rule_id="SIG-SSH-BRUTE-FORCE", name="SSH Brute Force Flow Pattern", severity="Medium",
        conditions={"Protocol": "TCP", "Dst Port": 22, "Flow Packets/s": {"min": 10.67}},
        version=RULE_SET_VERSION, attack_category="Brute Force",
        rationale="Repeated short TCP flows against port 22.", created_at=T0))
    alert = put("alert", make_alert(dataset, run))
    put("feedback", m.FeedbackEvent(
        alert_id=alert, user_id=analyst, category="mark_false_positive", original_score=50,
        requested_delta=-10, actual_delta=-10, guardrail_action="applied", created_at=T0))
    conn.commit()
    return rows


def audit_entry(event_type: str, *, moment: datetime | None = None,
                details: dict[str, Any] | None = None, **links: Any) -> m.AuditEntry:
    """An entry at a chosen timestamp. The typed constructors take no timestamp, so the query
    tests seed through ``record`` with one."""
    return m.AuditEntry(
        event_type=event_type, created_at=T0 if moment is None else moment,
        details=details or {}, **links)


@pytest.fixture
def seeded(writer: AuditWriter, graph: dict[str, m.Contract]) -> list[m.AuditEntry]:
    """Seven entries with known actors, event types and timestamps.

    Ids ascend with insertion order, and ``seeded[2]``/``seeded[3]`` share a ``created_at``: that
    is what pins ``query``'s id tiebreak. The whole-second entries at T0 and T0+1s sit next to a
    fractional one at T0+0.5s, which is what pins the inclusive/exclusive edges.
    """
    analyst, admin = graph["analyst"].id, graph["admin"].id
    alert, feedback = graph["alert"].id, graph["feedback"].id
    return [
        writer.record(audit_entry("LOGIN", actor_id=analyst, moment=T0,
                                  details={"rationale": "shift start"})),
        writer.record(audit_entry("LOGOUT", actor_id=analyst, moment=T0 + HALF_SECOND)),
        writer.record(audit_entry("LOGIN", actor_id=admin, moment=T0 + timedelta(seconds=1))),
        writer.record(audit_entry("LOGIN", actor_id=analyst, moment=T0 + timedelta(seconds=1))),
        writer.record(audit_entry("DETECTION_RUN", moment=T0 + timedelta(seconds=2),
                                  details={"run_id": graph["run"].id})),
        writer.record(audit_entry("FEEDBACK", actor_id=analyst, alert_id=alert,
                                  feedback_id=feedback, moment=T0 + timedelta(seconds=3),
                                  details={"category": "mark_false_positive"})),
        writer.record(audit_entry("GUARDRAIL_INTERVENTION", actor_id=analyst, alert_id=alert,
                                  feedback_id=feedback, moment=T0 + timedelta(seconds=4),
                                  details={"outcome": capped_outcome().model_dump(mode="json")})),
    ]


def ids(entries) -> list[int]:
    return [entry.id for entry in entries]


# --------------------------------------------------------------------------------------------
# Guardrail outcomes
# --------------------------------------------------------------------------------------------


def capped_outcome() -> m.GuardrailOutcome:
    return m.GuardrailOutcome(
        score_before=92, requested_delta=-25, actual_delta=-22, score_after=70, action="capped",
        interventions=[m.GuardrailIntervention(
            code="critical_alert_floor", configured_value=70, original_value=67, applied_value=70)],
        requires_review=True)


def rejected_outcome() -> m.GuardrailOutcome:
    return m.GuardrailOutcome(
        score_before=70, requested_delta=-25, actual_delta=0, score_after=70, action="rejected",
        interventions=[m.GuardrailIntervention(
            code="critical_alert_floor", configured_value=70, original_value=45, applied_value=None)])


def applied_outcome() -> m.GuardrailOutcome:
    return m.GuardrailOutcome(
        score_before=50, requested_delta=10, actual_delta=10, score_after=60, action="applied")


# --------------------------------------------------------------------------------------------
# Every typed constructor: build, store, read back
# --------------------------------------------------------------------------------------------

CONSTRUCTOR_CASES = ["login", "logout", "detection_run", "feedback", "guardrail_capped",
                     "guardrail_rejected", "guardrail_applied", "rule_create", "rule_update",
                     "config_change"]


def build(name: str, writer: AuditWriter, graph: dict[str, m.Contract]
          ) -> tuple[m.AuditEntry, str, dict[str, Any], str | None]:
    """Call one typed constructor: (entry, event type, details it must carry, rationale)."""
    analyst = graph["analyst"].id
    alert, feedback = graph["alert"].id, graph["feedback"].id
    run, rule = graph["run"], graph["rule"]
    if name == "login":
        return writer.login(analyst, rationale="shift start"), "LOGIN", {}, "shift start"
    if name == "logout":
        return writer.logout(analyst, rationale="shift end"), "LOGOUT", {}, "shift end"
    if name == "detection_run":
        return (
            writer.detection_run(run, actor_id=analyst, rationale="scheduled demo run"),
            "DETECTION_RUN",
            {"run_id": run.id, "dataset_id": run.dataset_id, "model_version": run.model_version,
             "rule_set_version": run.rule_set_version, "seed": run.seed, "status": run.status,
             "alert_count": run.alert_count},
            "scheduled demo run")
    if name == "feedback":
        return (
            writer.feedback(analyst, alert, feedback, category="mark_false_positive",
                            rationale="the analyst checked the flow"),
            "FEEDBACK", {"category": "mark_false_positive"}, "the analyst checked the flow")
    if name == "guardrail_capped":
        return (writer.guardrail(capped_outcome(), alert_id=alert, feedback_id=feedback,
                                 actor_id=analyst),
                "GUARDRAIL_INTERVENTION",
                {"outcome": capped_outcome().model_dump(mode="json")}, None)
    if name == "guardrail_rejected":
        return (writer.guardrail(rejected_outcome(), alert_id=alert, feedback_id=feedback),
                "GUARDRAIL_REJECTION",
                {"outcome": rejected_outcome().model_dump(mode="json")}, None)
    if name == "guardrail_applied":
        return (writer.guardrail(applied_outcome(), alert_id=alert, feedback_id=feedback),
                "GUARDRAIL_INTERVENTION",
                {"outcome": applied_outcome().model_dump(mode="json")}, None)
    if name == "rule_create":
        return (writer.rule_change(rule, actor_id=analyst, created=True,
                                   rationale="new rule for the demo"),
                "RULE_CREATE",
                {"rule_id": rule.rule_id, "version": rule.version, "enabled": rule.enabled},
                "new rule for the demo")
    if name == "rule_update":
        return (writer.rule_change(rule, actor_id=analyst, created=False, rationale="retuned"),
                "RULE_UPDATE",
                {"rule_id": rule.rule_id, "version": rule.version, "enabled": rule.enabled},
                "retuned")
    if name == "config_change":
        return (
            writer.config_change(analyst, key="critical_alert_floor", old_value=70, new_value=65,
                                 rationale="floor lowered for the demo"),
            "CONFIG_CHANGE",
            {"key": "critical_alert_floor", "old_value": 70, "new_value": 65},
            "floor lowered for the demo")
    raise AssertionError(f"unknown constructor case {name!r}")


@pytest.mark.parametrize("name", CONSTRUCTOR_CASES)
def test_typed_constructor_round_trips(writer, conn, graph, name):
    entry, event_type, details, rationale = build(name, writer, graph)
    assert entry.event_type == event_type
    assert entry.id is not None
    # record() returned the stored row: reading the row back independently gives the same object.
    assert db.get(conn, m.AuditEntry, entry.id) == entry
    assert entry.details.get("rationale") == rationale
    for key, value in details.items():
        assert entry.details[key] == value, key


@pytest.mark.parametrize("name", CONSTRUCTOR_CASES)
def test_typed_constructor_reaches_the_table(writer, conn, graph, name):
    entry, event_type, details, _ = build(name, writer, graph)
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry.id,)).fetchone()
    assert row["event_type"] == event_type
    assert row["details"] == json.dumps(entry.details, sort_keys=True)
    assert row["created_at"] == db.format_timestamp(entry.created_at)


def test_guardrail_event_type_follows_the_outcome_action(writer, graph):
    alert, feedback = graph["alert"].id, graph["feedback"].id
    capped = writer.guardrail(capped_outcome(), alert_id=alert, feedback_id=feedback)
    rejected = writer.guardrail(rejected_outcome(), alert_id=alert, feedback_id=feedback)
    applied = writer.guardrail(applied_outcome(), alert_id=alert, feedback_id=feedback)
    assert capped.event_type == "GUARDRAIL_INTERVENTION"
    assert applied.event_type == "GUARDRAIL_INTERVENTION"
    assert rejected.event_type == "GUARDRAIL_REJECTION"
    # The stored decision validates back to the outcome the engine handed over.
    assert m.GuardrailOutcome.model_validate(capped.details["outcome"]) == capped_outcome()
    assert m.GuardrailOutcome.model_validate(rejected.details["outcome"]) == rejected_outcome()
    assert m.GuardrailOutcome.model_validate(applied.details["outcome"]) == applied_outcome()
    assert (capped.alert_id, capped.feedback_id) == (alert, feedback)


def test_guardrail_entry_needs_the_rows_it_names(writer, graph):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        writer.guardrail(capped_outcome(), alert_id=graph["alert"].id, feedback_id=424242)


def test_detection_run_carries_the_replay_provenance(writer, graph):
    run = graph["run"]
    entry = writer.detection_run(run)
    for key in ("run_id", "dataset_id", "model_version", "rule_set_version", "seed", "status",
                "alert_count"):
        assert key in entry.details
    assert entry.details["model_version"] == run.model_version
    assert entry.actor_id is None  # a scheduled run has no actor


# --------------------------------------------------------------------------------------------
# The contract still governs what reaches the table
# --------------------------------------------------------------------------------------------


def test_contract_validation_still_applies(writer, graph):
    with pytest.raises(ValidationError, match="feedback_id"):
        writer.record(m.AuditEntry(event_type="FEEDBACK", actor_id=graph["analyst"].id,
                                   alert_id=graph["alert"].id, details={}))


def test_record_leaves_the_transaction_to_the_caller(writer, conn, graph):
    assert conn.in_transaction is False
    entry = writer.login(graph["analyst"].id)
    assert conn.in_transaction is True  # uncommitted: the caller decides, and can still roll back
    conn.commit()
    assert db.get(conn, m.AuditEntry, entry.id) == entry


# --------------------------------------------------------------------------------------------
# Append-only, enforced by the triggers and by the writer's own shape
# --------------------------------------------------------------------------------------------


def test_raw_sql_update_is_refused(writer, conn, seeded):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE audit_log SET details = '{}' WHERE id = ?", (seeded[0].id,))
    assert db.get(conn, m.AuditEntry, seeded[0].id) == seeded[0]


def test_raw_sql_delete_is_refused(writer, conn, seeded):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM audit_log WHERE id = ?", (seeded[0].id,))
    assert db.get(conn, m.AuditEntry, seeded[0].id) == seeded[0]


def test_writer_offers_no_way_to_mutate_the_trail():
    forbidden = {"update", "delete", "amend", "purge", "truncate", "remove"}
    assert forbidden.isdisjoint(dir(AuditWriter))


# --------------------------------------------------------------------------------------------
# Query filters
# --------------------------------------------------------------------------------------------


def test_query_orders_by_created_at_then_id(writer, seeded):
    found = writer.query()
    assert ids(found) == ids(seeded)
    assert [entry.created_at for entry in found] == sorted(e.created_at for e in found)
    # the tiebreak: two entries share a timestamp and came back in id order
    assert found[2].created_at == found[3].created_at
    assert found[2].id < found[3].id


def test_query_filters_by_actor(writer, seeded, graph):
    assert ids(writer.query(actor_id=graph["analyst"].id)) == [
        seeded[index].id for index in (0, 1, 3, 5, 6)]
    assert ids(writer.query(actor_id=graph["admin"].id)) == [seeded[2].id]


def test_query_filters_by_one_event_type(writer, seeded):
    assert ids(writer.query(event_types=["LOGIN"])) == [seeded[index].id for index in (0, 2, 3)]


def test_query_filters_by_several_event_types(writer, seeded):
    assert ids(writer.query(event_types=["LOGIN", "LOGOUT"])) == [
        seeded[index].id for index in (0, 1, 2, 3)]


def test_query_filters_by_alert(writer, seeded, graph):
    assert ids(writer.query(alert_id=graph["alert"].id)) == [seeded[5].id, seeded[6].id]


def test_empty_event_types_selects_nothing(writer, seeded):
    assert writer.query(event_types=[]) == []


def test_query_since_is_inclusive_at_a_whole_second(writer, seeded):
    # seeded[0] sits exactly on T0 with zero microseconds. A bound encoded any other way —
    # isoformat's "+00:00" sorts below "." — would drop it.
    assert ids(writer.query(since=T0)) == ids(seeded)


def test_query_until_is_exclusive_at_a_whole_second(writer, seeded):
    assert ids(writer.query(until=T0 + timedelta(seconds=1))) == [seeded[0].id, seeded[1].id]


def test_query_bounds_meet_the_fractional_entry(writer, seeded):
    assert ids(writer.query(since=T0 + HALF_SECOND)) == ids(seeded[1:])  # inclusive
    assert ids(writer.query(until=T0 + HALF_SECOND)) == [seeded[0].id]  # exclusive


def test_query_bounds_combine(writer, seeded):
    found = writer.query(since=T0 + timedelta(seconds=1), until=T0 + timedelta(seconds=2))
    assert ids(found) == [seeded[2].id, seeded[3].id]


def test_query_combines_filters_with_and(writer, seeded, graph):
    found = writer.query(actor_id=graph["analyst"].id, event_types=["LOGIN", "LOGOUT"],
                         since=T0 + HALF_SECOND, until=T0 + timedelta(seconds=1))
    assert ids(found) == [seeded[1].id]


def test_query_limit_takes_the_oldest(writer, seeded):
    assert ids(writer.query(limit=3)) == [seeded[index].id for index in (0, 1, 2)]
    assert writer.query(limit=0) == []


def test_query_binds_event_types_instead_of_formatting_them(writer, seeded):
    # An IN list built by string interpolation would return every row here.
    assert writer.query(event_types=["LOGIN' OR '1'='1"]) == []
    assert ids(writer.query(event_types=["LOGIN", "LOGIN' OR '1'='1"])) == [
        seeded[index].id for index in (0, 2, 3)]


def test_query_binds_actor_ids(writer, seeded):
    assert writer.query(actor_id="1 OR 1=1") == []


# --------------------------------------------------------------------------------------------
# CSV export
# --------------------------------------------------------------------------------------------


def test_export_csv_writes_a_header_and_every_row(writer, seeded, tmp_path):
    path = tmp_path / "audit.csv"
    assert writer.export_csv(seeded, path) == len(seeded) == 7
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == len(seeded) + 1
    by_id = {int(row[0]): row for row in rows[1:]}
    for entry in seeded:
        row = by_id[entry.id]
        assert row[1] == db.format_timestamp(entry.created_at)
        assert row[2] == entry.event_type
        assert row[6] == json.dumps(entry.details, sort_keys=True, separators=(",", ":"))
        assert json.loads(row[6]) == entry.details


def test_export_csv_of_nothing_writes_only_the_header(writer, tmp_path):
    path = tmp_path / "empty.csv"
    assert writer.export_csv([], path) == 0
    assert path.read_text(encoding="utf-8").strip() == ",".join(CSV_COLUMNS)


def test_export_csv_of_a_filtered_query_matches_it(writer, seeded, tmp_path):
    found = writer.query(event_types=["LOGIN"])
    path = tmp_path / "logins.csv"
    assert writer.export_csv(found, path) == 3
    with open(path, encoding="utf-8", newline="") as handle:
        assert [row[2] for row in list(csv.reader(handle))[1:]] == ["LOGIN"] * 3
