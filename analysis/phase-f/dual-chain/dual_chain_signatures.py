"""Read-only per-signature table for one capture day (Wednesday 14-02-2018).

Joins Suricata alerts (linked-*.jsonl) to:
  * our flow detector result (spike.db alerts.evidence_class / ml_predicted_class)
  * the ground-truth label (truth-*.csv Label)
via the flow key (SrcIP-DstIP-SrcPort-DstPort-Protocol, Timestamp).

Writes dual_chain_signatures.json. Creates no other files, edits nothing.
"""
import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict

BASE = (r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP"
        r"\CSIT321-Human-in-the-loop_IDS\hitl-ids\data\spike"
        r"\Wednesday-14-02-2018")
OUT = (r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP"
       r"\CSIT321-Human-in-the-loop_IDS\analysis\phase-f\dual-chain"
       r"\dual_chain_signatures.json")
DB = os.path.join(BASE, "spike.db")
TRUTH = os.path.join(BASE, "truth-Wednesday-14-02-2018.csv")
LINKED = [os.path.join(BASE, f"linked-{ip}.jsonl")
          for ip in ("172.31.64.80", "172.31.65.56", "172.31.69.25")]

EXPECTED_FLOWS = 362143
EXPECTED_LINKED = 76417


def norm_ts(ts):
    """Strip trailing zeros in the fractional part so 12:00:00.100000 == 12:00:00.1"""
    ts = str(ts).strip()
    if "." not in ts:
        return ts
    head, frac = ts.split(".", 1)
    frac = frac.rstrip("0")
    return f"{head}.{frac}" if frac else head


