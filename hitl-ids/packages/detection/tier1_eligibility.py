"""The one Tier 1 eligibility rule (B6, review S4-05; user decision 2026-11-07, option 1).

Every consumer that asks "is this alert Tier 1 work" calls this module. The rule has three results:

    current     tier1_review / triage AND a system routing row. Claim, verdict, selective review and the
                routing actions all accept it. Every flow item and every correlated Suricata alert routed by
                the system policy is current.
    historical  tier1_review / triage with NO system routing row. Only the non-bundle admission path makes
                these (`external_admission.py`, the `apply_triage_policy` + `admit_tier1` branch). Selective
                review and the routing actions labelled "Historical ..." accept it; claim and verdict refuse it.
    none        any other route or stage (staged, Tier 2 candidate, Tier 2 case).

Behaviour is unchanged from before B6; only the rule's location is. Baseline: analysis/phase-b/b6_baseline.py.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from packages.contracts.operational_v2 import OperationalTriageStateV2
from packages.detection.adapters.operational_v2 import read_triage

Tier1Status = Literal["current", "historical", "none"]

TIER1_TRIAGE = ("tier1_review", "triage")

#: SQL for "current" over the queue's joins (`t` = triage state, `s` = system routing, LEFT JOINed).
CURRENT_TIER1_SQL = ("s.operational_alert_id IS NOT NULL AND t.handling_route='tier1_review' "
                     "AND t.workflow_stage='triage'")


def in_tier1_triage(state: OperationalTriageStateV2) -> bool:
    """Route and stage only. Use `tier1_status` unless the routing row is known not to matter."""
    return (state.handling_route, state.workflow_stage) == TIER1_TRIAGE


def has_system_route(conn: sqlite3.Connection, alert_id: int) -> bool:
    return conn.execute("SELECT 1 FROM operational_system_routing WHERE operational_alert_id=?",
                        (alert_id,)).fetchone() is not None


def tier1_status(conn: sqlite3.Connection, alert_id: int,
                 state: OperationalTriageStateV2 | None = None) -> Tier1Status:
    state = state if state is not None else read_triage(conn, alert_id)
    if not in_tier1_triage(state):
        return "none"
    return "current" if has_system_route(conn, alert_id) else "historical"


__all__ = ["CURRENT_TIER1_SQL", "TIER1_TRIAGE", "Tier1Status", "has_system_route", "in_tier1_triage",
           "tier1_status"]
