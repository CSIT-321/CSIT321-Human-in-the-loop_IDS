"""The ranking selection experiment (docs/ranking-and-escalation-design.md §6).

Past versus future. The demo flows are ordered by timestamp; the first half is **calibration**, where a
simulated Tier 1 analyst reviews the top of the queue each round and gives verdicts, and the second
half is **future** traffic the analyst never sees. Every arm is scored on the future half only, against
a no-feedback control. Ground truth drives the simulated analyst and the metrics — never a detector.

Families (the unit feedback generalises over). The *coarse* key is predicted class, destination port,
protocol and matched rule - close to the fields the collaborator's similarity engine weights - plus
the destination IP for flows no detector flagged, so a verdict on one unflagged flow does not spread
across all benign traffic on a port. The *fine* key adds the destination IP for every flow.

Run 3 adds two arm dimensions after run 2's trace (changelog v1.12): the agreement gate
(``formulas.effective``) and the fine family key.
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
    GATE_MIN_AGREEMENT,
    GATE_MIN_FEEDBACK,
    MOVEMENTS,
    FamilyState,
    RankingParams,
    apply_verdict,
    effective,
    queue_class,
    tier2_candidate,
)
from packages.detection.ranking.severity import SeverityChart
from packages.detection.signature.engine import match_all
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_frame
from packages.detection.signature.rule_set import load_rule_set

ERROR_RATES = (0.0, 0.05, 0.15)
SEEDS = (20260911, 20260912, 20260913)
FAMILY_KEYS = ("coarse", "fine")
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


def family_key(attack: str | None, port: Any, protocol: Any, rule: str, destination_ip: Any,
               evidence_class: str, key: str = "coarse") -> tuple:
    """coarse: class, port, protocol, rule - plus the destination IP when no detector flagged the
    flow. fine: the destination IP for every flow."""
    if key not in FAMILY_KEYS:
        raise ValueError(f"unknown family key {key!r}")
    family = (attack, port, protocol, rule)
    if key == "fine" or evidence_class == "none":
        family += (destination_ip,)
    return family


def load_flows(processed: Path, chart: SeverityChart, key: str = "coarse") -> list[Flow]:
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
        flows.append(Flow(
            alert_id=alert_id, order=order,
            family=family_key(attack, record["destinationPort"], record["protocol"], rule,
                              record["destinationIp"], decision.evidence_class, key),
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


def rank(flows: list[Flow], families: dict, guardrails: bool, gated: bool = False) -> list[tuple]:
    """The queue: (class, -score, alert id), top first. Rows are (class, score, flow)."""
    rows = []
    for flow in flows:
        state = families.get(flow.family)
        adjustment, offset = effective(state, gated) if state else (0.0, 0)
        score = final_score(flow, adjustment, guardrails)
        tier2 = tier2_candidate(flow.evidence_class, flow.is_critical, score, flow.severity)
        cls = queue_class(flow.evidence_class, offset, tier2, protect=guardrails)
        rows.append((cls, -score, flow.alert_id, score, flow))
    rows.sort(key=lambda row: row[:3])
    return [(cls, score, flow) for cls, _, _, score, flow in rows]


def baseline_class(flow: Flow) -> int:
    tier2 = tier2_candidate(flow.evidence_class, flow.is_critical, flow.detection_score,
                            flow.severity)
    return queue_class(flow.evidence_class, 0, tier2)


def evaluate(flows: list[Flow], families: dict, guardrails: bool,
             gated: bool = False) -> dict[str, float]:
    queue = rank(flows, families, guardrails, gated)
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
    gated: bool = False
    family_key: str = "coarse"


ARM_FIELDS = ("formula", "movement", "guardrails", "gated", "family_key", "error_rate")


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
        queue = [flow for _, _, flow in rank(calibration, families, arm.guardrails, arm.gated)
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
            shown, _ = effective(state, arm.gated)  # the score the analyst is looking at
            entry.update(learned=True, score=final_score(flow, shown, arm.guardrails),
                         adjustment_before=state.adjustment)
            apply_verdict(state, params, entry["verdict"], entry["score"], flow.weight)
            entry.update(adjustment_after=state.adjustment, class_offset=state.class_offset)
    return families, log


def simulate(calibration: list[Flow], future: list[Flow], arm: Arm, *, rounds: int = 10,
             batch: int = 25, qa_sample: int = 5) -> dict[str, Any]:
    """One arm: a Tier 1 analyst works the calibration queue; the future queue is then scored."""
    families, log = calibrate(calibration, arm, rounds=rounds, batch=batch, qa_sample=qa_sample)
    metrics = evaluate(future, families, arm.guardrails, arm.gated)
    metrics.update(verdicts=sum(e["learned"] for e in log),
                   wrong_verdicts=sum(e["wrong"] for e in log),
                   class_changes=sum(state.class_changes for state in families.values()),
                   future_flows_in_learned_families=sum(
                       1 for flow in future if flow.family in families))
    return {**asdict(arm), **metrics}


SIMPLICITY = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "M1": 0, "M2": 1, "coarse": 0, "fine": 1}
SEVERITY_SCALED = frozenset({"C1", "C2", "C3"})  # Q27: the step depends on the attack's severity
SELECTION_RULE = "sel-3"


def select(aggregates: list[dict]) -> list[dict]:
    """sel-3, fixed before run 3 was executed. Candidates: the guarded, gated arms - the design S7b
    will build - for every formula, movement and family key. Ranked by
    1. Q27 - the step must depend on the attack type's severity (C0's fixed steps do not);
    2. safety - no Critical floor violation at any error rate, no attack demoted at 0 % error;
    3. robustness - fewest true attacks demoted under analyst error (5 % plus 15 %);
    4. escalation fidelity - highest Tier 2 precision at 5 % error;
    5. triage efficiency - lowest mean attack position at 5 % error;
    6. stability - fewest class changes at 5 % error;
    7. the simpler formula, movement and family key.

    History: sel-1 (run 20260911T111249Z) ranked on precision in the top 100, which the control
    already saturates. sel-2 (run 20260911T111625Z) was written after run 1, and its deciding
    metric traced to one family collision, so it did not choose the formula (changelog v1.12)."""
    ranked = []
    for formula in FORMULAS:
        for movement in MOVEMENTS:
            for key in FAMILY_KEYS:
                rows = [a for a in aggregates if a["guardrails"] and a["gated"]
                        and a["formula"] == formula and a["movement"] == movement
                        and a["family_key"] == key]
                if not rows:
                    continue
                realistic = next(a for a in rows if a["error_rate"] == 0.05)
                ranked.append({
                    "formula": formula, "movement": movement, "family_key": key,
                    "meets_q27": formula in SEVERITY_SCALED,
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
    ranked.sort(key=lambda r: (not r["meets_q27"], not r["safe"], r["attacks_demoted_under_error"],
                               -r["tier2_precision"], r["mean_attack_position"],
                               r["class_changes"], SIMPLICITY[r["formula"]],
                               SIMPLICITY[r["movement"]], SIMPLICITY[r["family_key"]]))
    return ranked


def aggregate(runs: list[dict]) -> list[dict]:
    """Mean of every metric over seeds, per arm (every field of ``Arm`` except the seed)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for run in runs:
        groups[tuple(run[field] for field in ARM_FIELDS)].append(run)
    out = []
    for key, rows in sorted(groups.items()):
        metrics = {name: round(statistics.mean(r[name] for r in rows), 4) for name in rows[0]
                   if name not in ARM_FIELDS and name != "seed"}
        out.append({**dict(zip(ARM_FIELDS, key)), "seeds": len(rows), **metrics})
    return out


