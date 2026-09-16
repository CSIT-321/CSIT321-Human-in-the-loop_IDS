#!/usr/bin/env python3
"""Build a SYNTHETIC degraded-detector prediction set (stress sample), then let the real
pipeline turn it into a stress detection database.

    python scripts/build_stress_detection.py                 # writes the prediction file
    python scripts/run_detection.py --replay data/processed/stress_ml_predictions.json \
        --database data/stress.db

**Why this exists.** `ranking-and-escalation-design.md` section 8 has asked since v1.13 for a run
against "a weaker or drifting detector, so that the top of the queue has false positives to learn
from". S15 could not answer the efficiency question without it: on the pristine demo sample the
control queue is already perfect (2 false positives in 996 flagged alerts), so analyst feedback has
nothing to correct and can only disturb a perfect ordering.

**How the degradation is made, and why it invents no numbers.** For each flow it degrades, the
script copies the *complete prediction record of a real attack flow of the target class* onto that
flow's id. Every prediction class, probability, confidence, margin and TreeSHAP attribution in the
output is therefore an unfabricated output of the committed model — read from
`data/processed/demo_ml_predictions_shap.json`. Only the association between a flow and a
prediction is synthetic, which is precisely what "a degraded detector" means: the detector reports
on this flow what it really said about a different one.

**The honest limit, stated plainly.** Because the record is copied, an injected alert's SHAP panel
describes the *donor* flow: its cited feature values belong to that flow, not to the alert it is
attached to. That is a defect of this synthetic artifact, not of the product, and it is why this
file must never be presented as a measurement of the model. `data/demo.db` remains the real one.

Two degradations, both seeded and reproducible:
  * **False positives** - a deterministic share of BENIGN flows is given a real attack's record, so
    they land at the top of the queue as high-confidence model-only alerts.
  * **False negatives** - a deterministic share of real ATTACK flows is given a real benign flow's
    record, so the detector also misses attacks it used to catch.

Output: data/processed/stress_ml_predictions.json plus a printed manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
PROCESSED = HITL / "data" / "processed"
SAMPLE = PROCESSED / "demo_sample.csv"
SOURCE = PROCESSED / "demo_ml_predictions_shap.json"
OUT = PROCESSED / "stress_ml_predictions.json"

#: A different seed from the sample's 20260911, so this artifact can never be mistaken for it.
SEED = 20260916
#: Share of BENIGN flows turned into false positives.
FALSE_POSITIVE_RATE = 0.15
#: Share of real ATTACK flows turned into false negatives.
FALSE_NEGATIVE_RATE = 0.30


def ground_truth(path: Path) -> dict[str, str]:
    """alert id -> the flow's own class. Used only to choose WHICH flows to degrade."""
    truth: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            truth[row["alert_id"]] = row["attack_class"] or "Benign"
    return truth


def donors_by_class(records: dict[str, dict], truth: dict[str, str]) -> dict[str, list[str]]:
    """Real attack flows the model genuinely called an attack, grouped by the class it named."""
    donors: dict[str, list[str]] = {}
    for alert_id, actual in truth.items():
        if actual == "Benign":
            continue
        predicted = records[alert_id].get("predictedAttackType")
        if predicted not in (None, "Benign"):
            donors.setdefault(str(predicted), []).append(alert_id)
    return {name: sorted(ids) for name, ids in sorted(donors.items())}


def build(*, fp_rate: float, fn_rate: float, seed: int) -> dict:
    truth = ground_truth(SAMPLE)
    records: dict[str, dict] = json.loads(SOURCE.read_text(encoding="utf-8"))

    benign = sorted(i for i, actual in truth.items() if actual == "Benign")
    attacks = sorted(i for i, actual in truth.items() if actual != "Benign")
    donors = donors_by_class(records, truth)
    if not donors:
        raise SystemExit("no donor attack records: is the prediction file the real one?")

    # A real benign record, for the false negatives.
    benign_donor = next(i for i in benign
                        if records[i].get("predictedAttackType") == "Benign")

    rng = random.Random(seed)
    out = dict(records)

    # ---- false positives: cycling through the classes keeps the injection balanced ----------
    classes = list(donors)
    injected = rng.sample(benign, int(len(benign) * fp_rate))
    fp_classes: Counter[str] = Counter()
    for index, alert_id in enumerate(injected):
        target = classes[index % len(classes)]
        donor = rng.choice(donors[target])
        out[alert_id] = {**records[donor], "id": alert_id}
        fp_classes[target] += 1

    # ---- false negatives --------------------------------------------------------------------
    missed = rng.sample(attacks, int(len(attacks) * fn_rate))
    for alert_id in missed:
        out[alert_id] = {**records[benign_donor], "id": alert_id}

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    remaining = Counter(truth[i] for i in attacks if i not in set(missed))
    return {
        "seed": seed,
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "flows": len(truth),
        "benign_flows": len(benign),
        "attack_flows": len(attacks),
        "injected_false_positives": len(injected),
        "false_positives_by_target_class": dict(sorted(fp_classes.items())),
        "injected_false_negatives": len(missed),
        "attacks_still_reported": sum(remaining.values()),
        "attacks_still_reported_by_class": dict(sorted(remaining.items())),
        "notice": ("SYNTHETIC. Every prediction value is a real output of the committed model, "
                   "copied from a donor flow; only the flow-to-prediction association is "
                   "synthetic. An injected alert's SHAP panel describes its donor flow. Never "
                   "present this file as a measurement of the model."),
        "output": str(OUT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--false-positive-rate", type=float, default=FALSE_POSITIVE_RATE)
    parser.add_argument("--false-negative-rate", type=float, default=FALSE_NEGATIVE_RATE)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    for path in (SAMPLE, SOURCE):
        if not path.exists():
            print(f"missing {path} - see data/README.md", file=sys.stderr)
            return 2

    print(json.dumps(build(fp_rate=args.false_positive_rate,
                           fn_rate=args.false_negative_rate,
                           seed=args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
