"""
Run 8-class inference with native TreeSHAP explanations over the demo sample.

Uses `hitl-ids/packages/detection/ml/inference.py` - a vendored, adapted copy of a
collaborator's `stage-3/core/ml_inference.py`. The upstream module targets the 6-class model
trained on the UNCORRECTED dataset and rejects ours outright (it hard-asserts 78 features; we
have 82). See that module's docstring for the three adaptations.

Leakage: the ML input carries `id` plus exactly the 82 model features and nothing else, so
`Label`, `Attempted Category`, `attack_class` and `is_attempted` cannot reach the model by
construction. The assertion below enforces it rather than trusting the construction.

Outputs (hitl-ids/data/processed/):
    demo_ml_input.csv              feature-only prediction input
    demo_ml_predictions_shap.json  predictions + per-alert TreeSHAP explanations
    ml-explainability-summary.json integrity report (supersedes the stage-3 6-class version)
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
HITL = HERE.parent
sys.path.insert(0, str(HITL / "packages" / "detection" / "ml"))
import inference as inf  # noqa: E402

PROC = HITL / "data" / "processed"


def main() -> int:
    src = PROC / "demo_sample.csv"
    if not src.exists():
        print(f"missing {src} - run build_samples.py first", file=sys.stderr)
        return 2

    artifacts = inf.load_model_artifacts()
    print(f"model: {artifacts.model_class_count} classes, "
          f"{len(artifacts.feature_columns)} features, {artifacts.objective}")

    df = pd.read_csv(src, low_memory=False)
    ml_in = pd.DataFrame({"id": df["alert_id"]})
    for col in artifacts.feature_columns:
        if col not in df.columns:
            print(f"feature missing from demo sample: {col!r}", file=sys.stderr)
            return 3
        ml_in[col] = pd.to_numeric(df[col], errors="coerce")

    leaked = [c for c in ml_in.columns if c in inf.FORBIDDEN_PREDICTION_FIELDS]
    if leaked:
        print(f"LEAKAGE - refusing to run: {leaked}", file=sys.stderr)
        return 4

    input_path = PROC / "demo_ml_input.csv"
    ml_in.to_csv(input_path, index=False)
    print(f"input: {len(ml_in):,} rows x {len(ml_in.columns)} cols (id + features), leakage guard clean")

    records = inf.predict_csv(input_path, artifacts, include_explanations=True)

    passed = failed = unavailable = 0
    diffs: list[float] = []
    for rec in records:
        expl = rec.get("mlExplanation") or {}
        check = expl.get("additivityCheck")
        if expl.get("status") != "available" or not check:
            unavailable += 1
            continue
        if check.get("passed"):
            passed += 1
        else:
            failed += 1
        diff = check.get("difference")
        if diff is not None:
            diffs.append(abs(float(diff)))

    distribution = dict(collections.Counter(r["predictedAttackType"] for r in records))
    summary = {
        "method": inf.TREESHAP_METHOD,
        "outputSpace": inf.TREESHAP_OUTPUT_SPACE,
        "additivityTolerance": inf.TREESHAP_ADDITIVITY_TOLERANCE,
        "datasetSource": "corrected CSE-CIC-IDS2018 (Engelen et al., IEEE CNS 2022)",
        "inputCount": len(records),
        "explanationsAvailable": passed + failed,
        "explanationsUnavailable": unavailable,
        "additivityPassed": passed,
        "additivityFailed": failed,
        "maxAdditivityDifference": max(diffs) if diffs else None,
        "meanAdditivityDifference": sum(diffs) / len(diffs) if diffs else None,
        "predictedClassDistribution": distribution,
        "modelProvenance": artifacts.provenance,
        "supersedes": "stage-3/evaluation/ml-explainability-summary.json (6-class, uncorrected)",
    }

    (PROC / "demo_ml_predictions_shap.json").write_text(
        json.dumps({r["id"]: r for r in records}, indent=1), encoding="utf-8")
    (PROC / "ml-explainability-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nTreeSHAP integrity over {len(records):,} alerts")
    print(f"   available   {passed + failed}   unavailable {unavailable}")
    print(f"   additivity  passed {passed}   failed {failed}")
    if diffs:
        print(f"   max |diff|  {max(diffs):.3e}  (tolerance {inf.TREESHAP_ADDITIVITY_TOLERANCE:.0e})")
    print("\npredicted class distribution:")
    for k, v in sorted(distribution.items(), key=lambda kv: -kv[1]):
        print(f"   {k:<14}{v:>6,}")

    if failed or unavailable:
        print("\nWARNING: not every alert has a verified explanation. NFR-01 requires one per alert.",
              file=sys.stderr)
        return 5
    print("\nEvery alert carries a TreeSHAP explanation with verified additivity (NFR-01 satisfied).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
