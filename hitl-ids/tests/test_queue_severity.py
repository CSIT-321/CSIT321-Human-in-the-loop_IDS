"""C9 / settled decision 8: the Tier 1 queue is severity-first for EVERY source (user decision 2026-11-07).

Order: severity (Critical > High > Medium > Low > Informational) -> flagged before unflagged inside a level ->
Operational Priority -> newest -> ref.

Severity of a flow alert = alerts.severity (the detector's label).
Severity of a Suricata alert = the approved severity chart's band for its classtype (config/severity-chart.json,
via config/suricata-classtypes-v1.json). A classtype not in the chart falls back to the alert's rule priority:
1 = High, 2 = Medium, 3 = Low, 4 = Informational. Never Critical without a chart entry.
"""
import sqlite3
from contextlib import closing

import pytest

from apps.api import operational_queue
from packages.detection.queue_severity import RANK, severity_label


@pytest.mark.parametrize("category, priority, expected", [
    ("A Network Trojan was detected", 1, "Critical"),          # trojan-activity, chart 9.0
    ("Exploit Kit Activity Detected", 1, "High"),              # exploit-kit, chart 8.5
    ("Detection of a Network Scan", 3, "Low"),                 # network-scan, chart 3.0
    ("Attempted Information Leak", 2, "Low"),                  # attempted-recon, chart 3.0: the chart wins over priority 2
    ("Attempted Administrator Privilege Gain", 1, "Critical"), # attempted-admin, chart 9.0
    ("Misc activity", 3, "Low"),                               # misc-activity, not in chart: priority 3
    ("Misc Attack", 2, "Medium"),                              # misc-attack, not in chart: priority 2
    ("Potential Corporate Privacy Violation", 1, "High"),      # policy-violation, not in chart: never Critical
    ("Some vendor category we do not know", 1, "High"),        # unknown description: priority fallback
    ("Some vendor category we do not know", 4, "Informational"),
    ("Some vendor category we do not know", 9, "Informational"),
])
def test_suricata_severity_comes_from_the_chart_then_the_rule_priority(category, priority, expected):
    assert severity_label("external_nids_alert", None, str(priority), category) == expected


@pytest.mark.parametrize("label", ["Critical", "High", "Medium", "Low", "Informational"])
def test_flow_alert_severity_is_the_detector_label(label):
    assert severity_label("legacy_flow_alert", label, '"ignored"', "ignored") == label


def test_ranks_are_ordered():
    assert RANK["Critical"] > RANK["High"] > RANK["Medium"] > RANK["Low"] > RANK["Informational"]


def _queue(rows):
    """rows: (id, ref, source_kind, legacy severity, evidence_class, native_severity, category, priority, occurred)."""
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.executescript('''CREATE TABLE operational_alerts_v2(id,operational_alert_ref,occurred_at,legacy_alert_id,
                source_kind,native_severity,detection_category);
            CREATE TABLE alerts(id,evidence_class,severity,detection_score,combined_score);
            CREATE TABLE operational_triage_state_v2(operational_alert_id,operational_priority);
            CREATE TABLE operational_system_routing(operational_alert_id);
            CREATE TABLE analyst_work(operational_alert_id,status);
            CREATE TABLE cross_chain_links(hidden_operational_alert_id);''')
        for i, ref, kind, sev, evidence, native, category, priority, when in rows:
            legacy = i if kind == "legacy_flow_alert" else None
            conn.execute("INSERT INTO operational_alerts_v2 VALUES (?,?,?,?,?,?,?)",
                         (i, ref, when, legacy, kind, native, category))
            if legacy:
                conn.execute("INSERT INTO alerts VALUES (?,?,?,?,?)", (i, evidence, sev, 50, 50))  # no verdict: delta 0
            conn.execute("INSERT INTO operational_triage_state_v2 VALUES (?,?)", (i, priority))
        return operational_queue.queue_page(conn, limit=50, offset=0)[1]


T = "2026-11-01T00:00:00Z"
FLOW = "legacy_flow_alert"
NIDS = "external_nids_alert"


def test_a_critical_item_ranks_above_higher_scoring_high_items():
    # The measured C9 gap: a Critical group at 99.6 sat below High groups at 100.
    assert _queue([
        (1, "a", FLOW, "High", "ml_only", '"High"', "x", 100, T),
        (2, "b", FLOW, "High", "ml_only", '"High"', "x", 100, T),
        (3, "c", FLOW, "Critical", "ml_only", '"Critical"', "x", 99.6, T),
    ]) == [3, 1, 2]


def test_a_severe_suricata_alert_is_never_buried_below_flow_alerts():
    # The user's concern: a truly severe Suricata alert must not rank lower because of its source.
    assert _queue([
        (1, "a", FLOW, "High", "ml_only", '"High"', "x", 100, T),
        (2, "b", NIDS, None, None, "1", "A Network Trojan was detected", 85, T),     # Critical by chart
        (3, "c", NIDS, None, None, "3", "Misc activity", 40, T),                     # Low by priority 3
        (4, "d", FLOW, "Low", "ml_only", '"Low"', "x", 30, T),
    ]) == [2, 1, 3, 4]


def test_inside_a_level_flagged_items_rank_above_unflagged_ones():
    # D4 condition 2 holds inside each severity level: an unflagged item with a higher score stays below.
    assert _queue([
        (1, "a", FLOW, "Medium", "none", '"Medium"', "x", 100, T),
        (2, "b", FLOW, "Medium", "ml_only", '"Medium"', "x", 60, T),
        (3, "c", NIDS, None, None, "2", "Misc Attack", 50, T),                        # Medium, external: flagged tier
    ]) == [2, 3, 1]


def test_severity_beats_the_flagged_tier():
    # Severity is the first key. A more severe unflagged item ranks above a less severe flagged one.
    assert _queue([
        (1, "a", FLOW, "Low", "ml_only", '"Low"', "x", 90, T),
        (2, "b", FLOW, "High", "none", '"High"', "x", 20, T),
    ]) == [2, 1]


def test_inside_a_level_and_tier_the_score_then_time_then_ref_decide():
    assert _queue([
        (1, "b", FLOW, "High", "ml_only", '"High"', "x", 90, "2026-11-01T00:00:00Z"),
        (2, "a", FLOW, "High", "ml_only", '"High"', "x", 90, "2026-11-01T00:00:00Z"),
        (3, "c", FLOW, "High", "ml_only", '"High"', "x", 90, "2026-11-02T00:00:00Z"),
        (4, "d", FLOW, "High", "ml_only", '"High"', "x", 95, "2026-10-01T00:00:00Z"),
    ]) == [4, 3, 2, 1]
