"""Build the walkthrough database with BOTH lanes, and record the stored facts of each lane.

Lane 1 (Suricata): one real eve.json alert staged -> eligibility review -> admitted -> its own queue item.
Lane 2 (flow): the same packets' 54 flows -> one group -> representative -> E1 Tier 2 case.

data/demo.db is only copied, never written. The copy lives at %LOCALAPPDATA%/Temp/hitl-review/p2w.db.
Output: data/lanes.json
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3] / "hitl-ids"
sys.path[:0] = [str(ROOT)]
from packages.contracts import db  # noqa: E402
from packages.detection.external_admission import (  # noqa: E402
    AdmissionRequest, EligibilityRequest, admit_external, review_eligibility)

OUT = Path(__file__).resolve().parent / "data"
DB = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\p2w.db"))
GT = json.loads((ROOT / "data/processed/demo_ground_truth.json").read_text(encoding="utf-8"))


def build() -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(ROOT / "data" / "demo.db", DB)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "materialize_flow_queue.py"), "--database", str(DB)],
                   check=True, cwd=ROOT)


def stage_one_alert(alert: dict) -> dict:
    window = OUT / "eve-window.jsonl"
    window.write_text(json.dumps(alert) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_suricata_eve.py"),
                             "--input", str(window), "--sensor-id", "p2w-sensor",
                             "--capture-scope", "p2w-capture-1", "--database", str(DB)],
                            capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"import failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def rows(c, sql, params=()):
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql, params)]


def main() -> None:
    alert = json.loads((OUT / "suricata_alert.json").read_text(encoding="utf-8"))["alert"]
    raw_alert = dict(alert)
    raw_alert["event_type"] = "alert"
    build()
    imported = stage_one_alert(raw_alert)
    print("import:", json.dumps(imported))

    facts = {"import": imported, "suricata": {}, "flow": {}}
    with db.connect(DB) as c:
        inbox = rows(c, """SELECT id, detection_title, detection_category, native_severity,
                                  proposed_operational_priority, admission_decision, import_status,
                                  source_ip, destination_ip, destination_port, occurred_at, detector_source,
                                  policy_snapshot FROM external_alert_inbox ORDER BY id LIMIT 1""")[0]
        facts["suricata"]["inbox"] = inbox
        actor = c.execute("SELECT id, display_name, role FROM users WHERE username='g.ang'").fetchone()
        actor_id = actor[0]
        facts["suricata"]["actor"] = {"id": actor[0], "name": actor[1], "role": actor[2]}
        review = review_eligibility(c, inbox["id"], actor_id=actor_id,
                                    request=EligibilityRequest(request_id=uuid4(), expected_review_id=None,
                                                               reason="Real packet evidence checked: SSH scan burst.",
                                                               decision="accepted"))
        c.commit()
        facts["suricata"]["review"] = review if isinstance(review, dict) else getattr(review, "__dict__", str(review))
        adm = admit_external(c, inbox["id"], actor_id=actor_id,
                             request=AdmissionRequest(request_id=uuid4(),
                                                      expected_review_id=int(facts["suricata"]["review"]["id"]),
                                                      reason="Admit to Tier 1 for analyst triage."))
        c.commit()
        facts["suricata"]["admission"] = adm if isinstance(adm, dict) else getattr(adm, "__dict__", str(adm))

        op = rows(c, """SELECT o.* FROM operational_alerts_v2 o
                        JOIN external_operational_admission a ON a.operational_alert_id=o.id
                        WHERE a.external_inbox_id=?""", (inbox["id"],))[0]
        state = rows(c, "SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?", (op["id"],))[0]
        classification = rows(c, "SELECT * FROM operational_system_routing WHERE operational_alert_id=?", (op["id"],))[0]
        facts["suricata"]["operationalAlert"] = {
            k: op[k] for k in ("operational_alert_ref", "source_kind", "detector_source", "detection_title",
                               "detection_category", "native_severity", "occurred_at", "src_ip", "src_port",
                               "destination_ip", "destination_port", "protocol", "external_inbox_id")}
        facts["suricata"]["triage"] = {k: state[k] for k in ("operational_priority", "priority_band",
                                                             "handling_route", "workflow_stage", "review_required",
                                                             "decision_source", "triage_policy_version")}
        import json as _json
        facts["suricata"]["classification"] = {
            "classification": _json.loads(classification["classification"]) if classification["classification"] else None,
            "routing_decision": classification["routing_decision"],
            "policy": classification["classification_policy"], "routing_policy": classification["routing_policy"]}

        # ---- flow lane: the group whose 54 flows Suricata matched ----
        grp = rows(c, """SELECT g.id, g.group_ref, g.member_count, g.first_seen_at, g.last_seen_at,
                                g.representative_operational_alert_id
                         FROM alert_groups g WHERE g.member_count=54 AND g.grouping_key='13.58.98.64'""")[0]
        rep_op = grp["representative_operational_alert_id"]
        rep = rows(c, """SELECT o.operational_alert_ref, o.legacy_alert_id FROM operational_alerts_v2 o
                         WHERE o.id=?""", (rep_op,))[0]
        al = rows(c, "SELECT * FROM alerts WHERE id=?", (rep["legacy_alert_id"],))[0]
        st = rows(c, "SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?", (rep_op,))[0]
        case = rows(c, """SELECT t.case_ref, t.decision_source, s.status FROM tier2_cases t
                          JOIN tier2_case_state s ON s.case_id=t.id
                          WHERE t.primary_operational_alert_id=?""", (rep_op,))[0]
        members = [r["source_record_id"] for r in rows(c, """SELECT f.source_record_id FROM alert_group_members m
                    JOIN flow_data f ON f.alert_id=m.legacy_alert_id WHERE m.group_id=? ORDER BY m.occurred_at""",
                    (grp["id"],))]
        truth = {}
        for rec in members:
            k = GT[rec]["groundTruth"] + "/" + GT[rec]["attackType"]
            truth[k] = truth.get(k, 0) + 1
        facts["flow"] = {
            "group": {k: grp[k] for k in ("group_ref", "member_count", "first_seen_at", "last_seen_at")},
            "representative": {"operational_alert_ref": rep["operational_alert_ref"],
                               "record_id": members[0] if members else None},
            "alert": {k: al[k] for k in ("alert_ref", "attack_category", "ml_predicted_class", "ml_probability",
                                         "confidence", "signature_severity", "combined_score", "detection_score",
                                         "severity", "evidence_class", "is_critical", "requires_review")},
            "signature_rules": json.loads(al["signature_rules"] or "null"),
            "shap": json.loads(al["shap_attributions"] or "null"),
            "triage": {k: st[k] for k in ("operational_priority", "priority_band", "handling_route",
                                          "workflow_stage", "tier2_recommended", "review_reason")},
            "triageReasons": json.loads(st["tier2_recommendation_reasons"] or "[]"),
            "case": case,
            "groundTruth": truth,
        }
    (OUT / "lanes.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    print("suricata lane:", facts["suricata"]["operationalAlert"]["source_kind"],
          "priority", facts["suricata"]["triage"]["operational_priority"],
          "classification", facts["suricata"]["classification"]["classification"])
    print("flow lane: group", facts["flow"]["group"]["member_count"], "score", facts["flow"]["alert"]["combined_score"],
          facts["flow"]["alert"]["severity"], "route", facts["flow"]["triage"]["handling_route"],
          "case", facts["flow"]["case"]["case_ref"][:8], "truth", facts["flow"]["groundTruth"])
    print("wrote", OUT / "lanes.json")


if __name__ == "__main__":
    main()
