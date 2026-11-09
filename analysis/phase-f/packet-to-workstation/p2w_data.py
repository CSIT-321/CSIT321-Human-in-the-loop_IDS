"""Build the two walkthrough databases and record their facts. Product code unchanged.

  suricata  DB #1: copy of data/demo.db WITHOUT flow routing. Real ET SCAN alerts are staged, one is
            reviewed and admitted, so the Suricata lane has a live queue item and a real backlog.
  flow      DB #2: copy of data/demo.db WITH materialize_flow_queue.py. The legacy CICIDS2018 flow lane:
            the 54 flows that the same packets produced, one group, E1 Tier 2 case.

Writes data/lane_suricata.json and data/lane_flow.json. data/demo.db is only copied.
Usage: python p2w_data.py suricata | flow
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
TMP = Path(os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review"))
EVE = ROOT / "data/spike/Wednesday-14-02-2018/suricata-172.31.69.25/eve.json"
SIG = "ET SCAN Potential SSH Scan"
GT = json.loads((ROOT / "data/processed/demo_ground_truth.json").read_text(encoding="utf-8"))


def fresh(path: Path, route: bool) -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(ROOT / "data" / "demo.db", path)
    if route:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "materialize_flow_queue.py"),
                        "--database", str(path)], check=True, cwd=ROOT)


def rows(c, sql, params=()):
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql, params)]


def suricata() -> None:
    target = TMP / "p2w-suri.db"
    fresh(target, route=False)
    # Stage every ET SCAN Potential SSH Scan alert of this capture: a real backlog, not one row.
    window = TMP / "p2w-eve-scan.jsonl"
    kept = []
    with EVE.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"event_type":"alert"' in line and SIG in line:
                e = json.loads(line)
                if e.get("event_type") == "alert" and e["alert"]["signature"] == SIG:
                    kept.append(e)
    window.write_text("\n".join(json.dumps(e) for e in kept) + "\n", encoding="utf-8")
    print(f"staged window: {len(kept)} alerts of {SIG}")

    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_suricata_eve.py"),
                          "--input", str(window), "--sensor-id", "p2w-sensor",
                          "--capture-scope", "p2w-capture-1", "--database", str(target)],
                         capture_output=True, text=True, cwd=ROOT)
    if run.returncode != 0:
        raise SystemExit(run.stdout + run.stderr)
    imported = json.loads(run.stdout)

    packets_alert = json.loads((OUT / "suricata_alert.json").read_text(encoding="utf-8"))["alert"]
    with db.connect(target) as c:
        actor = c.execute("SELECT id, display_name, role FROM users WHERE username='g.ang'").fetchone()
        mine = rows(c, """SELECT i.id, i.detection_title, i.native_severity, i.proposed_operational_priority,
                                 i.source_ip, i.destination_ip, i.destination_port, i.occurred_at,
                                 i.admission_decision, i.import_status
                          FROM external_alert_inbox i WHERE i.occurred_at LIKE ?""",
                     (packets_alert["timestamp"][:19] + "%",))
        if not mine:
            mine = rows(c, "SELECT * FROM external_alert_inbox ORDER BY id LIMIT 1")
        target_row = mine[0]
        review = review_eligibility(c, target_row["id"], actor_id=actor[0],
                                    request=EligibilityRequest(request_id=uuid4(), expected_review_id=None,
                                                               reason="Packet evidence checked: 7 SYNs to port 22 from 7 source "
                                                                      "ports within 1572 microseconds.",
                                                               decision="accepted"))
        adm, replayed = admit_external(c, target_row["id"], actor_id=actor[0],
                                       request=AdmissionRequest(request_id=uuid4(),
                                                                expected_review_id=review["id"],
                                                                reason="Admit for analyst triage."))
        op = rows(c, """SELECT * FROM operational_alerts_v2 o
                        JOIN external_operational_admission a ON a.operational_alert_id=o.id
                        WHERE a.external_inbox_id=?""", (target_row["id"],))[0]
        st = rows(c, "SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?", (op["id"],))[0]
        cls = rows(c, "SELECT * FROM operational_system_routing WHERE operational_alert_id=?", (op["id"],))[0]
        counts = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in
                  ("suricata_eve_records", "external_alert_inbox", "external_eligibility_review",
                   "external_operational_admission", "operational_alerts_v2")}
        payload = {
            "db": str(target), "import": imported, "stagedAlerts": len(kept),
            "counts": counts,
            "actor": {"id": actor[0], "name": actor[1], "role": actor[2]},
            "targetInbox": target_row, "review": review, "admission": adm, "replayed": replayed,
            "queue": {k: op[k] for k in ("operational_alert_ref", "source_kind", "detector_source",
                                         "detection_title", "detection_category", "native_severity",
                                         "occurred_at", "source_ip", "destination_ip", "destination_port",
                                         "protocol", "external_inbox_id")},
            "triage": {k: st[k] for k in ("operational_priority", "priority_band", "handling_route",
                                          "workflow_stage", "review_required", "decision_source",
                                          "triage_policy_version")},
            "classification": {"value": json.loads(cls["classification"]),
                               "policy": json.loads(cls["classification_policy"])["version"],
                               "routing_decision": cls["routing_decision"],
                               "routing_policy": cls["routing_policy"]},
            "inboxBacklog": rows(c, """SELECT id, detection_title, native_severity, admission_decision,
                                              import_status, source_ip, destination_ip, occurred_at
                                       FROM external_alert_inbox ORDER BY id LIMIT 8"""),
        }
        (OUT / "lane_suricata.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print("suricata lane: queue ref", payload["queue"]["operational_alert_ref"][:8],
              "priority", payload["triage"]["operational_priority"],
              "class", payload["classification"]["value"],
              "| inbox", counts["external_alert_inbox"], "admitted", counts["external_operational_admission"])


def flow() -> None:
    target = TMP / "p2w-flow.db"
    fresh(target, route=True)
    with db.connect(target) as c:
        grp = rows(c, """SELECT g.* FROM alert_groups g WHERE g.grouping_key='13.58.98.64'
                         ORDER BY g.member_count DESC LIMIT 1""")[0]
        rep_op = grp["representative_operational_alert_id"]
        rep = rows(c, "SELECT * FROM operational_alerts_v2 WHERE id=?", (rep_op,))[0]
        al = rows(c, "SELECT * FROM alerts WHERE id=?", (rep["legacy_alert_id"],))[0]
        st = rows(c, "SELECT * FROM operational_triage_state_v2 WHERE operational_alert_id=?", (rep_op,))[0]
        case = rows(c, """SELECT t.case_ref, t.decision_source, t.created_by_actor_id, s.status, s.revision
                          FROM tier2_cases t JOIN tier2_case_state s ON s.case_id=t.id
                          WHERE t.primary_operational_alert_id=?""", (rep_op,))
        members = [r["source_record_id"] for r in rows(c, """SELECT f.source_record_id FROM alert_group_members m
                    JOIN flow_data f ON f.alert_id=m.legacy_alert_id WHERE m.group_id=? ORDER BY m.occurred_at""",
                    (grp["id"],))]
        truth = {}
        for rec in members:
            k = GT[rec]["groundTruth"] + "/" + GT[rec]["attackType"]
            truth[k] = truth.get(k, 0) + 1
        payload = {
            "db": str(target),
            "group": {k: grp[k] for k in ("group_ref", "grouping_key", "member_count",
                                          "first_seen_at", "last_seen_at")},
            "representative": {"operational_alert_ref": rep["operational_alert_ref"],
                               "alert_ref": al["alert_ref"], "record_id": members[0], "members": members},
            "alert": {k: al[k] for k in ("attack_category", "ml_predicted_class", "ml_probability", "confidence",
                                         "signature_severity", "combined_score", "detection_score", "severity",
                                         "evidence_class", "is_critical")},
            "signatureRules": json.loads(al["signature_rules"] or "null"),
            "shap": json.loads(al["shap_attributions"] or "null"),
            "triage": {k: st[k] for k in ("operational_priority", "priority_band", "handling_route",
                                          "workflow_stage", "tier2_recommended", "review_reason")},
            "case": case[0] if case else None,
            "groundTruth": truth,
        }
        (OUT / "lane_flow.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print("flow lane: group", payload["group"]["member_count"], "score", payload["alert"]["combined_score"],
              payload["alert"]["severity"], "route", payload["triage"]["handling_route"],
              "case", payload["case"]["case_ref"][:8] if payload["case"] else None, "truth", truth)


if __name__ == "__main__":
    {"suricata": suricata, "flow": flow}[sys.argv[1]]()
