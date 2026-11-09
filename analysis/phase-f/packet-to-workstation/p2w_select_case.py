"""Summary of the Suricata -> flow matches: which signature, how many flows, ground truth, routing.
Read-only.
"""
import collections
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

BASE = r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids"
EVE = os.path.join(BASE, "data/spike/Wednesday-14-02-2018/suricata-172.31.69.25/eve.json")
DB = os.path.expandvars(r"%LOCALAPPDATA%\Temp\hitl-review\selftest.db")
GT = json.loads(open(os.path.join(BASE, "data/processed/demo_ground_truth.json"), encoding="utf-8").read())

alerts = []
with open(EVE, encoding="utf-8", errors="replace") as f:
    for line in f:
        if '"event_type":"alert"' not in line:
            continue
        e = json.loads(line)
        if e.get("event_type") != "alert":
            continue
        alerts.append((datetime.fromisoformat(e["timestamp"].replace("+0800", "+08:00")).astimezone(timezone.utc),
                       e.get("src_ip"), e.get("dest_ip"), e.get("dest_port"), e["alert"]["signature"],
                       e["alert"]["signature_id"], e["alert"]["severity"], e.get("proto")))

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
rows = []
for ts, src, dst, dport, sig, sid, sev, proto in alerts:
    lo = (ts - timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    hi = (ts + timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    for r in c.execute("""SELECT f.source_record_id, f.src_ip, f.dst_ip, f.dst_port, f.src_port,
                                 json_extract(f.flow_features,'$.Timestamp') ts,
                                 a.attack_category, a.combined_score, a.severity, a.evidence_class,
                                 g.id AS group_id, g.member_count, t.handling_route, t.tier2_recommended
                          FROM flow_data f JOIN alerts a ON a.id=f.alert_id
                          LEFT JOIN alert_group_members m ON m.legacy_alert_id=a.id
                          LEFT JOIN alert_groups g ON g.id=m.group_id
                          LEFT JOIN operational_alerts_v2 o ON o.legacy_alert_id=a.id
                          LEFT JOIN operational_triage_state_v2 t ON t.operational_alert_id=o.id
                          WHERE f.src_ip=? AND f.dst_ip=? AND f.dst_port=?
                            AND json_extract(f.flow_features,'$.Timestamp') BETWEEN ? AND ?""",
                         (src, dst, dport, lo, hi)):
        rows.append((sig, sid, sev, dict(r)))

print("matches:", len(rows))
by_sig = collections.defaultdict(list)
for sig, sid, sev, r in rows:
    by_sig[(sig, sid, sev)].append(r)
for (sig, sid, sev), rs in sorted(by_sig.items(), key=lambda kv: -len(kv[1])):
    gt = collections.Counter(GT[r["source_record_id"]]["groundTruth"] + "/" + GT[r["source_record_id"]]["attackType"]
                             for r in rs)
    routes = collections.Counter(r["handling_route"] for r in rs)
    groups = collections.Counter((r["group_id"], r["member_count"]) for r in rs)
    cats = collections.Counter(r["attack_category"] for r in rs)
    print(f"\n{sig}  (sid {sid}, native severity {sev})")
    print(f"  flows {len(rs)} | classes {dict(cats)} | truth {dict(gt)}")
    print(f"  routes {dict(routes)} | groups {dict(groups)}")
    print(f"  example: {rs[0]['source_record_id']} {rs[0]['ts']} {rs[0]['src_ip']}->{rs[0]['dst_ip']}:{rs[0]['dst_port']} "
          f"score {rs[0]['combined_score']} {rs[0]['severity']} {rs[0]['evidence_class']}")
