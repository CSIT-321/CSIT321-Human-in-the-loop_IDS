"""Grouped verdict vs family learning: what one human decision does when it counts once vs once per member.

Uses the approved engine's own functions (C1 + M1 + the category gate) with the live defaults.
Family: Brute Force (CVSS 5.0 -> weight 0.5), the SSH family from spike B (94,207 members).
"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS\hitl-ids")
from packages.detection.feedback.learning import LearningPolicy, gate  # noqa: E402
from packages.detection.guardrail.policy import GuardrailPolicy  # noqa: E402
from packages.detection.ranking.formulas import FamilyState, RankingParams, apply_verdict, effective  # noqa: E402

g = GuardrailPolicy()
params = RankingParams(formula="C1", movement="M1", max_reduction=g.max_feedback_reduction,
                       max_increase=g.max_feedback_increase)
policy = LearningPolicy()
WEIGHT = 0.5
print(f"live settings: gate {policy.min_feedback_count} verdicts at {policy.min_agreement_ratio}; "
      f"caps +{params.max_increase}/-{params.max_reduction}; C1 step up {params.k * WEIGHT:+.1f}, "
      f"down {-params.k * (1 - WEIGHT):+.1f}")


def run(label, verdicts):
    s = FamilyState()
    counts = {}
    for cat in verdicts:
        apply_verdict(s, params, cat, 0.0, WEIGHT)
        key = "confirm_true_positive" if cat in ("confirm_true_positive", "escalate") else cat
        counts[key] = counts.get(key, 0) + 1
    gt = gate(counts, policy)
    adj, off = effective(s, gated=False) if gt.open else (0.0, 0)
    print(f"{label:<58} verdicts={sum(counts.values()):>4} gate={'OPEN' if gt.open else 'shut'}  "
          f"family moves {adj:+6.1f} pts, {off:+d} band(s)")


for cat, word in (("confirm_true_positive", "confirm"), ("mark_false_positive", "false positive")):
    print(f"\n-- one analyst, one {word} decision on a group of 190 --")
    run("counted ONCE (recorded design)", [cat])
    run("counted once PER MEMBER (190 verdicts)", [cat] * 190)
    print(f"-- three independent {word} decisions, each counted once --")
    run("3 decisions (the gate's design case)", [cat] * 3)
    run("10 decisions", [cat] * 10)
