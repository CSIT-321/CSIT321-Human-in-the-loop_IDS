"""Similar-alert learning (plan step S7b): a verdict on one alert moves the alerts like it.

The project's goal (changelog v1.11) is that analyst feedback on past alerts reorders *future*
alerts. S7a applies a verdict to its own alert; this module carries it to the alert's **family**,
including members that arrive after the verdict. Every choice below was made by experiment
(``docs/ranking-and-escalation-design.md`` §6, notebooks 05-06), and it is built from the
experiment's own functions (``ranking.formulas``), so what runs is the design that was tested:

    family     the coarse key (sel-3): attack class, destination port, protocol, first matched
               rule - plus the destination IP for a flow no detector flagged, so a verdict on one
               unflagged flow cannot spread across all benign traffic on a port. Values are
               canonicalised as stage-5/core/similarity-engine.js does (protocol 6 == "TCP").
    learning   formula C1 (Q29) and movement M1: ``formulas.apply_verdict`` replayed over the
               family's *effective* verdicts - each member's latest, oldest first - so an amended
               verdict counts once (the collaborator's resolveEffectiveFeedbackEvents).
    gate       Q30, the collaborator's checkAdaptationEligibility, counted **by category** as their
               engine counts: at least ``min_feedback_count`` learning verdicts, no tie, and the
               dominant category holding at least ``min_agreement_ratio`` of them. Only learning
               that points the dominant way reaches the queue (``formulas.effective``). Expected
               activity does not propagate unless enabled, and then only past a stricter gate.
    placement  a member with no verdict of its own scores ``detection_score`` + the family's
               applied adjustment inside the S7a guardrails, and moves by the applied class offset.
               A member's own verdict takes priority over its family's (feedback-engine.js).

Decided in changelog v1.14:

* ``escalate`` counts as a confirmation - the design's match result S = 1. The collaborator's
  engine treats it as a workflow type that teaches nothing.
* A ``signature_override`` alert neither teaches its family nor learns from it, and never leaves
  its queue band (I3).
* The collaborator's weighted similarity (threshold 0.7) is not ported. The experiment that chose
  the formula and the gate grouped by exact family, which scores 1.0 under their weights.
* An alert's own verdict places it: E2 (escalate, or confirm on a type of severity >= 7) makes it a
  Tier 2 candidate; any other confirmation promotes it one band (M1); a dismissal withdraws its
  Tier 2 candidacy - that is the Tier 1 decision - but moves it no lower, because clearing an alert
  is a status change, not a score change.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from packages.contracts import models as m
from packages.detection.guardrail.policy import GuardrailPolicy, apply_guardrails
from packages.detection.ranking.formulas import (
    CONFIRMING,
    DISMISSING,
    QUEUE_CLASSES,
    TIER2_SEVERITY,
    FamilyState,
    RankingParams,
    apply_verdict,
    queue_class,
    tier2_candidate,
)
from packages.detection.ranking.severity import SeverityChart

SCHEME = "s7b-c1-m1-category-gate"
# A verdict's category as the gate counts it. needs_investigation is absent: it teaches nothing.
LEARNING_CATEGORY: dict[str, m.LearningCategory] = {
    "confirm_true_positive": "confirm_true_positive",
    "escalate": "confirm_true_positive",
    "mark_false_positive": "mark_false_positive",
    "mark_expected_activity": "mark_expected_activity",
}
PROTOCOL_NAMES = {"0": "hopopt", "1": "icmp", "6": "tcp", "17": "udp"}  # similarity-engine.js
NO_RULE = "-"
WIDE = 100.0  # guardrails off: only the 0-100 score range bounds a family's learning


# --------------------------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------------------------


def attack_of(alert: m.Alert) -> str | None:
    """The attack class an alert asserts: fusion's category, else the model's prediction."""
    return alert.attack_category or alert.ml_predicted_class


def family_key(attack: str | None, dst_port: int | str, protocol: int | str,
               rule_id: str | None, dst_ip: str, evidence_class: str) -> str:
    """The coarse family key, as canonical JSON text: ``["Web Attack",80,"tcp","-"]``."""
    proto = str(protocol).strip().lower()
    parts: list[Any] = [attack, int(dst_port), PROTOCOL_NAMES.get(proto, proto),
                        rule_id or NO_RULE]
    if evidence_class == "none":
        parts.append(str(dst_ip).strip())
    return json.dumps(parts, separators=(",", ":"))


#: The key's fields, in the order `family_key` writes them. The fifth is present only for a flow no
#: detector flagged, which is why this is a tuple and not a fixed-width record.
FAMILY_FIELDS = ("attack_category", "dst_port", "protocol", "rule_id", "dst_ip")


def parse_family_key(key: str | None) -> dict[str, Any] | None:
    """The key read back as named fields — the inverse of ``family_key``.

    The key is written as positional JSON because it is an identity, not a document; but "what makes
    these alerts similar" is a question an analyst is entitled to have answered on screen, and
    ``["Brute Force",21,"tcp","SIG-FTP-BRUTE-FORCE"]`` does not answer it. Parsing lives here,
    beside the function that writes it, so the two cannot drift.

    Returns ``None`` for a key that is absent or not in this scheme, never a partial guess.
    """
    if not key:
        return None
    try:
        parts = json.loads(key)
    except (TypeError, ValueError):
        return None
    if not isinstance(parts, list) or not 4 <= len(parts) <= len(FAMILY_FIELDS):
        return None
    fields: dict[str, Any] = dict(zip(FAMILY_FIELDS, parts, strict=False))
    if fields.get("rule_id") == NO_RULE:
        fields["rule_id"] = None
    return {name: fields.get(name) for name in FAMILY_FIELDS}


def family_label(key: str | None) -> str:
    """The key as a person reads it: ``Brute Force · port 21 · tcp · SIG-FTP-BRUTE-FORCE``."""
    fields = parse_family_key(key)
    if fields is None:
        return ""
    parts = [str(fields["attack_category"] or "Unflagged"), f"port {fields['dst_port']}",
             str(fields["protocol"])]
    if fields["rule_id"]:
        parts.append(str(fields["rule_id"]))
    if fields["dst_ip"]:
        parts.append(f"to {fields['dst_ip']}")
    return " · ".join(parts)


def family_key_of(alert: m.Alert, flow: m.FlowRecord) -> str:
    """An alert's family, from the alert and its flow - what S9 stores in ``alerts.family_key``."""
    rule = alert.signature_rules[0].rule_id if alert.signature_rules else None
    return family_key(attack_of(alert), flow.dst_port, flow.protocol, rule, flow.dst_ip,
                      alert.evidence_class)


