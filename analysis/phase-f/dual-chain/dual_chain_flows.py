#!/usr/bin/env python
"""Read-only flow-level cross table for one capture day.

Axes per flow: our detector (evidence_class) x Suricata (actionable vs
informational) x ground-truth label.  Nothing is written except the JSON
output next to this script; all inputs are opened read-only.
"""
import csv
import json
import os
import sqlite3
import time
from collections import Counter

BASE = (r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS"
        r"\hitl-ids\data\spike\Wednesday-14-02-2018")
DB = os.path.join(BASE, "spike.db")
TRUTH = os.path.join(BASE, "truth-Wednesday-14-02-2018.csv")
LINKED = [os.path.join(BASE, "linked-%s.jsonl" % ip)
          for ip in ("172.31.64.80", "172.31.65.56", "172.31.69.25")]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dual_chain_flows.json")

EXPECT_FLOWS = 362143
EXPECT_EVIDENCE = {"corroborated": 287591, "ml_only": 44, "none": 74504,
                   "signature_override": 4}
INFO_PREFIXES = ("ET INFO", "GPL ")


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def norm_ts(ts):
    """Strip trailing zeros from fractional seconds so near-identical
    timestamp spellings compare equal.  Identity for well-formed values."""
    if not isinstance(ts, str):
        return ts
    s = ts.strip()
    if "." in s:
        head, frac = s.split(".", 1)
        frac = frac.rstrip("0")
        return head + "." + frac if frac else head
    return s


