"""Data trace for the dual-chain workflow page: one real record for every unique end result in the queue.

Input   the scratch database of a whole Packet Replay (analysis/phase-f/dual-chain/replay_full.py),
        analysis/phase-f/dual-chain/replay_full.json, hitl-ids/data/packet-replay/eve.jsonl
Output  trace.json beside this file. Read-only on every input.

An end result is one distinct combination of: chain, evidence class, group or single item, classification
status and category, route class, route, workflow stage, priority band, Tier 2 case yes or no.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/workflow-layout/trace_data.py
"""
from __future__ import annotations

import collections
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN = json.loads((HERE.parent / "dual-chain" / "replay_full.json").read_text(encoding="utf-8"))
EVE = ROOT / "hitl-ids" / "data" / "packet-replay" / "eve.jsonl"

QUEUE = """SELECT o.id, o.operational_alert_ref, o.source_kind, o.legacy_alert_id, o.external_inbox_id, o.detection_title,
    o.occurred_at, o.source_ip, o.destination_ip, o.source_port, o.destination_port, o.protocol,
    t.handling_route, t.workflow_stage, t.priority_band, t.operational_priority, t.review_reason, t.tier2_recommended,
    s.classification, s.routing_decision, s.case_ref,
    (SELECT g.id FROM alert_groups g WHERE g.representative_operational_alert_id=o.id) AS group_id,
    (SELECT a.evidence_class FROM alerts a WHERE a.id=o.legacy_alert_id) AS evidence
    FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) o
    JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
    JOIN operational_system_routing s ON s.operational_alert_id=o.id ORDER BY o.id"""


def flow_opinion(conn, record: str | None) -> dict | None:
    """What the flow chain stored for one CICFlowMeter flow record."""
    if record is None:
        return None
    row = conn.execute(
        """SELECT a.id, a.evidence_class, a.attack_category, a.ml_predicted_class, a.ml_probability, a.combined_score,
                  (SELECT g.member_count FROM alert_group_members gm JOIN alert_groups g ON g.id=gm.group_id
                   WHERE gm.legacy_alert_id=a.id) AS group_members
           FROM flow_data f JOIN alerts a ON a.id=f.alert_id WHERE f.source_record_id=?""", (record,)).fetchone()
    if row is None:
        return None
    return {"flowAlertId": row["id"], "evidenceClass": row["evidence_class"], "ruleCategory": row["attack_category"],
            "modelClass": row["ml_predicted_class"], "modelProbability": round(row["ml_probability"], 4),
            "combinedScore": row["combined_score"], "groupMembers": row["group_members"]}


def flow_trace(conn, row, suricata_by_record) -> dict:
    alert = conn.execute("SELECT * FROM alerts WHERE id=?", (row["legacy_alert_id"],)).fetchone()
    flow = conn.execute("SELECT * FROM flow_data WHERE alert_id=?", (alert["id"],)).fetchone()
    rules = [rule.get("rule_id") or rule.get("name") for rule in json.loads(alert["signature_rules"] or "[]")]
    group = None
    if row["group_id"] is not None:
        g = conn.execute("SELECT * FROM alert_groups WHERE id=?", (row["group_id"],)).fetchone()
        linked = sum(1 for (record,) in conn.execute(
            "SELECT f.source_record_id FROM alert_group_members gm JOIN flow_data f ON f.alert_id=gm.legacy_alert_id "
            "WHERE gm.group_id=?", (g["id"],)) if record in suricata_by_record)
        group = {"key": g["grouping_key"], "members": g["member_count"], "firstSeen": g["first_seen_at"],
                 "lastSeen": g["last_seen_at"], "membersWithSuricataAlert": linked}
    return {
        "flow": {"record": flow["source_record_id"], "time": json.loads(flow["flow_features"]).get("Timestamp"),
                 "srcIp": flow["src_ip"], "srcPort": flow["src_port"], "dstIp": flow["dst_ip"],
                 "dstPort": flow["dst_port"], "protocol": flow["protocol"], "packets": flow["packets"],
                 "bytes": flow["bytes"], "durationSeconds": flow["duration"]},
        "detection": {"rules": rules, "ruleCategory": alert["attack_category"], "modelClass": alert["ml_predicted_class"],
                      "modelProbability": round(alert["ml_probability"], 4), "combinedScore": alert["combined_score"],
                      "evidenceClass": alert["evidence_class"]},
        "group": group,
        "otherChain": [{"signature": e["alert"]["signature"], "sid": e["alert"]["signature_id"],
                        "severity": e["alert"]["severity"]} for e in suricata_by_record.get(flow["source_record_id"], [])],
    }


