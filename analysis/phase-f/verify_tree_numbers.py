"""Read-only check of every count and threshold quoted in decision-tree/tree.json against a routed demo copy and the config.
Usage: python verify_tree_numbers.py <routed copy>"""
import json
import sqlite3
import sys
from pathlib import Path

H = Path(__file__).resolve().parents[2] / "hitl-ids"
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
q = lambda s: c.execute(s).fetchone()[0]
pol = json.loads((H / "config/flow-routing-v1.json").read_text())
chart = {e["model_class"]: e["severity"] for e in json.loads((H / "config/severity-chart.json").read_text())["entries"] if e["model_class"]}
gt = json.loads((H / "data/processed/demo_ground_truth.json").read_text())
checks = {
    "N1 corroborated 200": q("SELECT count(*) FROM alerts WHERE evidence_class='corroborated'") == 200,
    "N1 signature_override 0": q("SELECT count(*) FROM alerts WHERE evidence_class='signature_override'") == 0,
    "N1 ml_only 796": q("SELECT count(*) FROM alerts WHERE evidence_class='ml_only'") == 796,
    "N1 none 4004": q("SELECT count(*) FROM alerts WHERE evidence_class='none'") == 4004,
    "N2 is_critical == score>=80 (0 mismatches)": q("SELECT count(*) FROM alerts WHERE is_critical != (combined_score>=80)") == 0,
    "N3 flagged 996": q("SELECT count(*) FROM alerts WHERE evidence_class!='none'") == 996,
    "N4 groups 81": q("SELECT count(*) FROM alert_groups") == 81,
    "N4 window 30": pol["groupWindowMinutes"] == 30,
    "N5 auto 3 groups": q("SELECT count(*) FROM operational_triage_state_v2 WHERE handling_route='tier2_case'") == 3,
    "N5 E1 score 80, suricata sev 2, 5/min": (pol["e1MinimumScore"], pol["e1SuricataMaximumSeverity"], pol["newGroupsPerMinute"]) == (80, 2, 5),
    "N5 E1 alerts 200, 0 benign": q("SELECT count(*) FROM alerts WHERE evidence_class='corroborated' AND combined_score>=80") == 200
        and all(gt[r[0]]["groundTruth"] == "malicious" for r in c.execute(
            "SELECT f.source_record_id FROM alerts a JOIN flow_data f ON f.alert_id=a.id WHERE a.evidence_class='corroborated'")),
    "N6 candidates 74": q("SELECT count(*) FROM operational_triage_state_v2 WHERE handling_route='tier1_review' AND tier2_recommended=1") == 74,
    "N6 routine 4 groups": q("""SELECT count(*) FROM operational_triage_state_v2 t JOIN alert_groups g ON g.representative_operational_alert_id=t.operational_alert_id
                                WHERE t.handling_route='tier1_review' AND t.tier2_recommended=0""") == 4,
    "N6 E3 90 / 7": (pol["e3MinimumScore"], pol["e3MinimumAttackSeverity"]) == (90, 7.0),
    "N6 severities": (chart["Infiltration"], chart["Botnet"], chart["Web Attack"], chart["DDoS"], chart["DoS"], chart["Brute Force"]) == (9.5, 9.0, 8.0, 7.5, 6.5, 5.0),
    "N7 0 failed routes": q("SELECT count(*) FROM operational_triage_state_v2 WHERE review_reason LIKE 'Routing could not be evaluated%'") == 0,
    "N7 4085 routes": q("SELECT count(*) FROM operational_system_routing") == 4085,
}
for k, v in checks.items():
    print("PASS" if v else "FAIL", k)
print(f"{sum(checks.values())} of {len(checks)} pass")