def load_truth():
    """Timestamp+5-tuple -> raw label string ('BENIGN' or an attack name)."""
    labels = {}
    rows = 0
    t0 = time.time()
    with open(TRUTH, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            labels[(str(row["Protocol"]).strip(), row["Src IP"].strip(),
                    str(row["Src Port"]).strip(), row["Dst IP"].strip(),
                    str(row["Dst Port"]).strip(),
                    row["Timestamp"].strip())] = row["Label"].strip()
    log("truth rows=%d distinct=%d (%.0fs)" % (rows, len(labels), time.time() - t0))
    return labels


QUERY = ("SELECT a.evidence_class, a.ml_predicted_class, a.combined_score, "
         "f.flow_features FROM alerts a JOIN flow_data f ON f.alert_id = a.id")


def load_flows(truth):
    """One pass over spike.db.  Returns parallel lists: flow key, ours, label."""
    conn = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    cur = conn.cursor()
    keys, ours, labels = [], [], []
    evidence = Counter()
    n = 0
    t0 = time.time()
    for ev, _ml, _score, feats in cur.execute(QUERY):
        d = json.loads(feats)
        src, dst = d["Src IP"], d["Dst IP"]
        sp, dp, pr = d["Src Port"], d["Dst Port"], d["Protocol"]
        ts = d["Timestamp"]
        keys.append(("%s-%s-%s-%s-%s" % (src, dst, sp, dp, pr), ts))
        ours.append(ev)
        labels.append(truth.get((str(pr), src, str(sp), dst, str(dp), ts)))
        evidence[ev] += 1
        n += 1
        if n % 100000 == 0:
            log("  db rows %d (%.0fs)" % (n, time.time() - t0))
    conn.close()
    log("db rows=%d (%.0fs) evidence=%s" % (n, time.time() - t0, dict(evidence)))
    return keys, ours, labels, evidence


def load_linked():
    """Every linked line -> (raw key, signature list).  Raw keys are kept so the
    exact-match rate can be measured before any normalisation is applied."""
    line_keys, sigs = [], {}
    t0 = time.time()
    for path in LINKED:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                key = (obj["flow_id"], obj["flow_start"])
                line_keys.append(key)
                sig = (obj.get("alert") or {}).get("alert", {}).get("signature")
                if sig:
                    sigs.setdefault(key, []).append(sig)
    log("linked lines=%d distinct_keys=%d (%.0fs)"
        % (len(line_keys), len(sigs), time.time() - t0))
    return line_keys, sigs


def attach_suricata(line_keys, sigs, flow_keys):
    """Measure the exact join rate first, fall back to normalised timestamps
    only if it is below 95%.  Returns: flow_key -> signatures (timestamp part
    keyed by the chosen normaliser), matched line count, strategy name, and the
    timestamp normaliser the caller must apply to flow keys."""
    identity = lambda x: x
    fk_set = set(flow_keys)
    exact = sum(1 for k in line_keys if k in fk_set)
    rate_ex = exact / len(line_keys) if line_keys else 0.0
    if rate_ex >= 0.95:
        del fk_set
        log("linked matched exactly=%d/%d (%.2f%%) -> using exact keys"
            % (exact, len(line_keys), 100.0 * rate_ex))
        return sigs, exact, "exact", identity

    norm_set = {(f, norm_ts(t)) for f, t in fk_set}
    del fk_set
    norm = sum(1 for f, t in line_keys if (f, norm_ts(t)) in norm_set)
    del norm_set
    table = {}
    for (f, t), v in sigs.items():
        table.setdefault((f, norm_ts(t)), []).extend(v)
    log("linked: exact=%d (%.2f%%) below 95%%; normalised=%d (%.2f%%) -> using "
        "normalised_timestamps" % (exact, 100.0 * rate_ex, norm,
                                   100.0 * norm / len(line_keys)))
    return table, norm, "normalised_timestamps", norm_ts


def build(flow_keys, ours, labels, suri, keynorm):
    cross, attack_by, benign_by = Counter(), Counter(), Counter()
    so_attack, oo_attack, so_benign_sigs = Counter(), Counter(), Counter()
    attack_total = 0
    for i, fk in enumerate(flow_keys):
        ev = ours[i]
        raw = labels[i]
        if raw is None:
            ax = "unlabelled"
        elif raw == "BENIGN":
            ax = "benign"
        else:
            ax = "attack"
            attack_total += 1

        sigs = suri.get((fk[0], keynorm(fk[1])))
        if not sigs:
            sur, act = "none", []
        else:
            act = [s for s in sigs
                   if not s.startswith(INFO_PREFIXES[0]) and not s.startswith(INFO_PREFIXES[1])]
            sur = "actionable" if act else "info_only"

        cross[(ev, sur, ax)] += 1
        mine = ev != "none"
        theirs = sur == "actionable"

        if ax == "attack":
            if mine and theirs:
                attack_by["both"] += 1
            elif mine:
                attack_by["ours_only"] += 1
            elif theirs:
                attack_by["suricata_actionable_only"] += 1
                so_attack[raw] += 1
            else:
                attack_by["neither"] += 1
            if mine and not theirs:
                oo_attack[raw] += 1
        elif ax == "benign":
            if mine and theirs:
                benign_by["both"] += 1
            elif mine:
                benign_by["ours_only"] += 1
            elif theirs:
                benign_by["suricata_actionable_only"] += 1
                for s in set(act):
                    so_benign_sigs[s] += 1
    return (cross, attack_by, benign_by, so_attack, oo_attack,
            so_benign_sigs, attack_total)


def main():
    t0 = time.time()
    truth = load_truth()
    flow_keys, ours, labels, evidence = load_flows(truth)
    del truth
    line_keys, sigs = load_linked()
    n_linked = len(line_keys)
    suri, matched, strategy, keynorm = attach_suricata(line_keys, sigs, flow_keys)
    del sigs, line_keys

    (cross, attack_by, benign_by, so_attack, oo_attack,
     so_benign_sigs, attack_total) = build(flow_keys, ours, labels, suri, keynorm)

    flows = len(flow_keys)
    with_label = sum(1 for v in labels if v is not None)
    result = {
        "flows": flows,
        "linked_lines": n_linked,
        "linked_lines_matched_to_flow": matched,
        "flows_with_label": with_label,
        "cross": [{"ours": k[0], "suricata": k[1], "label": k[2], "flows": v}
                  for k, v in sorted(cross.items(), key=lambda kv: -kv[1])],
        "attack_flows_total": attack_total,
        "attack_by": {k: attack_by.get(k, 0) for k in
                      ("both", "ours_only", "suricata_actionable_only", "neither")},
        "benign_flagged_by": {k: benign_by.get(k, 0) for k in
                              ("both", "ours_only", "suricata_actionable_only")},
        "suricata_only_attack_labels": dict(so_attack.most_common()),
        "ours_only_attack_labels": dict(oo_attack.most_common()),
        "suricata_only_benign_top_signatures": [[s, v] for s, v in
                                                so_benign_sigs.most_common(10)],
    }
    return result, evidence, strategy, time.time() - t0


def report(result, evidence, strategy):
    """Self-checks and human-readable table."""
    failed = []
    flows = result["flows"]
    cross_total = sum(r["flows"] for r in result["cross"])
    checks = [
        ("flows == %d" % EXPECT_FLOWS, flows == EXPECT_FLOWS, flows),
        ("sum(cross) == flows", cross_total == flows,
         "%d vs %d" % (cross_total, flows)),
    ]
    for name, want in EXPECT_EVIDENCE.items():
        got = evidence.get(name, 0)
        checks.append(("evidence[%s] == %d" % (name, want), got == want, got))
    for label, ok, detail in checks:
        print("  %-42s %s (%s)" % (label, "PASS" if ok else "FAIL", detail), flush=True)
        if not ok:
            failed.append("%s -> %s" % (label, detail))

    print("\n  ours          suricata    label        flows", flush=True)
    for r in result["cross"]:
        print("  %-13s %-11s %-11s %7d"
              % (r["ours"], r["suricata"], r["label"], r["flows"]), flush=True)

    print("\n  attack_by        %s" % result["attack_by"], flush=True)
    print("  benign_flagged_by %s" % result["benign_flagged_by"], flush=True)
    print("  attack_flows_total %d" % result["attack_flows_total"], flush=True)
    print("  suricata_only_attack_labels %s" % result["suricata_only_attack_labels"], flush=True)
    print("  ours_only_attack_labels %s" % result["ours_only_attack_labels"], flush=True)
    print("  linked_lines %d matched %d (%.2f%%) via %s"
          % (result["linked_lines"], result["linked_lines_matched_to_flow"],
             100.0 * result["linked_lines_matched_to_flow"] / max(1, result["linked_lines"]),
             strategy), flush=True)
    print("  flows_with_label %d" % result["flows_with_label"], flush=True)
    return failed


def run():
    result, evidence, strategy, secs = main()
    failed = report(result, evidence, strategy)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=False)
    log("wrote %s (%.0fs total)" % (OUT, secs))
    if failed:
        log("ASSERTION FAILURES: %s" % "; ".join(failed))
        raise SystemExit(1)
    log("all self-checks passed")


if __name__ == "__main__":
    run()