def suricata_trace(conn, row, record_by_tuple) -> dict:
    inbox = conn.execute("SELECT * FROM external_alert_inbox WHERE id=?", (row["external_inbox_id"],)).fetchone()
    review = conn.execute("SELECT r.decision, r.reason, u.username FROM external_eligibility_review r "
                          "JOIN users u ON u.id=r.actor_id WHERE r.external_inbox_id=? ORDER BY r.id DESC LIMIT 1",
                          (inbox["id"],)).fetchone()
    admission = conn.execute("SELECT event_type, created_at FROM external_operational_admission "
                             "WHERE external_inbox_id=?", (inbox["id"],)).fetchone()
    key = (inbox["source_ip"], inbox["source_port"], inbox["destination_ip"], inbox["destination_port"])
    events = record_by_tuple.get(key, [])
    return {
        "eve": {"time": inbox["occurred_at"], "srcIp": inbox["source_ip"], "srcPort": inbox["source_port"],
                "dstIp": inbox["destination_ip"], "dstPort": inbox["destination_port"], "protocol": inbox["protocol"],
                "signature": inbox["detection_title"], "category": inbox["detection_category"],
                "severity": inbox["native_severity"],
                "sids": sorted({e["event"]["alert"]["signature_id"] for e in events}),
                "alertsInBundle": len(events), "flowId": events[0]["event"].get("flow_id") if events else None},
        "staging": {"inboxId": inbox["id"], "decision": inbox["admission_decision"],
                    "policyVersion": inbox["admission_policy_version"], "evidenceClass": inbox["proposed_evidence_class"]},
        "review": {"decision": review["decision"], "reason": review["reason"], "actor": review["username"]},
        "admission": {"event": admission["event_type"], "at": admission["created_at"]},
        "otherChain": flow_opinion(conn, events[0]["linkedRecord"] if events else None),
    }


