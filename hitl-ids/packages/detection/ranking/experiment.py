"""The ranking selection experiment (docs/ranking-and-escalation-design.md §6).

Past versus future. The demo flows are ordered by timestamp; the first half is **calibration**, where a
simulated Tier 1 analyst reviews the top of the queue each round and gives verdicts, and the second
half is **future** traffic the analyst never sees. Every arm is scored on the future half only, against
a no-feedback control. Ground truth drives the simulated analyst and the metrics — never a detector.

Families (the unit feedback generalises over): predicted class, destination port, protocol and matched
rule; for flows no detector flagged, the destination IP as well, so a verdict on one unflagged flow
does not spread across all benign traffic on a port.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from packages.contracts.models import MlPrediction
from packages.detection.fusion.cef import fuse
from packages.detection.guardrail.policy import GuardrailPolicy
from packages.detection.ranking.formulas import (
    EVIDENCE_TO_CLASS,
    FORMULAS,
    MOVEMENTS,
    FamilyState,
    RankingParams,
    apply_verdict,
    queue_class,
    tier2_candidate,
)
from packages.detection.ranking.severity import SeverityChart
from packages.detection.signature.engine import match_all
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_frame
from packages.detection.signature.rule_set import load_rule_set

ERROR_RATES = (0.0, 0.05, 0.15)
SEEDS = (20260911, 20260912, 20260913)
POLICY = GuardrailPolicy()


@dataclass(frozen=True)
class Flow:
    alert_id: str
    order: int
    family: tuple
    evidence_class: str
    detection_score: float
    is_critical: bool
    critical_protected: bool
    infiltration: bool
    attack_class: str | None
    severity: float
    weight: float
    malicious: bool  # ground truth - the simulated analyst and the metrics only


def parse_timestamps(values: pd.Series) -> pd.Series:
    """The corrected release writes ISO 8601 (``2018-03-01 12:15:42.329367``): parse it as ISO,
    never day-first. pandas 3 applies ``dayfirst=True`` even to ISO text and read 1 March as
    3 January, reordering the demo flows (pandas 2 ignored the flag). Unparseable text raises."""
    return pd.to_datetime(values, format="ISO8601")


def load_flows(processed: Path, chart: SeverityChart) -> list[Flow]:
    """Fuse every demo flow with the production engine, in timestamp order."""
    frame = pd.read_csv(processed / "demo_sample.csv",
                        usecols=["alert_id", "attack_class", *OBSERVABLE_FIELDS], low_memory=False)
    frame["_when"] = parse_timestamps(frame["Timestamp"])
    frame = frame.sort_values(["_when", "alert_id"], kind="stable").reset_index(drop=True)
    view = project_frame(frame).drop(columns="id").to_dict("records")
    predictions = json.loads((processed / "demo_ml_predictions_shap.json").read_text("utf-8"))
    rules = [rule for rule in load_rule_set() if rule.enabled]
    flows = []
    for order, (record, alert_id, truth) in enumerate(
            zip(view, frame["alert_id"], frame["attack_class"], strict=True)):
        decision = fuse(match_all(record, rules), MlPrediction.model_validate(predictions[alert_id]))
        attack = decision.attack_category or decision.ml_predicted_class
        rule = decision.signature_rules[0].rule_id if decision.signature_rules else "-"
        family = (attack, record["destinationPort"], record["protocol"], rule)
        if decision.evidence_class == "none":
            family += (record["destinationIp"],)
        flows.append(Flow(
            alert_id=alert_id, order=order, family=family,
            evidence_class=decision.evidence_class, detection_score=decision.combined_score,
            is_critical=decision.is_critical,
            critical_protected=decision.is_critical or any(
                match.severity == "Critical" for match in decision.signature_rules or []),
            infiltration=decision.attack_category == "Infiltration", attack_class=attack,
            severity=chart.severity(attack), weight=chart.weight(attack),
            malicious=truth != "Benign"))
    return flows


def final_score(flow: Flow, adjustment: float, guardrails: bool) -> float:
    """``detection_score + adjustment`` inside the guardrails - the same rules as
    ``guardrail.policy.apply_guardrails`` (a test pins the equivalence), without building an Alert."""
    base = flow.detection_score
    if not guardrails:
        return round(min(100.0, max(0.0, base + adjustment)), 2)
    if flow.evidence_class == "signature_override":
        return base  # I3
    capped = min(POLICY.max_feedback_increase, max(-POLICY.max_feedback_reduction, adjustment))
    score = base + capped
    if capped < 0:
        for protected, floor in ((flow.critical_protected, POLICY.critical_alert_floor),
                                 (flow.infiltration, POLICY.infiltration_alert_floor)):
            if protected and base >= floor and score < floor:
                score = floor
    return round(min(100.0, max(0.0, score)), 2)


def rank(flows: list[Flow], families: dict, guardrails: bool) -> list[tuple]:
    """The queue: (class, -score, alert id), top first. Rows are (class, score, flow)."""
    rows = []
    for flow in flows:
        state = families.get(flow.family)
        score = final_score(flow, state.adjustment if state else 0.0, guardrails)
        tier2 = tier2_candidate(flow.evidence_class, flow.is_critical, score, flow.severity)
        cls = queue_class(flow.evidence_class, state.class_offset if state else 0, tier2,
                          protect=guardrails)
        rows.append((cls, -score, flow.alert_id, score, flow))
    rows.sort(key=lambda row: row[:3])
    return [(cls, score, flow) for cls, _, _, score, flow in rows]


def baseline_class(flow: Flow) -> int:
    tier2 = tier2_candidate(flow.evidence_class, flow.is_critical, flow.detection_score,
                            flow.severity)
    return queue_class(flow.evidence_class, 0, tier2)


def evaluate(flows: list[Flow], families: dict, guardrails: bool) -> dict[str, float]:
    queue = rank(flows, families, guardrails)
    attacks = [position for position, (_, _, flow) in enumerate(queue, 1) if flow.malicious]

    def precision(k: int) -> float:
        return round(sum(flow.malicious for _, _, flow in queue[:k]) / k, 4)

    tier2 = [flow for cls, _, flow in queue if cls == 0]
    return {
        "precision_at_50": precision(50),
        "precision_at_100": precision(100),
        "precision_at_200": precision(200),
        "mean_attack_position": round(statistics.mean(attacks) / len(queue), 4) if attacks else 0,
        "last_attack_position": max(attacks, default=0),
        "benign_in_top_100": sum(not flow.malicious for _, _, flow in queue[:100]),
        "floor_violations": sum(1 for _, score, flow in queue if flow.critical_protected
                                and flow.detection_score >= POLICY.critical_alert_floor
                                and score < POLICY.critical_alert_floor),
        "attacks_demoted": sum(1 for cls, score, flow in queue if flow.malicious and (
            score < flow.detection_score or cls > baseline_class(flow))),
        "tier2_load": len(tier2),
        "tier2_precision": round(sum(f.malicious for f in tier2) / len(tier2), 4) if tier2 else 0,
    }


@dataclass(frozen=True)
class Arm:
    formula: str
    movement: str
    guardrails: bool
    error_rate: float
    seed: int


def calibrate(calibration: list[Flow], arm: Arm, *, rounds: int = 10, batch: int = 25,
              qa_sample: int = 5) -> tuple[dict[tuple, FamilyState], list[dict[str, Any]]]:
    """The calibration phase: a Tier 1 analyst works the queue. Returns the learned family states
    and a log of every verdict (one dict per reviewed alert), so a run can be inspected."""
    rng = random.Random(arm.seed)
    wide = 100.0  # guardrails off: no caps, only the 0-100 range
    params = RankingParams(formula=arm.formula, movement=arm.movement,
                           max_reduction=30.0 if arm.guardrails else wide,
                           max_increase=20.0 if arm.guardrails else wide)
    families: dict[tuple, FamilyState] = defaultdict(FamilyState)
    reviewed: set[str] = set()
    log: list[dict[str, Any]] = []
    for round_no in range(rounds):
        queue = [flow for _, _, flow in rank(calibration, families, arm.guardrails)
                 if flow.alert_id not in reviewed]
        picked = queue[:batch]
        unflagged = [flow for flow in queue[batch:] if flow.evidence_class == "none"]
        picked += rng.sample(unflagged, min(qa_sample, len(unflagged)))  # Tier 1 QA sampling
        for flow in picked:
            reviewed.add(flow.alert_id)
            wrong = rng.random() < arm.error_rate
            says_malicious = flow.malicious != wrong
            entry = {"round": round_no, "alert_id": flow.alert_id, "family": flow.family,
                     "malicious": flow.malicious, "wrong": wrong, "learned": False,
                     "verdict": "confirm_true_positive" if says_malicious
                     else "mark_false_positive"}
            log.append(entry)
            if arm.guardrails and flow.evidence_class == "signature_override":
                continue  # I3: the verdict is routed to the administrator, not learned
            state = families[flow.family]
            entry.update(learned=True, score=final_score(flow, state.adjustment, arm.guardrails),
                         adjustment_before=state.adjustment)
            apply_verdict(state, params, entry["verdict"], entry["score"], flow.weight)
            entry.update(adjustment_after=state.adjustment, class_offset=state.class_offset)
    return families, log


def simulate(calibration: list[Flow], future: list[Flow], arm: Arm, *, rounds: int = 10,
             batch: int = 25, qa_sample: int = 5) -> dict[str, Any]:
    """One arm: a Tier 1 analyst works the calibration queue; the future queue is then scored."""
    families, log = calibrate(calibration, arm, rounds=rounds, batch=batch, qa_sample=qa_sample)
    metrics = evaluate(future, families, arm.guardrails)
    metrics.update(verdicts=sum(e["learned"] for e in log),
                   wrong_verdicts=sum(e["wrong"] for e in log),
                   class_changes=sum(state.class_changes for state in families.values()),
                   future_flows_in_learned_families=sum(
                       1 for flow in future if flow.family in families))
    return {**asdict(arm), **metrics}


SIMPLICITY = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "M1": 0, "M2": 1}
SELECTION_RULE = "sel-2"


def select(aggregates: list[dict]) -> list[dict]:
    """sel-2: rank the guarded (formula, movement) pairs by
    1. safety - no Critical floor violation at any error rate, no attack demoted at 0 % error;
    2. robustness - fewest true attacks demoted under analyst error (5 % plus 15 %);
    3. escalation fidelity - highest Tier 2 precision at 5 % error;
    4. triage efficiency - lowest mean attack position at 5 % error;
    5. stability (fewest class changes), then the simpler formula and movement.

    sel-1 ranked on precision in the top 100 first. On the demo data the no-feedback control and
    every arm score 1.0 there, so it could not discriminate and the class-change tie-break decided
    (run 20260911T111249Z). sel-2 was written after seeing that run; both runs are kept."""
    ranked = []
    for formula in FORMULAS:
        for movement in MOVEMENTS:
            rows = [a for a in aggregates if a["guardrails"] and a["formula"] == formula
                    and a["movement"] == movement]
            realistic = next(a for a in rows if a["error_rate"] == 0.05)
            ranked.append({
                "formula": formula, "movement": movement,
                "safe": all(a["floor_violations"] == 0 for a in rows)
                and all(a["attacks_demoted"] == 0 for a in rows if a["error_rate"] == 0),
                "attacks_demoted_under_error": round(sum(
                    a["attacks_demoted"] for a in rows if a["error_rate"] > 0), 4),
                "tier2_precision": realistic["tier2_precision"],
                "tier2_load": realistic["tier2_load"],
                "mean_attack_position": realistic["mean_attack_position"],
                "precision_at_100": realistic["precision_at_100"],
                "class_changes": realistic["class_changes"],
            })
    ranked.sort(key=lambda r: (not r["safe"], r["attacks_demoted_under_error"],
                               -r["tier2_precision"], r["mean_attack_position"],
                               r["class_changes"], SIMPLICITY[r["formula"]],
                               SIMPLICITY[r["movement"]]))
    return ranked


def aggregate(runs: list[dict]) -> list[dict]:
    """Mean of every metric over seeds, per (formula, movement, guardrails, error rate)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for run in runs:
        groups[(run["formula"], run["movement"], run["guardrails"], run["error_rate"])].append(run)
    out = []
    for (formula, movement, guardrails, error_rate), rows in sorted(groups.items()):
        metrics = {key: round(statistics.mean(r[key] for r in rows), 4) for key in rows[0]
                   if key not in ("formula", "movement", "guardrails", "error_rate", "seed")}
        out.append({"formula": formula, "movement": movement, "guardrails": guardrails,
                    "error_rate": error_rate, "seeds": len(rows), **metrics})
    return out