# --------------------------------------------------------------------------------------------
# The agreement gate (Q30)
# --------------------------------------------------------------------------------------------


class LearningPolicy(m.Contract):
    """The gate's settings. The first two load from ``guardrail_config`` (NFR-08); the rest are
    ``aggregation.expectedActivity`` in stage-5/config/adaptation-config.json."""

    min_feedback_count: int = Field(
        default=int(m.GUARDRAIL_DEFAULTS["aggregation_min_feedback_count"][0]), ge=1)
    min_agreement_ratio: m.Probability = m.GUARDRAIL_DEFAULTS["aggregation_min_agreement_ratio"][0]
    expected_activity_propagates: bool = False
    expected_activity_min_count: int = Field(default=5, ge=1)
    expected_activity_min_agreement: m.Probability = 0.9

    @classmethod
    def from_rows(cls, rows: Mapping[str, float]) -> LearningPolicy:
        settings: dict[str, Any] = {}
        if "aggregation_min_feedback_count" in rows:
            settings["min_feedback_count"] = int(rows["aggregation_min_feedback_count"])
        if "aggregation_min_agreement_ratio" in rows:
            settings["min_agreement_ratio"] = rows["aggregation_min_agreement_ratio"]
        return cls(**settings)


@dataclass(frozen=True)
class Gate:
    open: bool
    dominant: m.LearningCategory | None
    agreement: float
    reason: str


def dominant_category(counts: Mapping[str, int]) -> tuple[str | None, float]:
    """chooseDominantFeedback: the most frequent category and its share, rounded to 4 places as
    the collaborator rounds it (so 2 of 3 is 0.6667). A tie has no dominant category."""
    present = {category: n for category, n in counts.items() if n > 0}
    if not present:
        return None, 0.0
    top = max(present.values())
    winners = [category for category, n in present.items() if n == top]
    return (winners[0] if len(winners) == 1 else None), round(top / sum(present.values()), 4)


def gate(counts: Mapping[str, int], policy: LearningPolicy) -> Gate:
    """checkAdaptationEligibility, with expectedActivityEligible, on a family's category counts.
    The collaborator's exact-context fields (protocol, port, rule) are part of the family key, so
    every member already passes that check."""
    total = sum(counts.values())
    dominant, share = dominant_category(counts)
    if total == 0:
        return Gate(False, None, 0.0, "cold start: no learning verdicts in this family")
    if total < policy.min_feedback_count:
        return Gate(False, dominant, share, f"not enough learning verdicts: {total} of "
                                            f"{policy.min_feedback_count} required")
    if dominant is None:
        return Gate(False, None, share, "the verdicts conflict: no dominant category")
    if share < policy.min_agreement_ratio:
        return Gate(False, dominant, share,
                    f"agreement {share} is below {policy.min_agreement_ratio}")
    if dominant == "mark_expected_activity":
        if not policy.expected_activity_propagates:
            return Gate(False, dominant, share,
                        "expected activity does not propagate to similar alerts")
        if (total < policy.expected_activity_min_count
                or share < policy.expected_activity_min_agreement):
            return Gate(False, dominant, share, (
                f"expected activity needs {policy.expected_activity_min_count} verdicts at "
                f"agreement >= {policy.expected_activity_min_agreement}"))
    return Gate(True, dominant, share, f"{counts[dominant]} of {total} verdicts agree: {dominant}")


