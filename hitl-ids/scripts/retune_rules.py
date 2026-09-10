"""
Empirically retune the 7 flow-based signature rules against the corrected dataset.

The as-shipped rules were written from textbook intuition and never calibrated. This script
measures, per rule, (A) whether the clause evaluator reproduces the documented ~62-63 total hits,
(B) which clause is the blocking one via leave-one-out attrition, and (C) whether a single-threshold
variation of a numeric clause can reach precision >= 0.90 against the rule's own target class.
Finally (D) it builds the best retuned rule set and measures coverage over truly-malicious rows:
does the retuned signature engine catch anything the ML model misses?

Inputs (read-only):
    hitl-ids/data/processed/demo_detection_input.csv   17 observable flow fields (detector input)
    hitl-ids/data/processed/demo_ground_truth.json     labels, evaluation only
    hitl-ids/tests/fixtures/legacy/flow-signatures.json  the 7 rules
    hitl-ids/data/processed/demo_ml_predictions.json   model output

Outputs:
    hitl-ids/data/processed/retune_results.json
    hitl-ids/docs/rule-retuning-report.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROC = HERE.parent / "data" / "processed"
FIX = HERE.parent / "tests" / "fixtures" / "legacy"
DOCS = HERE.parent / "docs"

INPUT_CSV = PROC / "demo_detection_input.csv"
GROUND_TRUTH = PROC / "demo_ground_truth.json"
SIGNATURES = FIX / "flow-signatures.json"
ML_PREDS = PROC / "demo_ml_predictions.json"
OUT_JSON = PROC / "retune_results.json"
OUT_MD = DOCS / "rule-retuning-report.md"

PRECISION_BAR = 0.90
QUANTILES = np.linspace(0.01, 0.99, 99)


def load_rules() -> list[dict]:
    raw = json.loads(SIGNATURES.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return raw.get("signatures", raw.get("rules", raw))


def clause_mask(df: pd.DataFrame, field: str, spec) -> pd.Series:
    """Evaluate one condition clause. Scalar = equality, {"oneOf": [...]} = membership,
    {"min"/"max"} = inclusive numeric range. All clauses are ANDed by the caller."""
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


def condition_mask(df: pd.DataFrame, condition: dict) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for f, s in condition.items():
        m &= clause_mask(df, f, s)
    return m


def precision_recall_f1(fired: pd.Series, y_target: pd.Series) -> dict:
    n_fired = int(fired.sum())
    tp = int((fired & y_target).sum())
    n_target = int(y_target.sum())
    precision = tp / n_fired if n_fired else 0.0
    recall = tp / n_target if n_target else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"fired": n_fired, "tp": tp, "precision": round(precision, 4),
            "recall": round(recall, 4), "f1": round(f1, 4)}


def candidate_thresholds(df: pd.DataFrame, field: str) -> list[float]:
    vals = pd.to_numeric(df[field], errors="coerce").dropna().to_numpy(dtype="float64")
    if vals.size == 0:
        return []
    qs = np.quantile(vals, QUANTILES)
    return sorted({round(float(q), 6) for q in qs})


def main() -> int:
    df = pd.read_csv(INPUT_CSV, low_memory=False)
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    ml_preds = json.loads(ML_PREDS.read_text(encoding="utf-8"))
    rules = load_rules()

    attack_map = {rid: v["attackType"] for rid, v in truth.items()}
    y_true = df["id"].map(attack_map)
    n_rows = len(df)
    n_malicious = int((y_true != "Benign").sum())

    # ---- A. baseline: reproduce total hits and overall precision/recall ----
    per_rule = {}
    dedup_hits: dict[str, dict] = {}
    for r in rules:
        m = condition_mask(df, r["condition"])
        per_rule[r["id"]] = int(m.sum())
        for i in df.loc[m, "id"]:
            dedup_hits.setdefault(i, r)

    total_hits = sum(per_rule.values())
    tp = sum(1 for i, r in dedup_hits.items() if attack_map[i] == r["predictedAttackType"])
    baseline = {
        "n_rows": n_rows,
        "n_malicious": n_malicious,
        "total_hits": total_hits,
        "dedup_hits": len(dedup_hits),
        "per_rule_hits": per_rule,
        "rules_firing": {k: v for k, v in per_rule.items() if v},
        "class_correct_tp": tp,
        "precision": round(tp / len(dedup_hits), 4) if dedup_hits else None,
        "recall": round(tp / n_malicious, 4) if n_malicious else None,
    }
    print(f"rows={n_rows} malicious={n_malicious}")
    print(f"A) total signature hits (sum over rules): {total_hits}")
    print(f"   per rule: {per_rule}")
    print(f"   dedup hits={len(dedup_hits)}  class-correct TP={tp}  "
          f"precision={baseline['precision']}  recall={baseline['recall']}")

    # ---- B. clause attrition (alone vs leave-one-out) ----
    attrition = {}
    for r in rules:
        cond = r["condition"]
        entry = {}
        for field, spec in cond.items():
            alone = int(clause_mask(df, field, spec).sum())
            others = pd.Series(True, index=df.index)
            for f2, s2 in cond.items():
                if f2 != field:
                    others &= clause_mask(df, f2, s2)
            entry[field] = {"clause": spec, "alone_pass": alone,
                            "others_pass": int(others.sum())}
        attrition[r["id"]] = entry

    # ---- C. single-threshold search per rule ----
    best_per_rule = {}
    threshold_search = {}
    for r in rules:
        target = r["predictedAttackType"]
        y_target = (y_true == target)
        cond = r["condition"]
        candidates = []
        for field, spec in cond.items():
            if not (isinstance(spec, dict) and ("min" in spec or "max" in spec)):
                continue  # skip scalar/oneOf clauses: not a numeric threshold
            for direction in ("HIGH", "LOW"):
                for t in candidate_thresholds(df, field):
                    variant = dict(cond)
                    variant[field] = {"min": t} if direction == "HIGH" else {"max": t}
                    fired = condition_mask(df, variant)
                    m = precision_recall_f1(fired, y_target)
                    candidates.append({"field": field, "direction": direction,
                                       "threshold": t, **m})

        qualified = [c for c in candidates if c["precision"] >= PRECISION_BAR]
        if qualified:
            best = max(qualified, key=lambda c: (c["recall"], c["precision"]))
            best_qualified = best
            retuned_condition = dict(cond)
            retuned_condition[best["field"]] = (
                {"min": best["threshold"]} if best["direction"] == "HIGH"
                else {"max": best["threshold"]})
        else:
            best_qualified = None
            retuned_condition = None
        max_prec = max(candidates, key=lambda c: (c["precision"], c["recall"])) if candidates else None

        best_per_rule[r["id"]] = {
            "name": r["name"],
            "target": target,
            "current_hits": per_rule[r["id"]],
            "n_candidates": len(candidates),
            "reached_precision_0.90": best_qualified is not None,
            "best_qualified": best_qualified,
            "max_precision": max_prec,
            "retuned_condition": retuned_condition,
        }
        threshold_search[r["id"]] = candidates

    # ---- D. coverage: retuned signatures vs ML over truly-malicious rows ----
    retuned_rules = []
    for r in rules:
        bpr = best_per_rule[r["id"]]
        if bpr["reached_precision_0.90"]:
            r2 = json.loads(json.dumps(r))
            r2["condition"] = bpr["retuned_condition"]
            retuned_rules.append(r2)

    sig_ids: set[str] = set()
    for r in retuned_rules:
        m = condition_mask(df, r["condition"])
        sig_ids |= set(df.loc[m, "id"])

    ml_flag_ids = {rid for rid, v in ml_preds.items() if v["predictedAttackType"] != "Benign"}
    mal_ids = {rid for rid, at in attack_map.items() if at != "Benign"}

    coverage = {
        "n_retuned_rules": len(retuned_rules),
        "total_malicious": len(mal_ids),
        "ml_only": len((ml_flag_ids & mal_ids) - sig_ids),
        "signature_only": len((sig_ids & mal_ids) - ml_flag_ids),
        "both": len(sig_ids & ml_flag_ids & mal_ids),
        "missed_by_both": len(mal_ids - ml_flag_ids - sig_ids),
    }

    out = {
        "baseline": baseline,
        "attrition": attrition,
        "best_per_rule": best_per_rule,
        "threshold_search": threshold_search,
        "coverage": coverage,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")

    # ---- report (markdown) ----
    write_report(out)
    print(f"wrote {OUT_MD}")

    # ---- stdout coverage table (required) ----
    print("\n===== COVERAGE (truly-malicious rows, attackType != Benign) =====")
    print(f"{'caught by ML only':<22} : {coverage['ml_only']}")
    print(f"{'caught by signatures only':<22} : {coverage['signature_only']}   <-- KEY NUMBER")
    print(f"{'caught by both':<22} : {coverage['both']}")
    print(f"{'missed by both':<22} : {coverage['missed_by_both']}")
    print(f"{'total malicious':<22} : {coverage['total_malicious']}")
    print(f"{'retuned rules used':<22} : {coverage['n_retuned_rules']}")
    return 0


def _fmt(x, nd=4):
    return "n/a" if x is None else f"{x:.{nd}f}"


def write_report(out: dict) -> None:
    baseline = out["baseline"]
    bpr = out["best_per_rule"]
    coverage = out["coverage"]

    lines: list[str] = []
    add = lines.append
    add("# Rule Retuning Report")
    add("")
    add(f"- rows: {baseline['n_rows']:,}  |  malicious (attackType != Benign): "
        f"{baseline['n_malicious']:,}")
    add(f"- as-shipped total signature hits: {baseline['total_hits']}  "
        f"(dedup {baseline['dedup_hits']}, class-correct precision "
        f"{_fmt(baseline['precision'])}, recall {_fmt(baseline['recall'])})")
    add("")
    add("## Per-rule retuning")
    add("")
    add("| Rule | Target | Current hits | Best precision | Best recall | Reaches >= 0.90 |")
    add("|---|---|---|---:|---:|---|")
    for rid, b in bpr.items():
        if b["reached_precision_0.90"]:
            q = b["best_qualified"]
            bp, br = _fmt(q["precision"]), _fmt(q["recall"])
            reach = "yes"
        else:
            mp = b["max_precision"]
            bp, br = (_fmt(mp["precision"]), _fmt(mp["recall"])) if mp else ("n/a", "n/a")
            reach = "no"
        add(f"| {rid} | {b['target']} | {b['current_hits']} | {bp} | {br} | {reach} |")
    add("")
    add("## Which rules can reach precision 0.90")
    add("")
    can = [rid for rid, b in bpr.items() if b["reached_precision_0.90"]]
    cannot = [rid for rid, b in bpr.items() if not b["reached_precision_0.90"]]
    add(f"- reach >= 0.90: {', '.join(can) if can else 'none'}")
    add(f"- cannot reach >= 0.90: {', '.join(cannot) if cannot else 'none'}")
    add("")
    add("## Coverage: retuned signatures vs ML (truly-malicious rows)")
    add("")
    add("| Metric | Count |")
    add("|---|---:|")
    add(f"| caught by ML only | {coverage['ml_only']} |")
    add(f"| caught by retuned signatures only | {coverage['signature_only']} |")
    add(f"| caught by both | {coverage['both']} |")
    add(f"| missed by both | {coverage['missed_by_both']} |")
    add(f"| total malicious | {coverage['total_malicious']} |")
    add("")
    add("## Conclusion")
    add("")
    if coverage["signature_only"] > 0:
        add(f"The retuned signatures catch {coverage['signature_only']} malicious row(s) that the "
            f"ML model misses, on top of {coverage['both']} caught by both. The signature engine "
            f"adds independent detection value and is not redundant with the model.")
    else:
        add("The retuned signatures catch no malicious rows that the ML model misses "
            "(signature-only = 0). Every malicious row the signatures flag is already flagged by "
            "the ML model, so on this dataset the signature engine adds no incremental coverage.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
