"""Phase A, method B: flagged flow alerts enter the operational queue as groups.

Every flagged flow alert joins exactly one group (same source IP, next alert within 30 minutes of the group's last
one). Each group is one operational alert - its first member, the representative - so the queue lists groups, not
flows. Unflagged flows join no group. The legacy workflow's rows never change.
"""
from contextlib import closing
import subprocess
import sys
from pathlib import Path

import pytest

from packages.contracts import db
from flow_group_fixture import GROUPS, grouped_database  # noqa: F401  (pytest fixture)
from test_operational_v2 import snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import materialize_flagged  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/materialize_flow_queue.py"


def membership(conn):
    """group id -> source_record_ids in arrival order."""
    out = {}
    for group_id, record in conn.execute(
            """SELECT gm.group_id, f.source_record_id FROM alert_group_members gm
               JOIN flow_data f ON f.alert_id = gm.legacy_alert_id
               ORDER BY gm.occurred_at, gm.legacy_alert_id"""):
        out.setdefault(group_id, []).append(record)
    return out


def expected_groups(conn):
    """group id -> grouping_key, ordered by first_seen_at (one IP can own several groups)."""
    return [tuple(r) for r in conn.execute(
        "SELECT id, grouping_key FROM alert_groups ORDER BY first_seen_at, id")]


def test_every_flagged_alert_joins_exactly_one_group_and_no_unflagged_one(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        flagged = {r[0] for r in conn.execute("SELECT id FROM alerts WHERE evidence_class != 'none'")}
        materialize_flagged(conn)
        members = [r[0] for r in conn.execute("SELECT legacy_alert_id FROM alert_group_members")]
    assert sorted(members) == sorted(flagged)


def test_groups_split_by_source_and_by_the_30_minute_window(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        materialize_flagged(conn)
        got = sorted(membership(conn).values())
        groups = expected_groups(conn)
    assert got == sorted(GROUPS.values())
    assert [key for _, key in groups] == ["18.221.219.4", "13.58.98.64", "10.0.0.66", "10.0.0.66"]


def test_each_group_is_one_queue_item_and_it_is_the_first_member(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        materialize_flagged(conn)
        groups = membership(conn)
        reps = dict(conn.execute(
            """SELECT g.id, f.source_record_id FROM alert_groups g
               JOIN operational_alerts_v2 o ON o.id = g.representative_operational_alert_id
               JOIN flow_data f ON f.alert_id = o.legacy_alert_id"""))
        projected = conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0]
    assert projected == len(groups) == 4
    assert {key: members[0] for key, members in groups.items()} == reps


def test_the_group_tables_are_append_only(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        materialize_flagged(conn)
        # group identity is frozen; only last_seen_at / member_count grow, and links can be set once
        for sql in ("UPDATE alert_groups SET grouping_key = 'x'", "DELETE FROM alert_groups",
                    "UPDATE alert_group_members SET occurred_at = 'x'", "DELETE FROM alert_group_members"):
            with pytest.raises(Exception, match="append-only|immutable"):
                conn.execute(sql)
        conn.execute("UPDATE alert_groups SET member_count = member_count + 1, last_seen_at = last_seen_at")


def test_the_legacy_workflow_rows_do_not_change(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        before = snapshot(conn)
        materialize_flagged(conn)
        assert snapshot(conn) == before


def test_a_second_run_creates_nothing(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        first = materialize_flagged(conn)
        second = materialize_flagged(conn)
        assert first == (15, 4, 0) and second == (0, 0, 15)


def test_the_command_line_reports_what_it_did(grouped_database):
    result = subprocess.run([sys.executable, str(SCRIPT), "--database", str(grouped_database)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "grouped 15 alerts into 4 new groups, already grouped 0" in result.stdout
