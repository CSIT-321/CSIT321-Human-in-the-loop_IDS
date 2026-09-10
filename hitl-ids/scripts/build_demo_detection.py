"""
Build the demo detection inputs and re-measure the key findings on the CORRECTED dataset.

Notebooks 01-03 established their findings on the old, uncorrected 1,000-row sample. This script
regenerates the equivalent inputs from `demo_sample.csv` and re-tests the three claims that drive
the project's direction:

    C1  signature engine precision / recall
    C2  the retuned SSH threshold (min 10 -> 20) still gives precision 1.000
    C3  signature+ML co-occurrence is still zero  (if it is not, the CEF design needs revisiting)

Detection inputs are the 17 observable flow fields only. Ground truth is joined AFTER prediction,
for evaluation exclusively. `Attempted Category` is label metadata and never reaches a detector.

Outputs (hitl-ids/data/processed/):
    demo_detection_input.csv    17 observable fields, the detectors' only legal input
    demo_ground_truth.json      labels, for evaluation only
    demo_ml_predictions.json    8-class model output per alert
    corrected_findings.json     C1/C2/C3 re-measured
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROC = HERE.parent / "data" / "processed"
MODELS = HERE.parent / "models"
FIX = HERE.parent / "tests" / "fixtures" / "legacy"

# corrected-release column -> the rule engine's observable field name
OBSERVABLE = {
    "Dst Port": "destinationPort", "Protocol": "protocol",
    "Flow Duration": "flowDuration", "Total Fwd Packet": "totalFwdPackets",
    "Total Bwd packets": "totalBwdPackets", "Flow Bytes/s": "flowBytesPerSecond",
    "Flow Packets/s": "flowPacketsPerSecond", "Packet Length Mean": "packetLengthMean",
    "Fwd Packet Length Mean": "fwdPacketLengthMean", "SYN Flag Count": "synFlagCount",
    "ACK Flag Count": "ackFlagCount", "FIN Flag Count": "finFlagCount",
    "RST Flag Count": "rstFlagCount", "Src IP": "sourceIp", "Dst IP": "destinationIp",
    "Timestamp": "timestamp",
}
PROTO = {6: "TCP", 17: "UDP", 1: "ICMP", 0: "HOPOPT"}


def clause(df, field, spec):
    col = df[field]
    if isinstance(spec, dict):
        if "oneOf" in spec:
            return col.isin(spec["oneOf"])
        m = pd.Series(True, index=df.index)
        if "min" in spec:
            m &= col >= spec["min"]
        if "max" in spec:
            m &= col <= spec["max"]
        return m
    return col == spec


def rule_mask(df, rule):
    m = pd.Series(True, index=df.index)
    for f, s in rule["condition"].items():
        m &= clause(df, f, s)
    return m


def main() -> int:
    src = PROC / "demo_sample.csv"
    if not src.exists():
        print(f"missing {src} - run build_samples.py first", file=sys.stderr)
        return 2

    df = pd.read_csv(src, low_memory=False)
    print(f"demo sample: {len(df):,} rows")

    det = pd.DataFrame({"id": df["alert_id"]})
    for src_col, dst_col in OBSERVABLE.items():
        if src_col not in df.columns:
            print(f"MISSING observable column {src_col!r}", file=sys.stderr)
            return 3
        det[dst_col] = df[src_col]
    det["protocol"] = pd.to_numeric(det["protocol"], errors="coerce").map(PROTO).fillna("OTHER")
    for c in det.columns:
        if c not in ("id", "protocol", "sourceIp", "destinationIp", "timestamp"):
            det[c] = (pd.to_numeric(det[c], errors="coerce")
                        .replace([np.inf, -np.inf], np.nan).fillna(0))
    det.to_csv(PROC / "demo_detection_input.csv", index=False)
    print(f"wrote demo_detection_input.csv  ({len(det.columns)} observable fields)")

    truth = {r.alert_id: {"attackType": r.attack_class,
                          "isAttempted": bool(r.is_attempted),
                          "groundTruth": "benign" if r.attack_class == "Benign" else "malicious"}
             for r in df.itertuples()}
    (PROC / "demo_ground_truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")

    rules_raw = json.load(open(FIX / "flow-signatures.json", encoding="utf-8"))
    RULES = (rules_raw if isinstance(rules_raw, list)
             else rules_raw.get("signatures", rules_raw.get("rules")))
    truth_s = df.set_index("alert_id")["attack_class"]

    def evaluate(rules, tag):
        hits, per_rule = {}, {}
        for r in rules:
            m = rule_mask(det, r)
            ids = list(det.loc[m, "id"])
            per_rule[r["id"]] = len(ids)
            for i in ids:
                hits[i] = r
        tp = sum(1 for i, r in hits.items() if truth_s[i] == r["predictedAttackType"])
        mal = sum(1 for i in hits if truth_s[i] != "Benign")
        n_mal = int((truth_s != "Benign").sum())
        prec = tp / len(hits) if hits else float("nan")
        rec = tp / n_mal if n_mal else float("nan")
        print(f"\n{tag}: {len(hits)} hits | class-correct TP={tp} "
              f"| any-malicious={mal} | precision={prec:.3f} recall={rec:.4f}")
        print("   per rule:", {k: v for k, v in per_rule.items() if v})
        return {"hits": len(hits), "tp": tp, "any_malicious": mal,
                "precision": None if np.isnan(prec) else round(prec, 4),
                "recall": None if np.isnan(rec) else round(rec, 4),
                "per_rule": per_rule, "hit_ids": sorted(hits)}

    c1 = evaluate(RULES, "C1 ORIGINAL rules on corrected data")

    tuned = json.loads(json.dumps(RULES))
    for r in tuned:
        if r["id"] == "SIG-SSH-BRUTE-FORCE":
            r["condition"]["flowPacketsPerSecond"] = {"min": 20}
    c2 = evaluate(tuned, "C2 RETUNED rules (SSH min 10 -> 20)")

    import xgboost as xgb
    feats = json.load(open(MODELS / "feature-columns.json", encoding="utf-8"))
    labmap = json.load(open(MODELS / "label-mapping.json", encoding="utf-8"))
    X = df.reindex(columns=feats).apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float32")
    booster = xgb.Booster()
    booster.load_model(str(MODELS / "xgboost_ids_model.json"))
    proba = booster.inplace_predict(X.to_numpy())
    idx = proba.argmax(axis=1)
    preds = {df.alert_id.iloc[i]: {"predictedAttackType": labmap[str(idx[i])],
                                   "modelConfidence": round(float(proba[i, idx[i]]), 6)}
             for i in range(len(df))}
    (PROC / "demo_ml_predictions.json").write_text(json.dumps(preds, indent=1), encoding="utf-8")
    ml_mal = {k for k, v in preds.items() if v["predictedAttackType"] != "Benign"}
    print(f"\nML flags malicious: {len(ml_mal)} of {len(df)}")

    sig_ids = set(c2["hit_ids"])
    mal_ids = set(truth_s.index[truth_s != "Benign"])
    both = sig_ids & ml_mal
    print(f"\nC3 co-occurrence (retuned rules): {len(both)}")
    print(f"   malicious caught by ML only        : {len((ml_mal & mal_ids) - sig_ids)}")
    print(f"   malicious caught by signature only : {len((sig_ids & mal_ids) - ml_mal)}")
    print(f"   malicious caught by both           : {len(sig_ids & ml_mal & mal_ids)}")
    print(f"   malicious missed by both           : {len(mal_ids - ml_mal - sig_ids)}")

    out = {"source": src.name, "rows": len(df),
           "C1_original_rules": c1, "C2_retuned_rules": c2,
           "C3_cooccurrence": {
               "signature_and_ml": len(both),
               "ml_only": len((ml_mal & mal_ids) - sig_ids),
               "signature_only": len((sig_ids & mal_ids) - ml_mal),
               "both": len(sig_ids & ml_mal & mal_ids),
               "missed_by_both": len(mal_ids - ml_mal - sig_ids),
               "total_malicious": len(mal_ids)}}
    (PROC / "corrected_findings.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {PROC / 'corrected_findings.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