def main() -> None:
    conn = sqlite3.connect(f"file:{Path(RUN['db']).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    suricata_by_record, record_by_tuple, arrived = collections.defaultdict(list), collections.defaultdict(list), 0
    with EVE.open(encoding="utf-8") as source:
        for item in map(json.loads, source):
            e = item["event"]
            suricata_by_record[item["linkedRecord"]].append(e)
            record_by_tuple[(e["src_ip"], e["src_port"], e["dest_ip"], e["dest_port"])].append(item)
            arrived += 1

    results: dict[tuple, dict] = {}
    for row in conn.execute(QUEUE).fetchall():
        cl, rd = json.loads(row["classification"]), json.loads(row["routing_decision"])
        chain = "flow" if row["source_kind"] == "legacy_flow_alert" else "suricata"
        key = (chain, row["evidence"], row["group_id"] is not None, cl["status"], cl["attackCategory"],
               rd["routeClass"], row["handling_route"], row["workflow_stage"], row["priority_band"],
               row["case_ref"] is not None)
        entry = results.setdefault(key, {"rows": []})
        entry["rows"].append(row)

    out = []
    for key, entry in results.items():
        chain = key[0]
        rows = entry["rows"]
        row = rows[0]
        if chain == "suricata":   # prefer an example whose flow the other chain also flagged
            for candidate in rows:
                trace = suricata_trace(conn, candidate, record_by_tuple)
                other = trace["otherChain"]
                if other and other["evidenceClass"] != "none":
                    row = candidate
                    break
            trace = suricata_trace(conn, row, record_by_tuple)
        else:
            trace = flow_trace(conn, row, suricata_by_record)
        cl, rd = json.loads(row["classification"]), json.loads(row["routing_decision"])
        out.append({
            "chain": chain, "count": len(rows), "operationalId": row["id"], "alertRef": row["operational_alert_ref"],
            "title": row["detection_title"], "evidenceClass": key[1], "isGroup": key[2],
            "classification": {"status": cl["status"], "category": cl["attackCategory"], "reasons": cl["reasons"],
                               "policyVersion": cl["policyVersion"]},
            "routing": {"routeClass": rd["routeClass"], "route": rd["route"], "reasons": rd["reasons"],
                        "policyVersion": rd["policyVersion"]},
            "triage": {"priority": row["operational_priority"], "band": row["priority_band"],
                       "route": row["handling_route"], "stage": row["workflow_stage"],
                       "tier2Recommended": bool(row["tier2_recommended"]), "reason": row["review_reason"]},
            "caseRef": row["case_ref"], "trace": trace,
        })
    out.sort(key=lambda item: (item["chain"] != "flow", item["triage"]["route"] != "tier2_case", -item["count"]))
    for index, item in enumerate(out, 1):
        item["id"] = f"R{index}"

    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    totals = {
        "flowsInWindow": RUN["flowsInWindow"], "steps": len(RUN["steps"]), "replaySeconds": RUN["seconds"],
        "suricataAlertsArrived": arrived, "suricataBundlesAdmitted": one("SELECT count(*) FROM external_operational_admission"),
        "queueItems": one("SELECT count(*) FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links))"),
        "queueItemsBeforeJoin": one("SELECT count(*) FROM operational_alerts_v2"),
        "joinedConnections": one("SELECT count(*) FROM cross_chain_links"),
        "flowQueueItems": one("SELECT count(*) FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) WHERE source_kind='legacy_flow_alert'"),
        "suricataQueueItems": one("SELECT count(*) FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) WHERE source_kind='external_nids_alert'"),
        "flaggedFlows": one("SELECT count(*) FROM alerts WHERE evidence_class!='none'"),
        "unflaggedFlows": one("SELECT count(*) FROM alerts WHERE evidence_class='none'"),
        "groups": one("SELECT count(*) FROM alert_groups"), "groupMembers": one("SELECT count(*) FROM alert_group_members"),
        "tier2Cases": one("SELECT count(*) FROM tier2_cases"),
        "tier2CasesFlow": one("SELECT count(*) FROM tier2_cases k JOIN operational_alerts_v2 o "
                              "ON o.id=k.primary_operational_alert_id WHERE o.source_kind='legacy_flow_alert'"),
        "tier1Items": one("SELECT count(*) FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
                           "WHERE t.handling_route='tier1_review'"),
        "unrouted": one("SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN operational_system_routing s "
                        "ON s.operational_alert_id=o.id WHERE s.operational_alert_id IS NULL"),
    }
    progress = [{k: s[k] for k in ("step", "flows", "queue", "suricataAdmitted", "groups", "groupMembers", "tier2Cases")}
                for s in RUN["steps"] if s["step"] % 10 == 9]
    assert sum(item["count"] for item in out) == totals["queueItems"], "results do not cover the whole queue"
    (HERE / "trace.json").write_text(json.dumps({"totals": totals, "results": out, "progress": progress}, indent=1),
                                     encoding="utf-8")
    print(json.dumps(totals))
    for item in out:
        print(item["id"], item["chain"], item["count"], item["evidenceClass"], "group" if item["isGroup"] else "single",
              item["classification"]["category"], item["routing"]["routeClass"], item["triage"]["band"],
              "| other:", json.dumps(item["trace"]["otherChain"])[:150])


if __name__ == "__main__":
    main()
