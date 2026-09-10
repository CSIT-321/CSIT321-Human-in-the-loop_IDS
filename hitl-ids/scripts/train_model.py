"""
Train the 8-class XGBoost detector on the corrected CSE-CIC-IDS2018 sample.

Replaces the legacy 6-class model, which could not emit `Infiltration` at all and was trained on
the uncorrected dataset. Class set (see docs/plan-changelog.md v1.1):
    Benign, Botnet, Brute Force, DDoS, DoS, Infiltration, Port Scan, Web Attack

LABEL LEAKAGE GUARDS - the detector must never see:
    Label, Attempted Category, attack_class, is_attempted   (ground truth, or metadata about it)
    id, Flow ID, alert_id, Src IP, Dst IP, Timestamp        (identifiers / trace back to labels)
    Src Port                                                (ephemeral, memorises hosts)
`Attempted Category` is a NEW leakage vector introduced by the corrected release: it states
whether an attack succeeded, so a model that sees it can infer maliciousness trivially.

Outputs (hitl-ids/models/):
    xgboost_ids_model.json     the booster
    feature-columns.json       exact feature order used at inference
    label-mapping.json         class index -> name
    training-metrics.json      per-class precision/recall/F1, confusion matrix
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "processed" / "train_sample.csv"
MODELS = HERE.parent / "models"

SEED = 20260911

DROP = {"alert_id", "attack_class", "is_attempted", "Label", "Attempted Category",
        "id", "Flow ID", "Src IP", "Dst IP", "Timestamp", "Src Port"}


def main() -> int:
    if not DATA.exists():
        print(f"missing {DATA} - run build_samples.py first", file=sys.stderr)
        return 2
    MODELS.mkdir(parents=True, exist_ok=True)

    print("loading", DATA)
    df = pd.read_csv(DATA, low_memory=False)
    print(f"  {len(df):,} rows x {len(df.columns)} columns")

    y_raw = df["attack_class"]
    classes = sorted(y_raw.unique())
    cls_to_idx = {c: i for i, c in enumerate(classes)}
    y = y_raw.map(cls_to_idx).to_numpy()
    print("  classes:", cls_to_idx)

    feats = [c for c in df.columns if c not in DROP]
    X = df[feats].apply(pd.to_numeric, errors="coerce")
    before = list(X.columns)
    X = X.loc[:, X.notna().any() & (X.nunique(dropna=True) > 1)]
    dropped = [c for c in before if c not in X.columns]
    if dropped:
        print(f"  dropped {len(dropped)} non-numeric/constant columns: {dropped[:8]}"
              f"{' ...' if len(dropped) > 8 else ''}")
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float32")
    feats = list(X.columns)
    print(f"  {len(feats)} features after cleaning")

    leaked = [c for c in feats if c in DROP]
    if leaked:
        print(f"LEAKAGE: {leaked} survived the drop list", file=sys.stderr)
        return 3

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, confusion_matrix
    import xgboost as xgb

    Xtr, Xte, ytr, yte = train_test_split(
        X.to_numpy(), y, test_size=0.2, random_state=SEED, stratify=y)
    print(f"  train {len(ytr):,} / held-out {len(yte):,}")

    # inverse-frequency weights: Web Attack and Infiltration are ~1000x rarer than Benign
    counts = np.bincount(ytr, minlength=len(classes))
    w = (len(ytr) / (len(classes) * np.maximum(counts, 1)))[ytr]

    clf = xgb.XGBClassifier(
        n_estimators=400, max_depth=8, learning_rate=0.15,
        subsample=0.9, colsample_bytree=0.9,
        objective="multi:softprob", num_class=len(classes),
        tree_method="hist", random_state=SEED, n_jobs=-1, eval_metric="mlogloss",
    )
    print("training ...")
    clf.fit(Xtr, ytr, sample_weight=w, verbose=False)

    pred = clf.predict(Xte)
    rep = classification_report(yte, pred, target_names=classes,
                                output_dict=True, zero_division=0)
    print("\nheld-out performance:")
    print(classification_report(yte, pred, target_names=classes, zero_division=0))

    clf.get_booster().save_model(str(MODELS / "xgboost_ids_model.json"))
    (MODELS / "feature-columns.json").write_text(json.dumps(feats, indent=2), encoding="utf-8")
    (MODELS / "label-mapping.json").write_text(
        json.dumps({str(i): c for c, i in cls_to_idx.items()}, indent=2), encoding="utf-8")
    (MODELS / "training-metrics.json").write_text(json.dumps({
        "seed": SEED,
        "source": DATA.name,
        "n_train": int(len(ytr)),
        "n_heldout": int(len(yte)),
        "n_features": len(feats),
        "classes": classes,
        "report": rep,
        "confusion_matrix": confusion_matrix(yte, pred).tolist(),
        "leakage_guard_dropped": sorted(DROP),
    }, indent=2), encoding="utf-8")

    print(f"\nwrote model + artifacts to {MODELS}")
    print(f"macro F1: {rep['macro avg']['f1-score']:.4f}   "
          f"weighted F1: {rep['weighted avg']['f1-score']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