def run_experiment(processed: Path, chart: SeverityChart, *, seeds=SEEDS,
                   error_rates=ERROR_RATES, rounds: int = 10, batch: int = 25,
                   qa_sample: int = 5) -> dict[str, Any]:
    flows = {key: load_flows(processed, chart, key) for key in FAMILY_KEYS}
    half = len(flows["coarse"]) // 2
    split = {key: (keyed[:half], keyed[half:]) for key, keyed in flows.items()}
    runs = [simulate(*split[key], Arm(formula, movement, guardrails, error_rate, seed, gated, key),
                     rounds=rounds, batch=batch, qa_sample=qa_sample)
            for key in FAMILY_KEYS for gated in (False, True) for formula in FORMULAS
            for movement in MOVEMENTS for guardrails in (True, False)
            for error_rate in error_rates for seed in seeds]
    aggregates = aggregate(runs)
    calibration, future = split["coarse"]
    return {
        "config": {"flows": len(flows["coarse"]), "calibration": len(calibration),
                   "future": len(future),
                   "calibration_attacks": sum(f.malicious for f in calibration),
                   "future_attacks": sum(f.malicious for f in future),
                   "severity_chart": chart.version, "seeds": list(seeds),
                   "error_rates": list(error_rates), "rounds": rounds, "batch": batch,
                   "qa_sample": qa_sample, "selection_rule": SELECTION_RULE,
                   "family_keys": list(FAMILY_KEYS),
                   "gate": {"min_feedback": GATE_MIN_FEEDBACK,
                            "min_agreement": GATE_MIN_AGREEMENT,
                            "source": "stage-5/config/adaptation-config.json, aggregation"},
                   # The space that was searched, not a set of defaults. This key used to hold
                   # ``asdict(RankingParams())`` — the dataclass's own defaults (C2/M1) — which read
                   # as "the parameters used" while describing nothing that ran: the arms executed
                   # are enumerated above, each records its own values in ``runs[]``, and the winner
                   # is ``selection[0]``. Recorded per run so a reader can see what was compared.
                   "candidate_space": {
                       "formulas": list(FORMULAS), "movements": list(MOVEMENTS),
                       "family_keys": list(FAMILY_KEYS),
                       "chosen_by_rule": "selection[0]; see METHOD.md for any lead override"},
                   "evidence_to_class": EVIDENCE_TO_CLASS},
        "control": evaluate(future, {}, True),
        "runs": runs,
        "aggregates": aggregates,
        "selection": select(aggregates),
    }
