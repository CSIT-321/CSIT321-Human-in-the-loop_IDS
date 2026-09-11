"""
Re-measure the tuned rule set with the production engine (plan step S4b verification).

HANDOVER §4 reports held-out figures for the tuned rules (precision 0.9999, recall 0.1993,
2 false positives in 30,025 hits on train_sample.csv). That run was never committed; this script
is the reproducible version. It uses the ported engine, not a vectorised re-implementation, so
the figures describe the code S9 will run.

Ground truth (`attack_class`) is joined only after matching. Two scorings are reported, because
the project has used both:
    class-correct      the flow's true class equals the class the first matching rule asserts
                       (changelog v1.3's per-rule figures)
    malicious-correct  the flow is any attack (HANDOVER §4's held-out figures)
Recall is over all malicious flows; per-rule recall is over the rule's own class.

Inputs:  rules/rule-set-s4b-1.json
         data/processed/demo_sample.csv    (5,000 rows, in git)
         data/processed/train_sample.csv   (250,655 rows, regenerate - see data/README.md)
Output:  data/processed/rule_set_validation.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts.models import SignatureRule  # noqa: E402
from packages.detection.signature.engine import match_all  # noqa: E402
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_frame  # noqa: E402
from packages.detection.signature.rule_set import DEFAULT_RULE_SET, load_rule_set  # noqa: E402

PROCESSED = HITL / "data" / "processed"
SAMPLES = {"demo": PROCESSED / "demo_sample.csv", "held_out": PROCESSED / "train_sample.csv"}
OUTPUT = PROCESSED / "rule_set_validation.json"


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def measure(sample: Path, rules: list[SignatureRule]) -> dict:
    frame = pd.read_csv(sample, usecols=["alert_id", "attack_class", *OBSERVABLE_FIELDS],
                        low_memory=False)
    view = project_frame(frame).drop(columns="id")
    truth = frame["attack_class"].tolist()
    enabled = [rule for rule in rules if rule.enabled]
    per_rule = {rule.rule_id: {"fired": 0, "class_correct": 0} for rule in enabled}
    misattributed: Counter[tuple[str, str]] = Counter()
    hits = 0

    for record, true_class in zip(view.to_dict("records"), truth, strict=True):
        matches = match_all(record, enabled)
        if not matches:
            continue
        first = matches[0]
        hits += 1
        per_rule[first.rule_id]["fired"] += 1
        if true_class == first.attack_category:
            per_rule[first.rule_id]["class_correct"] += 1
        else:
            misattributed[(first.rule_id, true_class)] += 1

    class_sizes = pd.Series(truth).value_counts().to_dict()
    for rule in enabled:
        stats = per_rule[rule.rule_id]
        stats["precision"] = ratio(stats["class_correct"], stats["fired"])
        stats["recall_of_class"] = ratio(stats["class_correct"],
                                         class_sizes.get(rule.attack_category, 0))
    malicious = sum(1 for true_class in truth if true_class != "Benign")
    class_correct = hits - sum(misattributed.values())
    benign_hits = sum(flows for (_, true_class), flows in misattributed.items()
                      if true_class == "Benign")
    return {
        "sample": sample.name,
        "rows": len(truth),
        "malicious": malicious,
        "hits": hits,
        "class_correct": class_correct,
        "benign_hits": benign_hits,
        "misattributed": [{"rule_id": rule_id, "true_class": true_class, "flows": flows}
                          for (rule_id, true_class), flows in sorted(misattributed.items())],
        "precision_class": ratio(class_correct, hits),
        "recall_class": ratio(class_correct, malicious),
        "precision_malicious": ratio(hits - benign_hits, hits),
        "recall_malicious": ratio(hits - benign_hits, malicious),
        "per_rule": per_rule,
    }


def main() -> int:
    rules = load_rule_set(DEFAULT_RULE_SET)
    report: dict = {"rule_set": DEFAULT_RULE_SET.relative_to(HITL).as_posix()}
    for name, path in SAMPLES.items():
        if not path.exists():
            print(f"skip {name}: {path.name} is missing (see data/README.md)")
            continue
        result = report[name] = measure(path, rules)
        print(f"{name:9} hits {result['hits']:>6,} | class-correct precision "
              f"{result['precision_class']} recall {result['recall_class']} | malicious-correct "
              f"precision {result['precision_malicious']} recall {result['recall_malicious']}"
              f" | misattributed {result['misattributed']}")
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(HITL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
