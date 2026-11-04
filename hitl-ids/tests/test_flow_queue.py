"""Phase A of the tier views: the flagged flow alerts enter the operational queue, unchanged.

The operational (V2) workstation reads only ``operational_alerts_v2``. On the approved demo database
that table is empty, so the workstation showed 0 of 996 flagged alerts. These tests pin the fix: every
flagged flow alert is projected exactly once, an unflagged flow is not, and the legacy workflow's own
rows do not change.
"""
from contextlib import closing
import subprocess
import sys
from pathlib import Path

from packages.contracts import db
from test_api import database  # noqa: F401  (pytest fixture)
from test_operational_v2 import snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import materialize_flagged  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/materialize_flow_queue.py"


def flagged_ids(conn):
    return {row[0] for row in conn.execute("SELECT id FROM alerts WHERE evidence_class != 'none'")}


def projected_ids(conn):
    return {row[0] for row in conn.execute(
        "SELECT legacy_alert_id FROM operational_alerts_v2 WHERE source_kind = 'legacy_flow_alert'")}


def test_every_flagged_flow_alert_is_projected_and_no_unflagged_one(database):
    with closing(db.connect(str(database))) as conn:
        expected = flagged_ids(conn)
        assert expected, "the synthetic capture must contain flagged alerts"
        unflagged = {row[0] for row in conn.execute("SELECT id FROM alerts WHERE evidence_class = 'none'")}
        assert unflagged, "the synthetic capture must contain unflagged flows"

        created, existing = materialize_flagged(conn)

        assert (created, existing) == (len(expected), 0)
        assert projected_ids(conn) == expected
        assert not projected_ids(conn) & unflagged


def test_the_legacy_workflow_rows_do_not_change(database):
    with closing(db.connect(str(database))) as conn:
        before = snapshot(conn)
        materialize_flagged(conn)
        assert snapshot(conn) == before


def test_a_second_run_creates_nothing(database):
    with closing(db.connect(str(database))) as conn:
        first, _ = materialize_flagged(conn)
        rows = conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0]

        created, existing = materialize_flagged(conn)

        assert (created, existing) == (0, first)
        assert conn.execute("SELECT count(*) FROM operational_alerts_v2").fetchone()[0] == rows


def test_the_command_line_reports_what_it_did(database):
    result = subprocess.run([sys.executable, str(SCRIPT), "--database", str(database)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with closing(db.connect(str(database))) as conn:
        assert f"created {len(flagged_ids(conn))}, already present 0" in result.stdout
