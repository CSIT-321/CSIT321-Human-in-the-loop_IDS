"""
Summarise the fused demo queue for the Iteration 2 report and its diagrams (plan step S6).

Runs the production path over all 5,000 demo flows - observable view -> rule engine -> model
output -> fuse() - and records the analyst's queue. Ground truth (`attack_class`) is joined only
after fusion, for the evaluation columns; it never reaches a detector.

Inputs:  data/processed/demo_sample.csv
         data/processed/demo_ml_predictions_shap.json   (regenerate with run_ml_inference.py)
         rules/rule-set-s4b-1.json
Output:  data/processed/fusion_demo_summary.json         (small and tracked; make_diagrams.py reads it)
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts.models import MlPrediction  # noqa: E402
from packages.detection.fusion.cef import (  # noqa: E402
    EVIDENCE_PRIORITY,
    FusionConfig,
    FusionDecision,
    fuse,
    queue_key,
)
from packages.detection.signature.engine import match_all  # noqa: E402
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_frame  # noqa: E402
from packages.detection.signature.rule_set import DEFAULT_RULE_SET, load_rule_set  # noqa: E402

PROCESSED = HITL / "data" / "processed"
OUTPUT = PROCESSED / "fusion_demo_summary.json"
EXAMPLE_FIELDS = {"evidence_class", "combined_score", "severity", "requires_review",
                  "signature_severity", "ml_probability", "ml_predicted_class", "attack_category",
                  "explanation"}


def example(alert_id: str, decision: FusionDecision) -> dict:
    return {"alert_id": alert_id, **decision.model_dump(mode="json", include=EXAMPLE_FIELDS)}


def queue_bands(queue: list) -> list[dict]:
    """Consecutive queue positions held by one evidence class."""
    bands: list[dict] = []
    for position, (_, _, decision) in enumerate(queue, start=1):
        if bands and bands[-1]["evidence_class"] == decision.evidence_class:
            bands[-1]["last"] = position
        else:
            bands.append({"evidence_class": decision.evidence_class,
                          "first": position, "last": position})
    return bands


def main() -> int:
    frame = pd.read_csv(PROCESSED / "demo_sample.csv",
                        usecols=["alert_id", "attack_class", *OBSERVABLE_FIELDS], low_memory=False)
    view = project_frame(frame).drop(columns="id").to_dict("records")
    predictions = {record_id: MlPrediction.model_validate(record) for record_id, record in
                   json.loads((PROCESSED / "demo_ml_predictions_shap.json")
                              .read_text(encoding="utf-8")).items()}
    live = [rule for rule in load_rule_set(DEFAULT_RULE_SET) if rule.enabled]
    config = FusionConfig()

    fused = [(alert_id, truth, fuse(match_all(record, live), predictions[alert_id], config))
             for record, alert_id, truth in
             zip(view, frame["alert_id"], frame["attack_class"], strict=True)]
    queue = sorted(fused, key=lambda item: queue_key(item[2]))  # stable, as the DB's id ASC

    classes = {}
    examples = {}
    for evidence in EVIDENCE_PRIORITY:
        members = [item for item in queue if item[2].evidence_class == evidence]
        scores = [decision.combined_score for _, _, decision in members]
        classes[evidence] = {
            "alerts": len(members),
            "requires_review": sum(decision.requires_review for _, _, decision in members),
            "truly_malicious": sum(truth != "Benign" for _, truth, _ in members),
            "truly_benign": sum(truth == "Benign" for _, truth, _ in members),
            "severity": dict(sorted(Counter(d.severity for _, _, d in members).items())),
            "score": ({"min": min(scores), "median": statistics.median(scores),
                       "max": max(scores)} if scores else None),
        }
        # the first alert of the class the analyst would reach; an SSH match shows the tuned rule
        ssh = [item for item in members if item[2].signature_rules
               and item[2].signature_rules[0].rule_id == "SIG-SSH-BRUTE-FORCE"]
        chosen = (ssh or members or [None])[0]
        examples[evidence] = example(chosen[0], chosen[2]) if chosen else None

    summary = {
        "rows": len(fused),
        "rule_set": DEFAULT_RULE_SET.relative_to(HITL).as_posix(),
        "live_rules": [{"rule_id": rule.rule_id, "severity": rule.severity,
                        "attack_category": rule.attack_category,
                        "severity_score": config.severity_scores[rule.severity]} for rule in live],
        "fusion_config": config.snapshot(),
        "requires_review": sum(decision.requires_review for _, _, decision in fused),
        "critical": sum(decision.is_critical for _, _, decision in fused),
        "classes": classes,
        "queue_bands": queue_bands(queue),
        "examples": examples,
    }
    OUTPUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "examples"}, indent=1))
    print(f"wrote {OUTPUT.relative_to(HITL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
