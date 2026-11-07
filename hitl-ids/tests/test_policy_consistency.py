"""B8 (review S3-06): one policy stated in several config files must say the same thing.

Editing one copy used to make staging's proposed priority, the operational priority, the auto-route and the flow
routing disagree with no error. This test loads every copy and fails on the first difference.

Deliberately NOT pinned: `selective-review-v1.json` campaignAlertThreshold (5) vs routing (3). They are different
rules. Routing escalates only when `repeated_campaign` is true AND the count reaches 3; selective review blocks a
deferral when `repeated_campaign` is true OR the count reaches 5. With `repeated_campaign` true both act; with it
false routing never escalates on count alone, so no alert gets opposite answers.
"""
import json
from pathlib import Path

from packages.contracts.models import GUARDRAIL_DEFAULTS
from packages.detection.ranking import formulas

CONFIG = Path(__file__).resolve().parents[1] / "config"


def load(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def test_suricata_severity_to_priority_is_one_map():
    triage = load("operational-triage-v1.json")["suricata_severity_priority"]
    admission = load("external-admission.json")["severity_to_priority"]
    assert triage == admission


def test_routing_thresholds_match_the_triage_policy():
    routing, triage = load("system-routing-v1.json"), load("operational-triage-v1.json")
    assert routing["highPriorityThreshold"] == triage["high_priority_threshold"]
    assert routing["campaignAlertThreshold"] == triage["campaign_alert_threshold"]


def test_flow_routing_thresholds_match_the_ranking_constants():
    flow = load("flow-routing-v1.json")
    assert flow["e3MinimumScore"] == formulas.TIER2_SCORE
    assert flow["e3MinimumAttackSeverity"] == formulas.TIER2_SEVERITY
    # E1 = corroborated AND is_critical, and is_critical is combined_score >= critical_alert_threshold
    assert flow["e1MinimumScore"] == GUARDRAIL_DEFAULTS["critical_alert_threshold"][0]
