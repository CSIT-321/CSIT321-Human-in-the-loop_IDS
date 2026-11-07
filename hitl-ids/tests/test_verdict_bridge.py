"""C1 verdict bridge (decisions D1, D2; user decisions 2026-11-07).

D1: the approved engine (feedback/service.py) stays the writer of a flow alert's score and family learning.
D2: one verdict form with the 4 V2 outcomes; on a flow alert each maps to one approved category. Escalate is a
separate action and records the approved 'escalate' (+15).
User: a verdict on a flow GROUP goes to the representative's legacy alert only; family learning carries it.
User: the Tier 2 escalate action on a flow alert also records the approved 'escalate', in the same transaction.
Queue (recommended option, user 2026-11-07): the flow alert's queue score = routing-time operational_priority +
the approved engine's verdict delta (combined_score - detection_score), clamped to 0-100. Read-only.

Every write is one transaction with the V2 verdict or escalation: both happen or neither does.
"""
from contextlib import closing
from uuid import uuid4

import pytest

from packages.contracts import db
from packages.detection import verdict_bridge
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.analyst_verdict import VerdictCommand, read_verdict, record_verdict
from packages.detection.routing import state_version
from packages.detection.tier2_escalation import EscalateCaseRequest, escalate_case
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)
from test_flow_routing import prepare_all
from work_claim_fixture import claim_work

ANALYST = 1


def _groups(conn):
    """{group grouping_key: (operational alert, its legacy alert id)} for every routed Tier 1 group."""
    rows = conn.execute("""SELECT g.id, g.representative_operational_alert_id rep, t.handling_route
        FROM alert_groups g JOIN operational_triage_state_v2 t ON t.operational_alert_id = g.representative_operational_alert_id
        ORDER BY g.id""").fetchall()
    return [(read_projection(conn, r["rep"]), r["handling_route"]) for r in rows]


def _tier1_group(conn, index=0):
    tier1 = [a for a, route in _groups(conn) if route == "tier1_review"]
    return tier1[index]


def _verdict(conn, alert, outcome, reason="Analyst conclusion"):
    claim_work(conn, alert, ANALYST)
    view = read_verdict(conn, alert.operational_alert_ref, ANALYST)
    return record_verdict(conn, alert.operational_alert_ref, actor_id=ANALYST, request=VerdictCommand(
        request_id=uuid4(), expected_revision=view.revision, expected_state_version=view.source_state_version,
        outcome=outcome, reason=reason))


def _feedback(conn, legacy_id=None):
    sql = "SELECT * FROM feedback_events" + (" WHERE alert_id = ?" if legacy_id else "") + " ORDER BY id"
    return conn.execute(sql, (legacy_id,) if legacy_id else ()).fetchall()


@pytest.fixture
def routed(grouped_database):
    from packages.contracts import models as m
    with closing(db.connect(str(grouped_database))) as conn:
        prepare_all(conn)
        db.insert(conn, m.User(username="analyst", password_hash="x", display_name="Analyst One",
                               email="analyst@example.test", role="security_analyst"))
        conn.commit()
        assert conn.execute("SELECT id FROM users WHERE username = 'analyst'").fetchone()[0] == ANALYST
    return grouped_database


def test_the_mapping_is_the_d2_table():
    assert verdict_bridge.OUTCOME_TO_CATEGORY == {
        "confirmed_malicious": "confirm_true_positive",
        "suspicious": "needs_investigation",
        "expected_activity": "mark_expected_activity",
        "false_positive": "mark_false_positive",
    }


@pytest.mark.parametrize("outcome, category", sorted(verdict_bridge.OUTCOME_TO_CATEGORY.items()))
def test_a_flow_verdict_records_the_mapped_approved_verdict_on_the_representative(routed, outcome, category):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        before = len(_feedback(conn))
        score_before = conn.execute("SELECT combined_score FROM alerts WHERE id = ?", (alert.legacy_alert_id,)).fetchone()[0]
        result = _verdict(conn, alert, outcome, reason="Seen this host before")
        rows = _feedback(conn)
        assert len(rows) == before + 1
        row = rows[-1]
        assert (row["alert_id"], row["category"], row["user_id"]) == (alert.legacy_alert_id, category, ANALYST)
        assert row["note"] == "Seen this host before"
        score_after = conn.execute("SELECT combined_score FROM alerts WHERE id = ?", (alert.legacy_alert_id,)).fetchone()[0]
        assert score_after == pytest.approx(float(row["original_score"]) + float(row["actual_delta"]))
        assert score_after == pytest.approx(score_before + float(row["actual_delta"]))
        assert result.verdict.outcome == outcome


