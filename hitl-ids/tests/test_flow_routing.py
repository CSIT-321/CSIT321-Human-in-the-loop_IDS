"""Phase B, method B: each group gets one routing decision (analysis/phase-b/GROUPING-METHOD-REVIEW.md).

A group is the queue item. Its route comes from its members, strongest first: any member that meets E1 escalates
the whole group to one Tier 2 case (the representative is the case's primary alert, the qualifying member is
marked); otherwise the first candidate member makes the group a Tier 2 candidate with the reasons. The
new-groups-per-minute limit counts new escalated groups by the minute their first member arrived.
"""
from contextlib import closing
import json
import sys
from pathlib import Path

import pytest

from packages.contracts import db, models as m
from packages.detection import flow_routing
from packages.detection.analyst_work import is_tier1_work
from packages.detection.ranking.severity import load_severity_chart
from flow_group_fixture import GROUPS, grouped_database  # noqa: F401  (pytest fixture)
from test_operational_v2 import snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import (materialize_flagged, materialize_unflagged, route_flagged,  # noqa: E402
                                    route_unflagged)

CHART = load_severity_chart()
IP = {"brute-a": "18.221.219.4", "brute-b": "13.58.98.64", "botnet-1": "10.0.0.66", "botnet-2": "10.0.0.66"}


def grouped(conn):
    """label -> (route, recommended, reasons, case_ref, decision, qualifying_ref).

    Labels: brute-a = first 18.221.219.4 group, brute-b = first 13.58.98.64 group,
    botnet-1 / botnet-2 = the 10.0.0.66 groups in first_seen_at order.
    """
    out = {}
    order = {ip: 0 for ip in IP.values()}
    rows = conn.execute("""
            SELECT g.grouping_key, g.first_seen_at, t.handling_route, t.tier2_recommended,
                   t.tier2_recommendation_reasons, s.case_ref, s.routing_decision, g.qualifying_member_alert_id
            FROM alert_groups g
            JOIN operational_triage_state_v2 t ON t.operational_alert_id = g.representative_operational_alert_id
            LEFT JOIN operational_system_routing s ON s.operational_alert_id = g.representative_operational_alert_id
            ORDER BY g.first_seen_at, g.id""").fetchall()
    for r in rows:
        decision = json.loads(r[6]) if r[6] else None
        qualifying = conn.execute("SELECT source_record_id FROM flow_data WHERE alert_id=?", (r[7],)).fetchone() \
            if r[7] else None
        ip = r[0]
        if ip == "10.0.0.66":
            label = "botnet-1" if order[ip] == 0 else "botnet-2"
        else:
            label = "brute-a" if ip == "18.221.219.4" else "brute-b"
        order[ip] += 1
        out[label] = (r[2], bool(r[3]), tuple(json.loads(r[4])), r[5], decision,
                      qualifying[0] if qualifying else None)
    return out


def prepare(conn, policy=None):
    materialize_flagged(conn)
    return route_flagged(conn, policy=policy)


def test_every_group_gets_one_routing_decision(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        counts = prepare(conn)
        rows = grouped(conn)
    assert len(rows) == 4 and all(v[4] is not None for v in rows.values())
    assert counts == {"auto_escalated": 2, "candidate": 2, "routine": 0}


def test_e1_groups_escalate_whole_with_one_case_and_the_qualifying_member_marked(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn)
        rows = grouped(conn)
        cases = conn.execute("SELECT count(*) FROM tier2_cases WHERE decision_source='system_policy'").fetchone()[0]
    for ref in ("brute-a", "brute-b"):
        route, _, _, case_ref, decision, qualifying = rows[ref]
        assert route == "tier2_case" and case_ref is not None, ref
        assert decision["routeClass"] == "CRITICAL_ESCALATION"
        assert any("E1-flow-rule" in reason for reason in decision["reasons"])
        assert any("group of" in reason for reason in decision["reasons"])
        assert qualifying == GROUPS[ref][0], ref
    assert cases == 2


def test_candidate_groups_carry_the_e3_reason_on_the_representative(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn)
        rows = grouped(conn)
    for ref in ("botnet-1", "botnet-2"):
        route, recommended, reasons, case_ref, _, _ = rows[ref]
        assert (route, recommended, case_ref) == ("tier1_review", True, None), ref
        assert any(reason.startswith("E3") for reason in reasons), reasons


def test_candidate_group_representatives_can_be_claimed(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn)
        ids = [r[0] for r in conn.execute(
            "SELECT representative_operational_alert_id FROM alert_groups g "
            "JOIN operational_triage_state_v2 t ON t.operational_alert_id=g.representative_operational_alert_id "
            "WHERE t.handling_route='tier1_review'")]
        assert len(ids) == 2 and all(is_tier1_work(conn, i) for i in ids)


def test_the_new_groups_limit_downgrades_the_second_group_in_the_same_minute(grouped_database):
    policy = flow_routing.load_flow_routing_policy().model_copy(update={"version": "flow-routing-test-limit",
                                                                        "new_groups_per_minute": 1})
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn, policy=policy)
        rows = grouped(conn)
    # brute-a and brute-b both start at 12:01; the first id wins, the other becomes a candidate.
    assert rows["brute-a"][0] == "tier2_case"
    route, recommended, reasons, case_ref, _, _ = rows["brute-b"]
    assert (route, recommended, case_ref) == ("tier1_review", True, None)
    assert any("limit" in reason.lower() for reason in reasons), reasons


