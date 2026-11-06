"""Spike B criterion 4: does an alert built from real packets reach E1 through the approved engine?

Input:  the CICFlowMeter CSVs and the linked Suricata alerts of one capture day (spike_pipeline.sh, link.py).
Steps:  1. CICFlowMeter flows -> the UNCHANGED approved engine (run_detection: rules + XGBoost + fusion + guardrails)
           into a fresh spike database. Every flow gets id `PK-<host>-<n>`.
        2. Join each flow to its linked Suricata alerts (5-tuple + time, link.py).
        3. Report E1 by both decided branches:
             E1-flow-rule  = evidence_class 'corroborated' AND combined_score >= 80      (approved engine)
             E1-suricata   = >= 1 linked Suricata alert of severity 1-2 AND ML predicts an attack AND score >= 80
        4. Ground truth for the spike: the demo sample's labels joined by 5-tuple + start time (where present).

Known gap (recorded): the fork's CSV has no `Total TCP Flow Time` column (the corrected release added it later);
this spike sets it to 0 for every flow. It is 1 of the model's 82 features.

    python spike_detect.py <day> <host-ip> [<host-ip> ...]
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HITL = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
sys.path.insert(0, str(HITL))
sys.path.insert(0, str(Path(__file__).parent))

from link import key, link, load_flows  # noqa: E402
from packages.contracts import models as m  # noqa: E402
from packages.detection.pipeline import store  # noqa: E402
from packages.detection.pipeline.predictor import MODEL_FILE, MODEL_VERSION, XgboostPredictor  # noqa: E402
from packages.detection.pipeline.runner import open_database, run_detection  # noqa: E402
from packages.detection.pipeline.source import Flow, _python  # noqa: E402

import pandas as pd  # noqa: E402

MISSING_FEATURE = "Total TCP Flow Time"


class CicFlowMeterSource:
    """CICFlowMeter fork CSVs as a FlowSource, timestamp order, ids `PK-<host>-<n>`."""

    def __init__(self, paths: list[tuple[str, Path]]):
        self.paths = paths
        self.name = "cicflowmeter:" + ",".join(h for h, _ in paths)

    def flows(self):
        frames = []
        for host, path in self.paths:
            f = pd.read_csv(path, low_memory=False)
            f.insert(0, "alert_id", [f"PK-{host}-{i}" for i in range(len(f))])
            frames.append(f)
        frame = pd.concat(frames, ignore_index=True)
        if MISSING_FEATURE not in frame.columns:
            frame[MISSING_FEATURE] = 0
        frame["_when"] = pd.to_datetime(frame["Timestamp"], format="ISO8601")
        frame = frame.sort_values(["_when", "alert_id"], kind="stable")
        cols = [c for c in frame.columns if c not in ("alert_id", "_when", "Label")]
        for rec in frame.to_dict("records"):
            yield Flow(source_record_id=str(rec["alert_id"]), features={c: _python(rec[c]) for c in cols})


def main() -> None:
    day, hosts = sys.argv[1], sys.argv[2:]
    base = HITL / "data" / "spike" / day
    db = base / "spike.db"
    if db.exists():
        db.unlink()
    paths = [(h, base / "flows" / f"{h}.pcap_Flow.csv") for h in hosts]
    conn = open_database(str(db))
    now = m.utc_now()
    store.register_model(conn, version=MODEL_VERSION, model_file=MODEL_FILE, metrics={}, now=now)
    ds = store.register_dataset(conn, name=f"CSE-CIC-IDS2018 packets {day} via CICFlowMeter fork (spike)",
                                version="spike-b", source_file=",".join(str(p) for _, p in paths),
                                total_records=0, class_distribution={}, preparation_meta={"hosts": hosts}, now=now)
    conn.commit()
    summary = run_detection(conn, CicFlowMeterSource(paths), XgboostPredictor(), dataset_id=ds, now=now)
    print(f"detection: flows={summary.flows:,} alerts={summary.alerts:,} by_evidence={summary.by_evidence}")

    # Suricata alerts per flow (5-tuple + time); keep the worst severity and the signatures.
    sur = defaultdict(lambda: {"n": 0, "sev": 9, "sigs": Counter()})
    linked_total = Counter()
    for host, path in paths:
        index, _ = load_flows(str(path))
        tmp = base / f"linked-{host}.jsonl"
        with tmp.open("w", encoding="utf-8") as out:
            linked_total.update(link(str(base / f"suricata-{host}" / "eve.json"), index, out))
        with tmp.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                a = r["alert"]
                k = (key({"TCP": 6, "UDP": 17}.get(a["proto"], -1), a["src_ip"], a.get("src_port", 0),
                         a["dest_ip"], a.get("dest_port", 0)), r["flow_start"])
                s = sur[k]
                s["n"] += 1
                s["sev"] = min(s["sev"], a["alert"]["severity"])
                s["sigs"][a["alert"]["signature"]] += 1
    print(f"suricata: alerts={linked_total['alerts']:,} linked={linked_total['linked']:,} "
          f"({linked_total['linked'] / max(1, linked_total['alerts']):.4f})")

    # Ground truth from the demo sample (5-tuple + start time to the microsecond).
    truth = {}
    with (HITL / "data/processed/demo_sample.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Timestamp"].startswith(day.split("-")[3] + "-" + day.split("-")[2] + "-" + day.split("-")[1]):
                k = (key(int(r["Protocol"]), r["Src IP"], int(r["Src Port"]), r["Dst IP"], int(r["Dst Port"])), r["Timestamp"])
                truth[k] = (r["alert_id"], r["attack_class"])

    rows = conn.execute("""SELECT f.source_record_id, a.evidence_class, a.combined_score, a.ml_predicted_class,
                                  f.src_ip, f.src_port, f.dst_ip, f.dst_port, f.protocol, f.flow_features
                           FROM alerts a JOIN flow_data f ON f.alert_id = a.id""").fetchall()
    proto_num = {"tcp": 6, "udp": 17, "TCP": 6, "UDP": 17}
    e1_rule = e1_sur = both = 0
    demo_hits, ex = Counter(), {}
    for ref, ev, score, ml, sip, sp, dip, dp, proto, feats in rows:
        ts = json.loads(feats)["Timestamp"]
        k = (key(proto_num.get(proto, json.loads(feats).get("Protocol")), sip, sp, dip, dp), ts)
        s = sur.get(k)
        r1 = ev == "corroborated" and score >= 80
        r2 = bool(s) and s["sev"] <= 2 and ml not in (None, "Benign") and score >= 80
        e1_rule += r1
        e1_sur += r2
        both += r1 and r2
        if k in truth:
            demo_hits[(truth[k][1], ev, "E1" if (r1 or r2) else "-")] += 1
            if truth[k][0] in ("AL-00478",):
                ex[truth[k][0]] = (ev, score, ml, dict(s["sigs"]) if s else None)
        if (r1 or r2) and "e1_example" not in ex:
            ex["e1_example"] = (ref, ev, score, ml, dict(s["sigs"].most_common(2)) if s else None)
    print(f"E1-flow-rule={e1_rule:,}  E1-suricata={e1_sur:,}  both={both:,}")
    print(f"flows matched to the demo sample's labelled rows: {sum(demo_hits.values()):,}")
    for (cls, ev, e1), n in sorted(demo_hits.items()):
        print(f"   truth={cls:<12} evidence={ev:<20} {e1:<3} {n}")
    print("examples:", json.dumps(ex, default=str)[:900])
    conn.close()


if __name__ == "__main__":
    main()
