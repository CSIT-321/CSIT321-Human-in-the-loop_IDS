"""B7 (review S1-03, S1-11): the database refuses changes the schema says cannot happen.

- `alerts.detection_score`, `alert_ref`, `evidence_class`, `dataset_id`, `run_id` never change. Guardrails and
  family learning read `detection_score` as their anchor, and `feedback_events.original_score` must keep agreeing
  with it. A plain UPDATE used to succeed silently.
- `operational_triage_state_v2` rows are never deleted. Without the row every V2 read of the alert fails, while
  the queue's LEFT JOIN silently ranks it last.
"""
from contextlib import closing
import sys
from pathlib import Path

import pytest

from packages.contracts import db
from flow_group_fixture import grouped_database  # noqa: F401  (pytest fixture)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from materialize_flow_queue import materialize_flagged  # noqa: E402

FROZEN = {"detection_score": "CASE WHEN detection_score < 50 THEN detection_score + 1 ELSE detection_score - 1 END",
          "alert_ref": "'00000000-0000-4000-8000-000000000000'",
          # these three also have CHECK / FK guards; the trigger must answer first
          "evidence_class": "CASE evidence_class WHEN 'none' THEN 'ml_only' ELSE 'none' END",
          "dataset_id": "dataset_id + 1000", "run_id": "run_id + 1000"}


def test_a_valid_detection_score_change_is_refused(grouped_database):
    """The S1-03 gap itself: an in-range score passes every CHECK, so only a trigger stops it."""
    with closing(db.connect(str(grouped_database))) as conn:
        alert_id, before = conn.execute("SELECT id, detection_score FROM alerts ORDER BY id LIMIT 1").fetchone()
        with pytest.raises(Exception, match="immutable"):
            conn.execute("UPDATE alerts SET detection_score = ? WHERE id = ?", (50.0 if before != 50.0 else 51.0,
                                                                              alert_id))


@pytest.mark.parametrize("column", sorted(FROZEN))
def test_a_frozen_alert_column_cannot_change(grouped_database, column):
    with closing(db.connect(str(grouped_database))) as conn:
        alert_id = conn.execute("SELECT id FROM alerts ORDER BY id LIMIT 1").fetchone()[0]
        with pytest.raises(Exception, match="immutable"):
            conn.execute(f"UPDATE alerts SET {column} = {FROZEN[column]} WHERE id = ?", (alert_id,))


def test_the_columns_feedback_moves_still_change(grouped_database):
    """The trigger must not block the feedback service's own writes."""
    with closing(db.connect(str(grouped_database))) as conn:
        alert_id = conn.execute("SELECT id FROM alerts ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute("UPDATE alerts SET combined_score = 12.5, severity = 'Low', requires_review = 1, "
                     "status = 'new', updated_at = updated_at WHERE id = ?", (alert_id,))
        # writing a frozen column with its own value is not a change
        conn.execute("UPDATE alerts SET detection_score = detection_score, evidence_class = evidence_class "
                     "WHERE id = ?", (alert_id,))
        assert conn.execute("SELECT combined_score FROM alerts WHERE id = ?", (alert_id,)).fetchone()[0] == 12.5


def test_triage_state_rows_cannot_be_deleted(grouped_database):
    with closing(db.connect(str(grouped_database))) as conn:
        materialize_flagged(conn)
        assert conn.execute("SELECT count(*) FROM operational_triage_state_v2").fetchone()[0] > 0
        with pytest.raises(Exception, match="cannot be deleted"):
            conn.execute("DELETE FROM operational_triage_state_v2")
