"""B6, option 1 (user decision 2026-11-07): one Tier 1 eligibility rule with three results.

`packages/detection/tier1_eligibility.py` answers "is this alert Tier 1 work" for every consumer:

    current     tier1_review / triage AND a system routing row  -> claim, verdict, selective review, routing
    historical  tier1_review / triage, NO routing row            -> selective review and the "Historical ..."
                (the non-bundle admission path,                     routing actions only; no claim, no verdict
                 external_admission.py:173-186)
    none        anything else (staged, Tier 2, candidate)        -> none of them

Before B6 the rule was written out in five places with three different meanings. Behaviour is unchanged:
these tests pin what each consumer did before, now through the one rule.
"""
from contextlib import closing
import sys
from pathlib import Path

import pytest

from packages.contracts import db, models as m
from packages.detection import analyst_verdict, analyst_work, routing, selective_review
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.external_admission import admit_external
from packages.detection.tier1_eligibility import CURRENT_TIER1_SQL, in_tier1_triage, tier1_status
from apps.api import auth
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)
from legacy_suricata_fixture import stage_file
from test_external_operational_admission import accept, admit_request
from test_selective_review import safe_context

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import materialize_flagged, materialize_unflagged, route_flagged  # noqa: E402


@pytest.fixture
def database(grouped_database):
    return str(grouped_database)


@pytest.fixture
def mixed(database):
    """One database with all three results: current (routed Tier 1 flow groups), historical (non-bundle
    Suricata, admitted with no routing row) and none (an escalated group, unrouted unflagged flows)."""
    with closing(db.connect(database)) as conn:
        auth.ensure_demo_accounts(conn)
        conn.commit()
        actor = conn.execute("SELECT id FROM users WHERE username='g.ang'").fetchone()[0]
        stage_file(conn, Path(__file__).parent / "fixtures/selective-review-demo.json", "selective-demo")
        historical = []
        for (source,) in conn.execute("SELECT id FROM external_alert_inbox WHERE sensor_id='selective-demo' "
                                      "ORDER BY id").fetchall():
            receipt, _ = admit_external(conn, source, actor_id=actor, request=admit_request(accept(conn, actor, source)),
                                        trusted_context=safe_context())
            historical.append(read_projection(conn, receipt["operational_alert_id"]))
            seed_synthetic_facts(conn, historical[-1], safe_context(), m.utc_now())
        materialize_flagged(conn)
        route_flagged(conn)
        materialize_unflagged(conn)
        ids = {status: [] for status in ("current", "historical", "none")}
        for (alert_id,) in conn.execute("SELECT id FROM operational_alerts_v2 ORDER BY id").fetchall():
            ids[tier1_status(conn, alert_id)].append(alert_id)
    return actor, historical, ids


def test_the_fixture_holds_every_result(database, mixed):
    _, historical, ids = mixed
    assert all(ids.values()), {k: len(v) for k, v in ids.items()}
    assert {a.id for a in historical} <= set(ids["historical"])
    with closing(db.connect(database)) as conn:
        routes = {read_triage(conn, i).handling_route for i in ids["none"]}
    assert routes == {"unassigned", "tier2_case"}, routes


def test_the_rule_reads_route_stage_and_the_routing_row(database, mixed):
    _, _, ids = mixed
    with closing(db.connect(database)) as conn:
        for status, members in ids.items():
            for alert_id in members:
                state = read_triage(conn, alert_id)
                routed = conn.execute("SELECT 1 FROM operational_system_routing WHERE operational_alert_id=?",
                                      (alert_id,)).fetchone() is not None
                expected = "none" if not in_tier1_triage(state) else "current" if routed else "historical"
                assert status == expected, (alert_id, status, expected)


def test_claim_and_verdict_accept_current_work_only(database, mixed):
    """Claim (`is_tier1_work`) and verdict (`_eligible`) share the rule. `read_verdict.can_record` also needs the
    caller to own the claim, so with no claim it is False everywhere; the eligibility part is checked directly."""
    actor, _, ids = mixed
    with closing(db.connect(database)) as conn:
        for status, members in ids.items():
            for alert_id in members[:5]:
                ref = conn.execute("SELECT operational_alert_ref FROM operational_alerts_v2 WHERE id=?",
                                   (alert_id,)).fetchone()[0]
                alert = analyst_verdict._alert(conn, ref)
                assert analyst_work.is_tier1_work(conn, alert_id) == (status == "current"), alert_id
                assert analyst_verdict._eligible(conn, alert) == (status == "current"), alert_id
                assert not analyst_verdict.read_verdict(conn, ref, actor).can_record, alert_id


def test_selective_review_and_routing_accept_current_and_historical(database, mixed):
    """Selective review: current and historical are eligible. Routing: `manual_escalate` on both; staged alerts
    get `admit_tier1` only; Tier 2 gets nothing (baseline b6-before.json)."""
    _, _, ids = mixed
    with closing(db.connect(database)) as conn:
        for status, members in ids.items():
            for alert_id in members[:5]:
                ref = conn.execute("SELECT operational_alert_ref FROM operational_alerts_v2 WHERE id=?",
                                   (alert_id,)).fetchone()[0]
                eligible = selective_review.read_review(conn, ref).eligible_alert
                state = read_triage(conn, alert_id)
                actions = routing.allowed_actions(state, tier1_status(conn, alert_id))
                assert eligible == (status != "none"), (alert_id, status)
                if status == "none":
                    assert actions in ((), ("admit_tier1",)), (alert_id, actions)
                else:
                    assert "manual_escalate" in actions, (alert_id, actions)


def test_routing_actions_need_the_tier1_status():
    """The status is required: a caller cannot forget it and silently fall back to route/stage only."""
    import inspect
    parameters = inspect.signature(routing.allowed_actions).parameters
    assert list(parameters)[:2] == ["state", "status"]
    assert parameters["status"].default is inspect.Parameter.empty


def test_the_queue_sql_and_the_function_agree_on_every_alert(database, mixed):
    _, _, ids = mixed
    with closing(db.connect(database)) as conn:
        from apps.api.operational_queue import SOURCE
        by_sql = {r[0] for r in conn.execute(f"SELECT a.id {SOURCE} WHERE {CURRENT_TIER1_SQL}")}
    assert by_sql == set(ids["current"])


def test_every_consumer_imports_the_one_rule():
    """No module restates the route/stage pair; the evaluation package (frozen research code), the triage policy
    gate (a different question) and the recorded review policy (part of a stored input hash) are excluded."""
    root = Path(__file__).resolve().parents[1]
    restated = []
    for path in list((root / "packages/detection").rglob("*.py")) + list((root / "apps/api").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(root).as_posix()
        if name in ("packages/detection/tier1_eligibility.py", "packages/detection/triage_policy_service.py",
                    "packages/detection/selective_review_policy.py"):
            continue
        for line in text.splitlines():
            squeezed = line.replace(" ", "").replace('"', "'")
            if "('tier1_review','triage')" in squeezed and "route,stage=" not in squeezed:
                restated.append(f"{name}: {line.strip()}")
            if "handling_route='tier1_review'ANDt.workflow_stage='triage'" in squeezed:
                restated.append(f"{name}: {line.strip()}")
    assert restated == []
