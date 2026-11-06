"""Project flagged flow alerts into the operational queue as groups (phase A, method B).

The operational workstation reads only ``operational_alerts_v2``. Detection writes ``alerts``, so on a
detection database the workstation is empty until this runs. Method B (analysis/phase-b/GROUPING-METHOD-REVIEW.md):
flagged alerts group by source IP - the next alert within ``group_window_minutes`` of the group's last one joins the
group. Each group is one operational alert (its first member, the representative), so the queue lists groups, not
flows. Unflagged flows are not queue work and join no group. The legacy workflow's tables never change.

    python scripts/materialize_flow_queue.py --database data/demo.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.contracts import db, models as m  # noqa: E402
from packages.detection.adapters.operational_v2 import materialize_source  # noqa: E402
from packages.detection.flow_routing import load_flow_routing_policy, route_flow_alert  # noqa: E402
from packages.detection.ranking.severity import load_severity_chart  # noqa: E402

FLAGGED = """SELECT a.id, f.src_ip, json_extract(f.flow_features, '$.Timestamp')
             FROM alerts a JOIN flow_data f ON f.alert_id = a.id
             WHERE a.evidence_class != 'none' ORDER BY a.id"""
UNROUTED = """SELECT g.id, g.first_seen_at, g.representative_operational_alert_id
              FROM alert_groups g
              LEFT JOIN operational_system_routing s
                ON s.operational_alert_id = g.representative_operational_alert_id
              WHERE s.operational_alert_id IS NULL ORDER BY g.first_seen_at, g.id"""
MEMBERS = """SELECT a.* FROM alert_group_members gm JOIN alerts a ON a.id = gm.legacy_alert_id
             WHERE gm.group_id=? ORDER BY gm.occurred_at, gm.legacy_alert_id"""


def _utc(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def group_flagged(conn: sqlite3.Connection, *, policy=None) -> tuple[int, int, int]:
    """(new members, new groups, already-grouped members). Idempotent. Caller commits."""
    db.migrate(conn)
    policy = policy or load_flow_routing_policy()
    gap = timedelta(minutes=policy.group_window_minutes)
    grouped = {row[0] for row in conn.execute("SELECT legacy_alert_id FROM alert_group_members")}
    rows = [(alert_id, src_ip, _utc(ts)) for alert_id, src_ip, ts in conn.execute(FLAGGED).fetchall()
            if alert_id not in grouped]
    rows.sort(key=lambda r: (r[2], r[0]))
    open_groups: dict[str, tuple[datetime, int]] = {}
    new_members = new_groups = 0
    stamp = db.format_timestamp(datetime.now(timezone.utc))
    for alert_id, src_ip, when in rows:
        previous = open_groups.get(src_ip)
        if previous is None or when - previous[0] > gap:
            group_id = conn.execute(
                "INSERT INTO alert_groups (group_ref, grouping_key, first_seen_at, last_seen_at, member_count, "
                "representative_operational_alert_id, qualifying_member_alert_id, case_ref, created_at) "
                "VALUES (?,?,?,?,?,NULL,NULL,NULL,?)",
                (str(uuid5(NAMESPACE_URL, f"flow-group:{alert_id}")), src_ip,
                 db.format_timestamp(when), db.format_timestamp(when), 1, stamp)).lastrowid
            new_groups += 1
        else:
            group_id = previous[1]
            conn.execute("UPDATE alert_groups SET last_seen_at=?, member_count=member_count+1 WHERE id=?",
                         (db.format_timestamp(when), group_id))
        open_groups[src_ip] = (when, group_id)
        conn.execute("INSERT INTO alert_group_members (group_id, legacy_alert_id, source_ip, occurred_at, joined_at) "
                     "VALUES (?,?,?,?,?)",
                     (group_id, alert_id, src_ip, db.format_timestamp(when), stamp))
        new_members += 1
    return new_members, new_groups, len(grouped)


def materialize_flagged(conn: sqlite3.Connection, *, policy=None) -> tuple[int, int, int]:
    """(new members, new groups, already-grouped members). Re-running creates nothing."""
    members, new_groups, existing = group_flagged(conn, policy=policy)
    conn.commit()
    unprojected = conn.execute(
        "SELECT g.id, gm.legacy_alert_id FROM alert_group_members gm JOIN alert_groups g ON g.id = gm.group_id "
        "WHERE g.representative_operational_alert_id IS NULL GROUP BY g.id ORDER BY MIN(gm.occurred_at), g.id").fetchall()
    for group_id, legacy_id in unprojected:
        projected = materialize_source(conn, "legacy_flow_alert", legacy_id)
        conn.execute("UPDATE alert_groups SET representative_operational_alert_id=? WHERE id=?",
                     (projected.id, group_id))
        conn.commit()
    return members, new_groups, existing


def route_flagged(conn: sqlite3.Connection, *, policy=None) -> dict[str, int]:
    """Give every not yet routed group its one system routing decision (phase B, method B).

    One transaction per group, so a failure leaves earlier decisions in place and a re-run continues.
    The new-groups-per-minute limit counts new escalated groups by the minute their first member arrived.
    Returns counts by outcome; a second run returns all zeros.
    """
    policy = policy or load_flow_routing_policy()
    chart = load_severity_chart()
    counts = {"auto_escalated": 0, "candidate": 0, "routine": 0}
    minute_escalations: dict[str, int] = {}
    for group_id, first_seen, rep in conn.execute(UNROUTED).fetchall():
        members = [db.from_row(m.Alert, row) for row in conn.execute(MEMBERS, (group_id,))]
        minute = first_seen[:16] if first_seen else ""
        conn.execute("BEGIN IMMEDIATE")
        try:
            outcome, qualifying = route_flow_alert(
                conn, rep, policy=policy, chart=chart, group_members=members,
                escalated_groups_this_minute=minute_escalations.get(minute, 0),
                qualifying_member_alert_id=members[0].id)
            if outcome == "auto_escalated":
                minute_escalations[minute] = minute_escalations.get(minute, 0) + 1
                case_ref = conn.execute("SELECT case_ref FROM operational_system_routing WHERE operational_alert_id=?",
                                        (rep,)).fetchone()[0]
                conn.execute("UPDATE alert_groups SET qualifying_member_alert_id=?, case_ref=? WHERE id=?",
                             (qualifying, case_ref, group_id))
            else:
                conn.execute("UPDATE alert_groups SET qualifying_member_alert_id=? WHERE id=?",
                             (qualifying, group_id))
            counts[outcome] += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    if not args.database.exists():
        print(f"no database at {args.database}", file=sys.stderr)
        return 2
    with closing(db.connect(args.database)) as conn:
        members, new_groups, existing = materialize_flagged(conn)
        counts = route_flagged(conn)
    print(f"grouped {members} alerts into {new_groups} new groups, already grouped {existing}")
    print("routed: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
