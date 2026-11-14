"""Measure where the two chains combine, and the family-learning instances, on one whole Packet Replay.

Input   the scratch database of a whole Packet Replay (analysis/phase-f/dual-chain/replay_full.json -> db),
        hitl-ids/data/packet-replay/eve.jsonl, and the product's own family functions
        (packages/detection/feedback/learning.py, packages/detection/suricata_learning.py).
Output  families.json beside this file. Read-only on every input.

    hitl-ids/.venv/Scripts/python.exe analysis/phase-f/workflow-layout/families_data.py
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "hitl-ids"))
from packages.detection import suricata_learning  # noqa: E402
from packages.detection.feedback.learning import learn, parse_family_key  # noqa: E402
from packages.detection.feedback.service import load_learning_policy, load_policy  # noqa: E402
from packages.detection.verdict_bridge import OUTCOME_TO_CATEGORY  # noqa: E402

RUN = json.loads((HERE.parent / "dual-chain" / "replay_full.json").read_text(encoding="utf-8"))
EVE = ROOT / "hitl-ids" / "data" / "packet-replay" / "eve.jsonl"
TIER1 = "t.handling_route='tier1_review' AND t.workflow_stage='triage'"


def main() -> None:
    conn = sqlite3.connect(f"file:{Path(RUN['db']).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    one = lambda sql, *p: conn.execute(sql, p).fetchone()[0]  # noqa: E731

    # ---- 1. packet split: every Suricata alert is linked to the CICFlowMeter record of the same connection
    evidence_by_record = {r[0]: r[1] for r in conn.execute(
        "SELECT f.source_record_id, a.evidence_class FROM flow_data f JOIN alerts a ON a.id=f.alert_id")}
    group_by_record = {r[0]: r[1] for r in conn.execute(
        "SELECT f.source_record_id, gm.group_id FROM alert_group_members gm "
        "JOIN flow_data f ON f.alert_id=gm.legacy_alert_id")}
    eve = [json.loads(line) for line in EVE.open(encoding="utf-8")]
    # One queue item per bundle (same flow_id); its title is the most severe signature (lowest severity number).
    bundle_items: dict = {}
    for item in eve:
        ev = item["event"]
        b = ev.get("flow_id")
        current = bundle_items.get(b)
        if current is None or ev["alert"]["severity"] < current["event"]["alert"]["severity"]:
            bundle_items[b] = {**item, "step": max(item["step"], current["step"]) if current else item["step"]}
        else:
            current["step"] = max(current["step"], item["step"])
    third_step: dict[tuple, int] = {}
    seen: dict[tuple, int] = collections.Counter()
    for item in sorted(bundle_items.values(), key=lambda i: i["step"]):
        ev = item["event"]
        key = suricata_learning.family_of(ev["alert"]["signature"], ev["src_ip"], ev["dest_ip"])
        seen[key] += 1
        if seen[key] == 3:
            third_step[key] = item["step"] + 1
    linked = collections.Counter(evidence_by_record.get(item["linkedRecord"], "missing") for item in eve)
    bundles = collections.Counter(item["event"].get("flow_id") for item in eve)
    per_bundle = collections.Counter(bundles.values())
    groups_touched = collections.Counter(group_by_record[item["linkedRecord"]] for item in eve
                                         if item["linkedRecord"] in group_by_record)

    # ---- 2. compression inside each chain
    groups = [dict(r) for r in conn.execute(
        "SELECT g.id, g.grouping_key, g.member_count, g.first_seen_at, g.last_seen_at, "
        "t.handling_route, t.operational_priority, o.detection_title "
        "FROM alert_groups g JOIN operational_alerts_v2 o ON o.id=g.representative_operational_alert_id "
        "JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id ORDER BY g.member_count DESC")]
    for g in groups:
        g["suricataAlertsOnMembers"] = groups_touched.get(g["id"], 0)

    # ---- 3. one table, one routing audit, one sort (the visible queue: after the cross-chain join)
    visible = "(SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links))"
    by_chain = {r[0]: dict(r) for r in conn.execute(
        "SELECT o.source_kind AS chain, count(*) AS items, "
        "sum(t.handling_route='tier1_review') AS tier1, sum(t.handling_route='tier2_case') AS tier2, "
        "sum(s.operational_alert_id IS NOT NULL) AS routed "
        f"FROM {visible} o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
        "LEFT JOIN operational_system_routing s ON s.operational_alert_id=o.id GROUP BY o.source_kind")}
    raw_by_chain = {r[0]: r[1] for r in conn.execute(
        "SELECT source_kind, count(*) FROM operational_alerts_v2 GROUP BY 1")}
    bands = collections.defaultdict(dict)
    for r in conn.execute(f"SELECT o.source_kind, t.priority_band, count(*) FROM {visible} o "
                          "JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id GROUP BY 1,2"):
        bands[r[0]][r[1] or "none"] = r[2]
    # ---- 3b. the cross-chain join (packages/detection/cross_chain.py)
    join_rows = conn.execute(
        "SELECT l.reason, ts.priority_band AS sb, tf.priority_band AS fb, ts.handling_route AS sr, "
        "tf.handling_route AS fr, (SELECT a.evidence_class FROM alerts a WHERE a.id=l.flow_alert_id) AS ev, "
        "(l.flow_operational_alert_id IN (SELECT representative_operational_alert_id FROM alert_groups)) AS grp "
        "FROM cross_chain_links l "
        "JOIN operational_triage_state_v2 ts ON ts.operational_alert_id=l.suricata_operational_alert_id "
        "JOIN operational_triage_state_v2 tf ON tf.operational_alert_id=l.flow_operational_alert_id").fetchall()
    join_cases = collections.Counter(
        (r["reason"], "flow group" if r["grp"] else f"flow single ({r['ev']})", f"{r['fb']} / {r['fr']}",
         f"{r['sb']} / {r['sr']}") for r in join_rows)
    join = {"links": len(join_rows),
            "distinctFlowItems": one("SELECT count(DISTINCT flow_operational_alert_id) FROM cross_chain_links"),
            "hidden": one("SELECT count(DISTINCT hidden_operational_alert_id) FROM cross_chain_links"),
            "suricataShown": sum(1 for r in join_rows if r["reason"] == "suricata more severe"),
            "flowShown": sum(1 for r in join_rows if r["reason"] != "suricata more severe"),
            "unlinkedSuricata": one("SELECT count(*) FROM operational_alerts_v2 WHERE source_kind='external_nids_alert' "
                                    "AND id NOT IN (SELECT suricata_operational_alert_id FROM cross_chain_links)"),
            "rawItems": one("SELECT count(*) FROM operational_alerts_v2"), "rawByChain": raw_by_chain,
            "visibleItems": one(f"SELECT count(*) FROM {visible}"),
            "cases": [{"shown": k[0], "flowSide": k[1], "flowBandRoute": k[2], "suricataBandRoute": k[3], "links": v}
                      for k, v in join_cases.most_common()]}
    escalation_rules = collections.Counter()
    for (decision,) in conn.execute("SELECT s.routing_decision FROM operational_system_routing s "
                                    "JOIN tier2_cases k ON k.primary_operational_alert_id=s.operational_alert_id"):
        d = json.loads(decision)
        escalation_rules[(d.get("routeClass"), (d.get("reasons") or ["-"])[0][:90])] += 1

    # ---- 4. family learning: Tier 1 items only (a verdict needs a Tier 1 claim)
    flow_rows = conn.execute(
        f"SELECT a.family_key, a.evidence_class, t.operational_priority FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) o "
        f"JOIN alerts a ON a.id=o.legacy_alert_id JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
        f"WHERE {TIER1}").fetchall()
    suri_rows = conn.execute(
        f"SELECT o.detection_title, o.source_ip, o.destination_ip, o.detection_category, o.native_severity, "
        f"t.operational_priority "
        f"FROM (SELECT * FROM operational_alerts_v2 WHERE id NOT IN (SELECT hidden_operational_alert_id FROM cross_chain_links)) o JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id "
        f"WHERE o.source_kind='external_nids_alert' AND {TIER1}").fetchall()

    def summarise(keyed: dict[str, list[float]], describe) -> dict:
        sizes = sorted(((k, v) for k, v in keyed.items()), key=lambda kv: -len(kv[1]))
        quorum = [kv for kv in sizes if len(kv[1]) >= 3]
        return {"items": sum(len(v) for v in keyed.values()), "families": len(keyed),
                "quorumFamilies": len(quorum), "quorumItems": sum(len(v) for _, v in quorum),
                "singletons": sum(1 for v in keyed.values() if len(v) == 1),
                "top": [{**describe(k), "members": len(v), "priorityMin": round(min(v), 2),
                         "priorityMax": round(max(v), 2)} for k, v in sizes[:8]]}

    flow_fam: dict[str, list[float]] = collections.defaultdict(list)
    flagged_fam: dict[str, list[float]] = collections.defaultdict(list)
    for r in flow_rows:
        flow_fam[r["family_key"]].append(r["operational_priority"] or 0)
        if r["evidence_class"] != "none":
            flagged_fam[r["family_key"]].append(r["operational_priority"] or 0)
    suri_fam: dict[tuple, list[float]] = collections.defaultdict(list)
    suri_weight: dict[tuple, float] = {}
    for r in suri_rows:
        key = suricata_learning.family_of(r["detection_title"], r["source_ip"], r["destination_ip"])
        suri_fam[key].append(r["operational_priority"] or 0)
        suri_weight[key] = suricata_learning.weight_of(r["detection_category"], r["native_severity"])

    suri_summary_holder = {}

    def out_suri_top(_fam):
        return suri_summary_holder["suricata"]["top"]

    def flow_describe(key):
        f = parse_family_key(key) or {}
        return {"key": key, "attack": f.get("attack_category"), "port": f.get("dst_port"),
                "protocol": f.get("protocol"), "rule": f.get("rule_id"), "host": f.get("dst_ip")}

    def suri_describe(key):
        title, host = key
        return {"key": key, "signature": title, "internalHost": host}

    suri_summary_holder["suricata"] = summarise(suri_fam, suri_describe)
    guard = {r[0]: r[1] for r in conn.execute("SELECT config_key, config_value FROM guardrail_config")}

    # Predicted, not run: the product's learn() on 3 agreeing false positives, then the critical floor.
    policy, learning = load_policy(conn), load_learning_policy(conn)
    for item in out_suri_top(suri_fam):
        key = (item["signature"], item["internalHost"])
        delta = learn([OUTCOME_TO_CATEGORY["false_positive"]] * 3, suri_weight[key], policy, learning).applied_adjustment
        before = item["priorityMax"]
        after = max(0.0, before + delta)
        if before >= guard["critical_alert_threshold"]:
            after = max(after, guard["critical_alert_floor"])
        item.update(weight=round(suri_weight[key], 2), familyDelta=delta, predictedAfterThreeFP=round(after, 2),
                    thirdMemberStep=third_step.get(key))
    out = {
        "source": {"db": RUN["db"], "steps": len(RUN["steps"]), "eve": str(EVE.relative_to(ROOT))},
        "split": {"suricataAlerts": len(eve), "linkedToFlagged": linked.get("corroborated", 0) + linked.get("ml_only", 0),
                  "linkedByEvidence": dict(linked), "bundles": len(bundles),
                  "alertsPerBundle": {str(k): v for k, v in sorted(per_bundle.items())},
                  "suricataAlertsInFlowGroups": sum(groups_touched.values()),
                  "flowGroupsWithSuricata": len(groups_touched)},
        "compression": {"flowsInWindow": RUN["flowsInWindow"],
                        "flagged": one("SELECT count(*) FROM alerts WHERE evidence_class!='none'"),
                        "unflagged": one("SELECT count(*) FROM alerts WHERE evidence_class='none'"),
                        "groups": groups, "suricataBundlesAdmitted": one("SELECT count(*) FROM external_operational_admission")},
        "queue": {"byChain": by_chain, "bands": bands, "join": join,
                  "unrouted": one("SELECT count(*) FROM operational_alerts_v2 o LEFT JOIN operational_system_routing s "
                                  "ON s.operational_alert_id=o.id WHERE s.operational_alert_id IS NULL"),
                  "tier2ByRule": [{"routeClass": k[0], "reason": k[1], "cases": v} for k, v in escalation_rules.most_common()]},
        "families": {"flow": summarise(flow_fam, flow_describe), "flowFlagged": summarise(flagged_fam, flow_describe),
                     "suricata": suri_summary_holder["suricata"]},
        "guardrails": guard,
        "homeNet": [str(n) for n in suricata_learning._config()[1]],
        "suricataConfig": suricata_learning._config()[0],
    }
    (HERE / "families.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("split",)}, default=str))
    print("bychain", json.dumps(by_chain)); print("tier2", out["queue"]["tier2ByRule"])
    print("join", json.dumps({k: v for k, v in join.items() if k != "cases"}))
    for c in join["cases"]:
        print("   ", c)
    for chain in ("flow", "flowFlagged", "suricata"):
        f = out["families"][chain]
        print(chain, {k: f[k] for k in ("items", "families", "quorumFamilies", "quorumItems", "singletons")})
        for t in f["top"][:5]:
            print("   ", t)
    print("guard", guard)


if __name__ == "__main__":
    main()