def test_a_switched_off_rule_turns_escalations_into_candidates(grouped_database):
    policy = flow_routing.load_flow_routing_policy().model_copy(update={"version": "flow-routing-test-off",
                                                                        "e1_flow_rule_enabled": False})
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn, policy=policy)
        rows = grouped(conn)
    route, recommended, reasons, case_ref, _, _ = rows["brute-a"]
    assert (route, recommended, case_ref) == ("tier1_review", True, None)
    assert any("switched off" in reason for reason in reasons)


def test_a_second_run_routes_nothing_new(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn)
        audits = conn.execute("SELECT count(*) FROM operational_routing_audit").fetchone()[0]
        assert route_flagged(conn) == {"auto_escalated": 0, "candidate": 0, "routine": 0}
        assert conn.execute("SELECT count(*) FROM operational_routing_audit").fetchone()[0] == audits


def test_routing_leaves_the_legacy_workflow_rows_unchanged(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        before = snapshot(conn)
        prepare(conn)
        assert snapshot(conn) == before


def test_a_group_escalates_when_a_later_member_meets_e1():
    """The qualifying member need not be the representative (the first member)."""
    policy = flow_routing.load_flow_routing_policy()
    a1 = m.Alert.model_construct(evidence_class="ml_only", combined_score=99.0, ml_predicted_class="Port Scan",
                                 attack_category=None)
    a2 = m.Alert.model_construct(evidence_class="corroborated", combined_score=100.0,
                                 ml_predicted_class="Brute Force", attack_category="Brute Force")
    result = flow_routing.route_group([a1, a2], policy, CHART)
    assert result.decision.route == "tier2_case" and result.qualifying_member == 1
    assert any("member" in reason for reason in result.decision.reasons)


def test_the_stored_qualifying_member_is_the_member_that_met_e1_not_the_first(grouped_database, monkeypatch):
    # review 2026-11-06: route_flagged passed members[0] as the qualifying member for every group
    real_e1 = flow_routing._e1
    with closing(db.connect(str(grouped_database))) as conn:
        materialize_flagged(conn)
        third = conn.execute("SELECT alert_id FROM flow_data WHERE source_record_id='AL-0003'").fetchone()[0]
        monkeypatch.setattr(flow_routing, "_e1",
                            lambda alert, policy, sev: real_e1(alert, policy, sev) if alert.id == third else [])
        route_flagged(conn)
        rows = grouped(conn)
    route, _, _, case_ref, _, qualifying = rows["brute-a"]
    assert route == "tier2_case" and case_ref is not None
    assert qualifying == "AL-0003"


def test_routine_groups_store_no_qualifying_member(grouped_database):
    # review 2026-11-06: routine groups were stored with their first member as "qualifying"
    policy = flow_routing.load_flow_routing_policy().model_copy(update={"version": "flow-routing-test-routine",
                                                                        "e3_minimum_score": 101.0})
    with closing(db.connect(str(grouped_database))) as conn:
        prepare(conn, policy=policy)
        rows = grouped(conn)
    for ref in ("botnet-1", "botnet-2"):
        route, recommended, reasons, case_ref, _, qualifying = rows[ref]
        assert (route, recommended, reasons, case_ref) == ("tier1_review", False, (), None), ref
        assert qualifying is None, ref


# D4 (analysis/phase-b/PHASE-B-STATUS.md): every unflagged flow is a single routine Tier 1 item.

def prepare_all(conn, policy=None):
    materialize_flagged(conn)
    route_flagged(conn, policy=policy)
    materialize_unflagged(conn)
    return route_unflagged(conn, policy=policy)


def unflagged_rows(conn):
    return conn.execute(
        """SELECT o.id, t.handling_route, t.tier2_recommended, s.case_ref, s.routing_decision
           FROM operational_alerts_v2 o JOIN alerts a ON a.id = o.legacy_alert_id
           JOIN operational_triage_state_v2 t ON t.operational_alert_id = o.id
           LEFT JOIN operational_system_routing s ON s.operational_alert_id = o.id
           WHERE a.evidence_class = 'none'""").fetchall()


def test_every_unflagged_item_gets_one_routine_tier1_decision(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        counts = prepare_all(conn)
        rows = unflagged_rows(conn)
        claimable = [is_tier1_work(conn, row[0]) for row in rows]
    assert counts == {"auto_escalated": 0, "candidate": 0, "routine": 6}
    assert len(rows) == 6
    assert all(r[1] == "tier1_review" and not r[2] and r[3] is None and r[4] is not None for r in rows), rows
    assert all(claimable)


def test_unflagged_items_rank_below_every_group(grouped_database):
    from apps.api import operational_queue
    with closing(db.connect(str(grouped_database))) as conn:
        prepare_all(conn)
        groups = {r[0] for r in conn.execute("SELECT representative_operational_alert_id FROM alert_groups")}
        _, order = operational_queue.queue_page(conn, limit=1000, offset=0)
    assert set(order[:len(groups)]) == groups, order


def test_routing_unflagged_twice_routes_nothing_new_and_keeps_the_legacy_rows(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        before = snapshot(conn)
        prepare_all(conn)
        again = route_unflagged(conn)
        assert again == {"auto_escalated": 0, "candidate": 0, "routine": 0}
        assert snapshot(conn) == before