def run_experiment(processed: Path, chart: SeverityChart, *, seeds=SEEDS,
                   error_rates=ERROR_RATES, rounds: int = 10, batch: int = 25,
                   qa_sample: int = 5) -> dict[str, Any]:
    flows = load_flows(processed, chart)
    half = len(flows) // 2
    calibration, future = flows[:half], flows[half:]
    runs = [simulate(calibration, future, Arm(formula, movement, guardrails, error_rate, seed),
                     rounds=rounds, batch=batch, qa_sample=qa_sample)
            for formula in FORMULAS for movement in MOVEMENTS for guardrails in (True, False)
            for error_rate in error_rates for seed in seeds]
    aggregates = aggregate(runs)
    return {
        "config": {"flows": len(flows), "calibration": len(calibration), "future": len(future),
                   "calibration_attacks": sum(f.malicious for f in calibration),
                   "future_attacks": sum(f.malicious for f in future),
                   "severity_chart": chart.version, "seeds": list(seeds),
                   "error_rates": list(error_rates), "rounds": rounds, "batch": batch,
                   "qa_sample": qa_sample, "selection_rule": SELECTION_RULE,
                   "params": asdict(RankingParams()),
                   "evidence_to_class": EVIDENCE_TO_CLASS},
        "control": evaluate(future, {}, True),
        "runs": runs,
        "aggregates": aggregates,
        "selection": select(aggregates),
    }