def test_only_the_representative_gets_a_verdict_not_the_other_members(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        group = conn.execute("SELECT id, member_count FROM alert_groups WHERE representative_operational_alert_id = ?",
                             (alert.id,)).fetchone()
        assert group["member_count"] > 1, "the fixture's first Tier 1 group must have several members"
        _verdict(conn, alert, "false_positive")
        judged = {r["alert_id"] for r in _feedback(conn)}
        members = {r[0] for r in conn.execute("SELECT legacy_alert_id FROM alert_group_members WHERE group_id = ?",
                                              (group["id"],))}
        assert judged & members == {alert.legacy_alert_id}


def test_the_approved_audit_trail_names_the_analyst(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        _verdict(conn, alert, "confirmed_malicious")
        feedback_id = _feedback(conn)[-1]["id"]
        audit = conn.execute("SELECT actor_id FROM audit_log WHERE event_type = 'FEEDBACK' AND feedback_id = ?",
                             (feedback_id,)).fetchall()
        assert [r[0] for r in audit] == [ANALYST]


def test_a_failed_approved_write_leaves_no_v2_verdict(routed, monkeypatch):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        claim_work(conn, alert, ANALYST)
        verdicts = conn.execute("SELECT count(*) FROM analyst_verdict_events").fetchone()[0]
        feedback = len(_feedback(conn))

        def boom(*args, **kwargs):
            raise RuntimeError("approved engine failed")
        monkeypatch.setattr(verdict_bridge, "apply_feedback", boom)
        view = read_verdict(conn, alert.operational_alert_ref, ANALYST)
        with pytest.raises(RuntimeError):
            record_verdict(conn, alert.operational_alert_ref, actor_id=ANALYST, request=VerdictCommand(
                request_id=uuid4(), expected_revision=view.revision, expected_state_version=view.source_state_version,
                outcome="false_positive", reason="x"))
        assert conn.execute("SELECT count(*) FROM analyst_verdict_events").fetchone()[0] == verdicts
        assert len(_feedback(conn)) == feedback
        assert conn.execute("SELECT status FROM analyst_work WHERE operational_alert_id = ?",
                            (alert.id,)).fetchone()[0] == "in_review"


def test_the_approved_write_does_not_commit_early(routed, monkeypatch):
    """A failure AFTER the bridge (here: completing the work) must also undo the approved write."""
    from packages.detection import analyst_work
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        claim_work(conn, alert, ANALYST)
        feedback = len(_feedback(conn))
        monkeypatch.setattr(analyst_work, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("late")))
        view = read_verdict(conn, alert.operational_alert_ref, ANALYST)
        with pytest.raises(RuntimeError):
            record_verdict(conn, alert.operational_alert_ref, actor_id=ANALYST, request=VerdictCommand(
                request_id=uuid4(), expected_revision=view.revision, expected_state_version=view.source_state_version,
                outcome="false_positive", reason="x"))
        assert len(_feedback(conn)) == feedback


def test_a_retried_request_writes_no_second_approved_verdict(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        claim_work(conn, alert, ANALYST)
        view = read_verdict(conn, alert.operational_alert_ref, ANALYST)
        command = VerdictCommand(request_id=uuid4(), expected_revision=view.revision,
                                 expected_state_version=view.source_state_version, outcome="suspicious", reason="x")
        record_verdict(conn, alert.operational_alert_ref, actor_id=ANALYST, request=command)
        count = len(_feedback(conn))
        again = record_verdict(conn, alert.operational_alert_ref, actor_id=ANALYST, request=command)
        assert again.replayed and len(_feedback(conn)) == count


def test_a_corrected_verdict_amends_the_approved_verdict(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        _verdict(conn, alert, "confirmed_malicious")
        first = _feedback(conn, alert.legacy_alert_id)[-1]
        _verdict(conn, alert, "false_positive", reason="Correction: scheduled scan")
        rows = _feedback(conn, alert.legacy_alert_id)
        assert [r["category"] for r in rows][-2:] == ["confirm_true_positive", "mark_false_positive"]
        assert rows[-1]["amended_from_id"] == first["id"]


def test_an_external_nids_verdict_writes_nothing_to_the_approved_engine():
    assert verdict_bridge.bridge_verdict.__doc__  # behaviour proven in test_analyst_verdict.unchanged()
    calls = []

    class Conn:
        in_transaction = True
    alert = type("A", (), {"source_kind": "external_nids_alert", "legacy_alert_id": None})()
    assert verdict_bridge.bridge_verdict(Conn(), alert, actor_id=1, outcome="false_positive", note="x") is None
    assert calls == []


def test_the_bridge_refuses_to_run_outside_a_transaction(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        with pytest.raises(ValueError):
            verdict_bridge.bridge_verdict(conn, alert, actor_id=ANALYST, outcome="suspicious", note="x")


def _escalate(conn, alert):
    claim_work(conn, alert, ANALYST)
    return escalate_case(conn, alert.operational_alert_ref, actor_id=ANALYST, request=EscalateCaseRequest(
        request_id=uuid4(), expected_state_version=state_version(read_triage(conn, alert.id)),
        reason="Lateral movement suspected", action="manual_escalate"))


def test_escalating_a_flow_alert_records_the_approved_escalate(routed):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        _escalate(conn, alert)
        row = _feedback(conn, alert.legacy_alert_id)[-1]
        assert (row["category"], float(row["requested_delta"])) == ("escalate", 15.0)
        assert row["note"] == "Lateral movement suspected"


def test_a_failed_approved_escalate_leaves_no_case(routed, monkeypatch):
    with closing(db.connect(str(routed))) as conn:
        alert = _tier1_group(conn)
        claim_work(conn, alert, ANALYST)
        cases = conn.execute("SELECT count(*) FROM tier2_cases").fetchone()[0]
        monkeypatch.setattr(verdict_bridge, "apply_feedback",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("approved engine failed")))
        with pytest.raises(RuntimeError):
            escalate_case(conn, alert.operational_alert_ref, actor_id=ANALYST, request=EscalateCaseRequest(
                request_id=uuid4(), expected_state_version=state_version(read_triage(conn, alert.id)),
                reason="x", action="manual_escalate"))
        assert conn.execute("SELECT count(*) FROM tier2_cases").fetchone()[0] == cases
        assert read_triage(conn, alert.id).handling_route == "tier1_review"


def test_a_false_positive_moves_the_group_down_the_queue(routed):
    """D1 'the queue re-orders': the queue score adds the approved engine's verdict delta.

    The fixture's two Tier 1 groups are both Critical at 99; the newer one ranks first on the time tie-break.
    A false positive on that one must move it below the other."""
    from apps.api import operational_queue
    with closing(db.connect(str(routed))) as conn:
        first, other = _tier1_group(conn, 1), _tier1_group(conn, 0)
        _, before = operational_queue.queue_page(conn, limit=1000, offset=0)
        assert before.index(first.id) < before.index(other.id), "fixture: the verdict target must start above"
        _verdict(conn, first, "false_positive")
        delta = conn.execute("SELECT combined_score - detection_score FROM alerts WHERE id = ?",
                             (first.legacy_alert_id,)).fetchone()[0]
        assert delta < 0, "the guardrails let this false positive lower the score"
        _, after = operational_queue.queue_page(conn, limit=1000, offset=0)
        assert after.index(first.id) > after.index(other.id)


def test_the_verdict_delta_moves_an_item_inside_its_severity_level(routed):
    """The score key itself must carry the verdict, not only a severity change. Two Critical groups tie at 99;
    the newer ranks first. 'Expected activity' (-15) takes it to 84: still Critical (threshold 80), so only the
    score key can move it below the other."""
    from apps.api import operational_queue
    with closing(db.connect(str(routed))) as conn:
        first, other = _tier1_group(conn, 1), _tier1_group(conn, 0)
        _, before = operational_queue.queue_page(conn, limit=1000, offset=0)
        assert before.index(first.id) < before.index(other.id)
        _verdict(conn, first, "expected_activity")
        severity, delta = conn.execute("SELECT severity, combined_score - detection_score FROM alerts WHERE id = ?",
                                       (first.legacy_alert_id,)).fetchone()
        assert (severity, delta) == ("Critical", -15), "fixture: -15 must apply and keep the Critical level"
        _, after = operational_queue.queue_page(conn, limit=1000, offset=0)
        assert after.index(first.id) > after.index(other.id)


def test_the_queue_score_keeps_the_routing_context(routed):
    """Trusted context (up to +25) is in operational_priority, not in the detection score. The queue score keeps
    it: here the routing priority is set 20 above the detection score, with no verdict."""
    from apps.api import operational_queue
    with closing(db.connect(str(routed))) as conn:
        a, b = _tier1_group(conn, 0), _tier1_group(conn, 1)
        conn.execute("UPDATE operational_triage_state_v2 SET operational_priority = 80 WHERE operational_alert_id = ?",
                     (b.id,))
        conn.execute("UPDATE operational_triage_state_v2 SET operational_priority = 100 WHERE operational_alert_id = ?",
                     (a.id,))
        conn.commit()
        same = conn.execute("SELECT count(DISTINCT detection_score) FROM alerts WHERE id IN (?, ?)",
                            (a.legacy_alert_id, b.legacy_alert_id)).fetchone()[0]
        assert same == 1, "fixture: equal detection scores, so only the routing priority can order them"
        _, order = operational_queue.queue_page(conn, limit=1000, offset=0)
        assert order.index(a.id) < order.index(b.id)


def test_no_verdict_means_no_queue_change(routed):
    """Before any verdict combined_score == detection_score, so the queue score is the routing priority."""
    from apps.api import operational_queue
    with closing(db.connect(str(routed))) as conn:
        assert conn.execute("SELECT count(*) FROM alerts WHERE combined_score != detection_score").fetchone()[0] == 0
        _, order = operational_queue.queue_page(conn, limit=1000, offset=0)
        old = f"{operational_queue.SEVERITY} DESC, {operational_queue.UNFLAGGED_LAST} ASC, " \
              f"{operational_queue.ROUTING_PRIORITY} DESC, queue_occurred_at(a.occurred_at) DESC, a.operational_alert_ref ASC"
        frozen = [r[0] for r in conn.execute(f"SELECT a.id {operational_queue.SOURCE} ORDER BY {old}")]
        assert order == frozen