# --------------------------------------------------------------------------------------------
# A family's learning (Q29: formula C1, movement M1)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FamilyLearning:
    counts: dict[str, int]
    gate: Gate
    learned_adjustment: float
    learned_offset: int
    applied_adjustment: float
    applied_offset: int


def ranking_params(policy: GuardrailPolicy) -> RankingParams:
    """C1 + M1, bounded by the guardrail caps - or, with guardrails off, only by the score range,
    as in the experiment's guardrails-off arms."""
    if not policy.active:
        return RankingParams(formula="C1", movement="M1", max_reduction=WIDE, max_increase=WIDE)
    return RankingParams(formula="C1", movement="M1", max_reduction=policy.max_feedback_reduction,
                         max_increase=policy.max_feedback_increase)


def learn(categories: Iterable[str], weight: float, policy: GuardrailPolicy,
          learning: LearningPolicy) -> FamilyLearning:
    """A family's learning from its members' effective verdicts, oldest first. Pure."""
    params = ranking_params(policy)
    state, counts = FamilyState(), Counter()
    for category in categories:
        learned = LEARNING_CATEGORY.get(category)
        if learned is None:
            continue
        apply_verdict(state, params, learned, 0.0, weight)  # C1's step ignores the score
        counts[learned] += 1
    decision = gate(counts, learning)
    adjustment, offset = 0.0, 0
    if decision.open:
        # As formulas.effective: only learning that points the dominant way reaches the queue.
        direction = 1 if decision.dominant == "confirm_true_positive" else -1
        adjustment = state.adjustment if state.adjustment * direction > 0 else 0.0
        offset = state.class_offset if -state.class_offset * direction > 0 else 0  # promotion < 0
    return FamilyLearning(dict(counts), decision, round(state.adjustment, 4), state.class_offset,
                          round(adjustment, 4), offset)


# --------------------------------------------------------------------------------------------
# Placement: where an alert sits in the queue
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """An alert's score, queue band and review flag, and the guardrail decision behind the score
    (None when no change was proposed)."""

    score: float
    queue_class: m.QueueClass
    requires_review: bool
    outcome: m.GuardrailOutcome | None = None

    @property
    def queue_priority(self) -> int:
        return m.QUEUE_PRIORITY[self.queue_class]


def fusion_review(alert: m.Alert, score: float, critical_threshold: float) -> bool:
    """S6's review rule, re-applied to a new score."""
    if alert.evidence_class == "signature_override" or alert.ml_predicted_class is None:
        return True
    return alert.evidence_class in ("corroborated", "ml_only") and score >= critical_threshold


def _meets_e1_or_e3(alert: m.Alert, score: float, chart: SeverityChart) -> bool:
    return tier2_candidate(alert.evidence_class, alert.is_critical, score,
                           chart.severity(attack_of(alert)))


def _band(alert: m.Alert, offset: int, tier2: bool, policy: GuardrailPolicy) -> m.QueueClass:
    if alert.evidence_class == "signature_override":
        return "signature_override"  # I3: a disputed rule goes to the administrator, not Tier 2
    return QUEUE_CLASSES[queue_class(alert.evidence_class, offset, tier2, protect=policy.active)]


def member_placement(alert: m.Alert, adjustment: float, offset: int, chart: SeverityChart,
                     policy: GuardrailPolicy) -> Placement:
    """A family member with no verdict of its own: ``detection_score`` + the family's applied
    adjustment inside the guardrails, moved by the applied class offset. Pure."""
    if alert.evidence_class == "signature_override":  # I3: frozen, whatever its family learned
        return Placement(alert.detection_score, "signature_override", True)
    outcome = apply_guardrails(alert, adjustment, policy) if adjustment else None
    score = outcome.score_after if outcome is not None else alert.detection_score
    review = ((outcome is not None and outcome.requires_review)
              or fusion_review(alert, score, policy.critical_alert_threshold))
    return Placement(score, _band(alert, offset, _meets_e1_or_e3(alert, score, chart), policy),
                     review, outcome)


def detection_placement(alert: m.Alert, chart: SeverityChart,
                        policy: GuardrailPolicy | None = None) -> Placement:
    """Where detection puts an alert before any feedback: its evidence band, or the Tier 2 band
    when it meets E1 or E3. S9 stores this at ingest."""
    return member_placement(alert, 0.0, 0, chart, policy if policy is not None
                            else GuardrailPolicy())


def verdict_queue_class(alert: m.Alert, category: str, score: float, chart: SeverityChart,
                        policy: GuardrailPolicy) -> m.QueueClass:
    """The band of an alert with its own verdict, at the score S7a gave it."""
    if alert.evidence_class == "signature_override":
        return "signature_override"
    if category == "escalate" or (category == "confirm_true_positive"
                                  and chart.severity(attack_of(alert)) >= TIER2_SEVERITY):
        return "tier2_candidate"  # E2
    tier2 = category not in DISMISSING and _meets_e1_or_e3(alert, score, chart)
    offset = -1 if category in CONFIRMING else 0  # M1: a confirmation promotes one band
    return _band(alert, offset, tier2, policy)