def load_flows():
    """fk -> [evidence_class, ml_predicted_class, index]; also the field list."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    flows = {}
    sql = ("SELECT a.evidence_class, a.ml_predicted_class, f.flow_features "
           "FROM alerts a JOIN flow_data f ON f.alert_id = a.id")
    n = 0
    for ev, ml, feat in con.execute(sql):
        d = json.loads(feat)
        fk = (f"{d['Src IP']}-{d['Dst IP']}-{d['Src Port']}-{d['Dst Port']}"
              f"-{d['Protocol']}", str(d["Timestamp"]))
        # composite truth key carries the same fields, so keep them together
        tkey = (str(d["Protocol"]), str(d["Src IP"]), str(d["Src Port"]),
                str(d["Dst IP"]), str(d["Dst Port"]), str(d["Timestamp"]))
        flows[fk] = [ev, ml, tkey]
        n += 1
    con.close()
    print(f"[load] flows loaded: {n}")
    return flows, n


def load_truth():
    """(Protocol, SrcIP, SrcPort, DstIP, DstPort, Timestamp) -> 'BENIGN' | <attack name>."""
    truth = {}
    with open(TRUTH, "r", encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            key = (str(row["Protocol"]).strip(), str(row["Src IP"]).strip(),
                   str(row["Src Port"]).strip(), str(row["Dst IP"]).strip(),
                   str(row["Dst Port"]).strip(), str(row["Timestamp"]).strip())
            truth[key] = row["Label"]
    print(f"[load] truth rows: {len(truth)}")
    return truth


def load_linked(flow_keys, norm_map):
    """Aggregate linked Suricata alerts per signature.

    flow_keys: set of exact (flow_id, timestamp) keys present in spike.db
    norm_map:  {(flow_id, timestamp-with-trailing-zeros-stripped): real key}
    Returns (rows_state, total_lines, matched_lines, stamp_stats).
    """
    state = {}          # signature -> dict
    total = 0
    matched = 0
    exact = 0
    via_norm = 0
    unmatched = 0
    for path in LINKED:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                total += 1
                al = rec["alert"].get("alert", {})
                sig = al.get("signature") or "<unknown>"
                st = state.get(sig)
                if st is None:
                    st = state[sig] = {
                        "alerts": 0,
                        "matched": 0,
                        "flows": set(),
                        "sev": Counter(),
                        "cat": Counter(),
                    }
                st["alerts"] += 1
                st["sev"][al.get("severity")] += 1
                st["cat"][al.get("category")] += 1

                fk = (rec.get("flow_id"), str(rec.get("flow_start")))
                if fk in flow_keys:
                    exact += 1
                else:
                    real = norm_map.get((fk[0], norm_ts(fk[1])))
                    if real is None:
                        unmatched += 1
                        continue
                    fk = real
                    via_norm += 1
                matched += 1
                st["matched"] += 1
                st["flows"].add(fk)      # always a real spike.db key
    stats = {"exact": exact, "via_norm": via_norm, "unmatched": unmatched}
    print(f"[load] linked lines: {total}  matched: {matched}  {stats}")
    return state, total, matched, stats


def label_of(flows, truth, fk, miss):
    """'attack' | 'benign' | 'unlabelled' plus the raw label name (or None)."""
    name = truth.get(flows[fk][2])
    if name is None:
        miss.add(fk)
        return "unlabelled", None
    return ("benign", name) if name == "BENIGN" else ("attack", name)


def build_rows(state, flows, truth, miss):
    rows = []
    group_flows = {True: set(), False: set()}
    for sig, st in state.items():
        info = sig.startswith("ET INFO") or sig.startswith("GPL ")
        ours = Counter()
        model = Counter()
        lab = Counter()
        names = Counter()
        for fk in st["flows"]:
            ev, ml, _ = flows[fk]
            ours[ev] += 1
            model[ml] += 1
            kind, name = label_of(flows, truth, fk, miss)
            lab[kind] += 1
            if name is not None and kind == "attack":
                names[name] += 1
        group_flows[info] |= st["flows"]
        rows.append({
            "signature": sig,
            "informational": bool(info),
            "native_severity": st["sev"].most_common(1)[0][0] if st["sev"] else None,
            "category": st["cat"].most_common(1)[0][0] if st["cat"] else None,
            "alerts": st["alerts"],
            "matched_alerts": st["matched"],
            "distinct_flows": len(st["flows"]),
            "ours": {k: ours.get(k, 0) for k in
                     ("corroborated", "ml_only", "signature_override", "none")},
            "model_class": dict(model),
            "label": {"attack": lab.get("attack", 0),
                      "benign": lab.get("benign", 0),
                      "unlabelled": lab.get("unlabelled", 0)},
            "attack_labels": dict(names),
        })
    rows.sort(key=lambda r: (-r["alerts"], r["signature"]))
    return rows, group_flows


def totals_for(rows, group_flows, flows, truth, miss, info):
    sel = [r for r in rows if r["informational"] is info]
    fks = group_flows[info]
    kind = Counter()
    flagged = 0
    for fk in fks:
        kind[label_of(flows, truth, fk, miss)[0]] += 1
        if flows[fk][0] != "none":
            flagged += 1
    return {
        "alerts": sum(r["alerts"] for r in sel),
        "distinct_flows": len(fks),
        "flows_attack": kind.get("attack", 0),
        "flows_benign": kind.get("benign", 0),
        "flows_unlabelled": kind.get("unlabelled", 0),
        "flows_also_flagged_by_ours": flagged,
        "flows_not_flagged_by_ours": len(fks) - flagged,
    }


FAILURES = []


def check(name, ok, detail=""):
    print(f"[check] {'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        FAILURES.append(name)


def main():
    flows, n_flows = load_flows()
    check("flows loaded == 362143", n_flows == EXPECTED_FLOWS, f"got {n_flows}")

    flow_keys = set(flows)
    norm_map = {(fid, norm_ts(ts)): (fid, ts) for (fid, ts) in flows}

    truth = load_truth()
    hit = sum(1 for fk in flows if flows[fk][2] in truth)
    print(f"[load] flows with truth label: {hit} / {n_flows}")

    state, total, matched, stats = load_linked(flow_keys, norm_map)
    check("linked_lines == 76417", total == EXPECTED_LINKED, f"got {total}")
    pct = 100.0 * matched / total if total else 0.0
    print(f"[join] linked lines matched to a flow: {matched} ({pct:.2f}%)")
    if pct < 95.0:
        print("[warn] match rate below 95% - see stamp stats: "
              + json.dumps(stats))

    miss = set()
    rows, group_flows = build_rows(state, flows, truth, miss)
    totals = {("informational" if k else "actionable"):
              totals_for(rows, group_flows, flows, truth, miss, k)
              for k in (False, True)}

    out = {
        "linked_lines": total,
        "linked_lines_matched_to_flow": matched,
        "signatures": len(rows),
        "rows": rows,
        "totals": {"actionable": totals["actionable"],
                   "informational": totals["informational"]},
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=False)
    print(f"[write] {OUT}")

    sum_alerts = sum(r["alerts"] for r in rows)
    check("sum(rows.alerts) == 76417", sum_alerts == total, f"got {sum_alerts}")
    check("distinct signatures > 0", len(rows) > 0, f"got {len(rows)}")
    check("totals alerts add up",
          totals["actionable"]["alerts"] + totals["informational"]["alerts"] == total)
    if FAILURES:
        raise AssertionError(f"failed checks: {FAILURES}")

    print("\n[top] actionable signatures by alert count")
    shown = 0
    for r in rows:
        if r["informational"] or shown >= 8:
            continue
        ours_flag = r["distinct_flows"] - r["ours"]["none"]
        print(f"{r['signature'][:70]:70s} | {r['alerts']:6d} | "
              f"{r['distinct_flows']:5d} | {r['label']['attack']}/{r['label']['benign']}"
              f" | ours={ours_flag}")
        shown += 1


if __name__ == "__main__":
    main()


