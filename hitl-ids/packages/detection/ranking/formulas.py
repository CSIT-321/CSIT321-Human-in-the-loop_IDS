"""The candidate ranking formulas and class movement (docs/ranking-and-escalation-design.md §5).

A verdict on one alert updates its **family's** learned adjustment; every member of the family —
including future alerts the analyst never sees — is then scored ``detection_score + adjustment``,
inside the guardrails. That is how feedback reorders future alerts (the confirmed project goal).

    C0  fixed step            the S7a engine's values: +10 / +15 / -30 / -15
    C1  severity-weighted     up +K*w, down -K*(1 - w)
    C2  Elo-style             delta = K_dir * (S - E); E = score/100;
                              K_up = K*(0.5 + 0.5w), K_down = K*(1 - 0.5w)
    C3  Elo + uncertainty     C2 * max(0.4, 1 / sqrt(1 + n/3)) for a family with n prior verdicts

    M1  one class at a time: a confirming verdict promotes one class; dismissals demote one class
        only after ``demotion_shield`` of them (hysteresis, as a ranked ladder's demotion shield)
    M2  a confirming verdict moves the family straight to the top class; demotion as M1

Queue classes, top to bottom (decision Q24/Q25): Tier 2 candidates, corroborated,
signature_override, ml_only, none. ``evidence_class`` never changes; movement is a separate offset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CONFIRMING = frozenset({"confirm_true_positive", "escalate"})
DISMISSING = frozenset({"mark_false_positive", "mark_expected_activity"})
FIXED_STEPS = {"confirm_true_positive": 10.0, "escalate": 15.0,
               "mark_false_positive": -30.0, "mark_expected_activity": -15.0}
FORMULAS = ("C0", "C1", "C2", "C3")
MOVEMENTS = ("M1", "M2")
QUEUE_CLASSES = ("tier2_candidate", "corroborated", "signature_override", "ml_only", "none")
EVIDENCE_TO_CLASS = {"corroborated": 1, "signature_override": 2, "ml_only": 3, "none": 4}
TIER2_SEVERITY = 7.0   # E2/E3: High or above on the CVSS scale
TIER2_SCORE = 90.0     # E3


@dataclass(frozen=True)
class RankingParams:
    formula: str = "C2"
    movement: str = "M1"
    k: float = 30.0                 # the largest step; equals the guardrail's maximum reduction
    max_reduction: float = 30.0     # the family adjustment's bounds - the guardrail caps
    max_increase: float = 20.0
    demotion_shield: int = 2        # dismissals needed before a class drop
    uncertainty_floor: float = 0.4  # C3

    def __post_init__(self) -> None:
        if self.formula not in FORMULAS or self.movement not in MOVEMENTS:
            raise ValueError(f"unknown formula/movement {self.formula}/{self.movement}")


@dataclass
class FamilyState:
    adjustment: float = 0.0
    verdicts: int = 0
    class_offset: int = 0
    dismissals_since_move: int = 0
    class_changes: int = 0


def verdict_delta(params: RankingParams, category: str, score: float, weight: float,
                  verdicts: int = 0) -> float:
    """The change one verdict makes to its family's learned adjustment."""
    if category not in CONFIRMING | DISMISSING:
        return 0.0
    if params.formula == "C0":
        return FIXED_STEPS[category]
    up = category in CONFIRMING
    if params.formula == "C1":
        return params.k * weight if up else -params.k * (1 - weight)
    expected = min(1.0, max(0.0, score / 100))
    k_dir = params.k * (0.5 + 0.5 * weight) if up else params.k * (1 - 0.5 * weight)
    delta = k_dir * ((1.0 if up else 0.0) - expected)
    if params.formula == "C3":
        delta *= max(params.uncertainty_floor, 1 / math.sqrt(1 + verdicts / 3))
    return delta


def apply_verdict(state: FamilyState, params: RankingParams, category: str, score: float,
                  weight: float) -> FamilyState:
    """Update a family in place: its learned adjustment, then its class offset."""
    if category not in CONFIRMING | DISMISSING:
        return state
    delta = verdict_delta(params, category, score, weight, state.verdicts)
    state.adjustment = min(params.max_increase,
                           max(-params.max_reduction, state.adjustment + delta))
    state.verdicts += 1
    before = state.class_offset
    if category in CONFIRMING:
        state.dismissals_since_move = 0
        state.class_offset = -len(QUEUE_CLASSES) if params.movement == "M2" else before - 1
    else:
        state.dismissals_since_move += 1
        if state.dismissals_since_move >= params.demotion_shield:
            state.class_offset = before + 1
            state.dismissals_since_move = 0
    state.class_offset = max(-len(QUEUE_CLASSES), min(len(QUEUE_CLASSES), state.class_offset))
    if state.class_offset != before:
        state.class_changes += 1
    return state


def tier2_candidate(evidence_class: str, is_critical: bool, score: float, severity: float) -> bool:
    """Escalation criteria E1 and E3 (E2 - an analyst's verdict - acts through promotion)."""
    return ((evidence_class == "corroborated" and is_critical)
            or (score >= TIER2_SCORE and severity >= TIER2_SEVERITY))


def queue_class(evidence_class: str, offset: int, tier2: bool, protect: bool = True) -> int:
    """Index into QUEUE_CLASSES. With ``protect``, a detector-flagged alert never drops into the
    unflagged ``none`` band (tier-loss protection)."""
    base = 0 if tier2 else EVIDENCE_TO_CLASS[evidence_class]
    lowest = 3 if (protect and evidence_class != "none") else len(QUEUE_CLASSES) - 1
    return min(lowest, max(0, base + offset))
