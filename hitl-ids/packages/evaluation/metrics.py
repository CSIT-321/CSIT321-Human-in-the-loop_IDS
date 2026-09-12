"""What an arm is measured by (plan step S15, task 3).

Every function here reads one arm's database and returns numbers. None of them writes, and none of
them knows which arm it is looking at - the comparison is the harness's job, so a metric cannot
quietly treat the treatment arm differently from the control.

Four families of measurement, and they answer different questions:

``detection_metrics``
    Per-class precision/recall/F1/FPR/FNR of the *detection decision*. Feedback never touches
    ``attack_category`` or ``evidence_class``, so these must come out **identical in all three
    arms**; the harness asserts it. That is not a formality - it is the proof that the treatment
    arm changed the queue and not the detector, which is the difference between reordering alerts
    and retraining a model behind the examiner's back.

``queue_metrics``
    What the analyst actually experiences: what fraction of the first k alerts are real, and how
    far down the true positives sit. This is where a feedback effect, if there is one, appears.
    Mean reciprocal rank is defined here as the mean of 1/rank over **every** true positive, not
    the classic "first relevant hit" MRR - the analyst works the whole queue, not just its head.

``movement_metrics``
    The S7b claim, measured directly: how many alerts moved, split into the ones the analyst
    judged, the **untouched members of judged families** (the alerts the claim is about), and
    everything else (which should be nothing).

``safety_metrics``
    What the guardrails did: cap and reject counts, the Critical floor, and - reported separately,
    as the plan requires - ``signature_override`` preservation, invariant I3.

Ranks are 1-based positions in the contract's queue order. "True positive" always means ground
truth says the flow was an attack, reached only through ``flow_data.source_record_id``.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Any

from packages.evaluation.truth import GroundTruth

#: The cut-offs the report quotes. 50 is the plan's headline ("Delta FP in top-50").
PRECISION_AT = (10, 25, 50, 100, 200)

#: The queue's order, qualified for a join against flow_data.
QUEUE_ORDER_QUALIFIED = "a.queue_priority ASC, a.combined_score DESC, a.id ASC"


@dataclass(frozen=True)
class QueuedAlert:
    """One alert as the queue presents it, with the answer attached."""

    alert_id: int
    rank: int
    source_record_id: str
    queue_class: str
    evidence_class: str
    combined_score: float
    detection_score: float
    predicted_class: str | None
    is_critical: bool
    requires_review: bool
    family_key: str | None
    truth_class: str

    @property
    def malicious(self) -> bool:
        return self.truth_class != "Benign"

    @property
    def predicted_attack(self) -> str:
        """The detector's class as a label comparable with ground truth: no class means benign."""
        return self.predicted_class or "Benign"


def read_queue(conn: sqlite3.Connection, truth: GroundTruth) -> list[QueuedAlert]:
    """Every alert in queue order, ranked from 1, with its ground truth joined on."""
    rows = conn.execute(
        "SELECT a.id, a.queue_class, a.evidence_class, a.combined_score, a.detection_score, "
        "a.attack_category, a.is_critical, a.requires_review, a.family_key, f.source_record_id "
        "FROM alerts a JOIN flow_data f ON f.alert_id = a.id "
        "ORDER BY " + QUEUE_ORDER_QUALIFIED)
    return [
        QueuedAlert(
            alert_id=int(row["id"]), rank=rank, source_record_id=row["source_record_id"],
            queue_class=row["queue_class"], evidence_class=row["evidence_class"],
            combined_score=float(row["combined_score"]),
            detection_score=float(row["detection_score"]),
            predicted_class=row["attack_category"], is_critical=bool(row["is_critical"]),
            requires_review=bool(row["requires_review"]), family_key=row["family_key"],
            truth_class=truth.of(row["source_record_id"]).attack_type)
        for rank, row in enumerate(rows, start=1)
    ]


def _rates(tp: int, fp: int, fn: int, tn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "support": tp + fn, "predicted": tp + fp,
        "precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6),
        "fpr": round(fp / (fp + tn), 6) if fp + tn else 0.0,
        "fnr": round(fn / (tp + fn), 6) if tp + fn else 0.0,
    }


def detection_metrics(queue: list[QueuedAlert]) -> dict[str, Any]:
    """Per-class precision/recall/F1/FPR/FNR of the detection decision, one-vs-rest.

    Scored on the class the system assigned (``attack_category``), against the class the capture
    actually was. An alert no detector classified counts as a predicted "Benign" - leaving those
    out would turn recall into precision (the mistake D3 exists to prevent).
    """
    classes = sorted({alert.truth_class for alert in queue}
                     | {alert.predicted_attack for alert in queue})
    total = len(queue)
    per_class: dict[str, Any] = {}
    for label in classes:
        tp = sum(1 for a in queue if a.predicted_attack == label and a.truth_class == label)
        fp = sum(1 for a in queue if a.predicted_attack == label and a.truth_class != label)
        fn = sum(1 for a in queue if a.predicted_attack != label and a.truth_class == label)
        per_class[label] = _rates(tp, fp, fn, total - tp - fp - fn)

    attacks = [a for a in queue if a.malicious]
    flagged = [a for a in queue if a.queue_class != "none"]
    hits = sum(1 for a in flagged if a.malicious)
    binary = _rates(hits, len(flagged) - hits, len(attacks) - hits,
                    total - len(flagged) - (len(attacks) - hits))
    scored = [label for label in classes if per_class[label]["support"]]
    return {
        "alerts": total, "attacks": len(attacks), "per_class": per_class,
        "macro_f1": round(sum(per_class[c]["f1"] for c in scored) / len(scored), 6),
        # "Did a detector flag it at all", independent of which class it guessed.
        "flagged_vs_benign": binary,
    }


def queue_metrics(queue: list[QueuedAlert], *, cuts: tuple[int, ...] = PRECISION_AT
                  ) -> dict[str, Any]:
    """What the analyst sees: how clean the head of the queue is, and how deep the attacks sit."""
    attacks = [a for a in queue if a.malicious]
    at_k: dict[str, Any] = {}
    for k in cuts:
        head = queue[:k]
        found = sum(1 for a in head if a.malicious)
        at_k[str(k)] = {
            "precision": round(found / len(head), 6) if head else 0.0,
            "attacks": found, "false_positives": len(head) - found,
        }
    ranks = [a.rank for a in attacks]
    # Saturation is load-bearing for reading every other number here: where a whole band sits at
    # the maximum score, the ranking formula has no headroom to express a promotion, and order
    # inside the band falls to the contract's `id ASC` tie-break rather than to any judgement.
    flagged = [a for a in queue if a.queue_class != "none"]
    at_ceiling = [a for a in flagged if a.combined_score >= 100]
    return {
        "attacks": len(attacks),
        "precision_at": at_k,
        "saturation": {
            "flagged_alerts": len(flagged),
            "at_maximum_score": len(at_ceiling),
            "share_at_maximum": round(len(at_ceiling) / len(flagged), 6) if flagged else 0.0,
            "distinct_scores_among_flagged": len({a.combined_score for a in flagged}),
        },
        "false_positives_in_top_50": at_k["50"]["false_positives"] if "50" in at_k else None,
        # The mean of 1/rank over every true positive - the analyst works the whole queue.
        "mrr_true_positives": round(sum(1 / r for r in ranks) / len(ranks), 8) if ranks else 0.0,
        "mean_rank_true_positives": round(sum(ranks) / len(ranks), 4) if ranks else 0.0,
        "worst_rank_true_positive": max(ranks) if ranks else None,
        "attacks_below_flagged_bands": sum(1 for a in attacks if a.queue_class == "none"),
        "by_queue_class": dict(sorted(Counter(a.queue_class for a in queue).items())),
    }


@dataclass(frozen=True)
class Movement:
    """One alert's change between the control arm and this one."""

    alert_id: int
    source_record_id: str
    truth_class: str
    score_before: float
    score_after: float
    rank_before: int
    rank_after: int
    band_before: str
    band_after: str

    @property
    def moved(self) -> bool:
        return (self.score_before != self.score_after or self.band_before != self.band_after
                or self.rank_before != self.rank_after)


def movements(control: list[QueuedAlert], arm: list[QueuedAlert]) -> list[Movement]:
    """Pair the two arms by alert id. They are copies of one detection run, so the ids match; a
    mismatch means the arms are not comparable and the caller must be told, not left to guess."""
    before = {a.alert_id: a for a in control}
    if before.keys() != {a.alert_id for a in arm}:
        raise ValueError("the arms hold different alerts; they are not comparable")
    return [Movement(alert_id=a.alert_id, source_record_id=a.source_record_id,
                     truth_class=a.truth_class, score_before=before[a.alert_id].combined_score,
                     score_after=a.combined_score, rank_before=before[a.alert_id].rank,
                     rank_after=a.rank, band_before=before[a.alert_id].queue_class,
                     band_after=a.queue_class)
            for a in arm]


def movement_metrics(control: list[QueuedAlert], arm: list[QueuedAlert],
                     sequence: list[dict[str, Any]]) -> dict[str, Any]:
    """The S7b claim, split by who the moved alert is.

    ``judged`` got a verdict of its own (S7a). ``family_untouched`` is a member of a judged family
    that got no verdict - **these are the alerts the project's goal is about**. ``unrelated`` should
    be empty: a non-zero count means learning leaked past its family.
    """
    judged = {entry["source_record_id"] for entry in sequence}
    families = {entry["family_key"] for entry in sequence}
    by_id = {a.alert_id: a for a in arm}
    groups: dict[str, list[Movement]] = {"judged": [], "family_untouched": [], "unrelated": []}
    for move in movements(control, arm):
        if move.source_record_id in judged:
            groups["judged"].append(move)
        elif by_id[move.alert_id].family_key in families:
            groups["family_untouched"].append(move)
        else:
            groups["unrelated"].append(move)

    def describe(items: list[Movement]) -> dict[str, Any]:
        # Two different things, and conflating them makes the queue look chaotic. `adjusted` is an
        # alert the system acted on - its score or its band changed. `rank_changed` includes every
        # alert that merely drifted because others moved around it; rank is a relative position, so
        # a single promotion re-ranks everything beneath it and that is not an effect on those
        # alerts. Leakage is measured by `adjusted` in the `unrelated` group, never by rank.
        adjusted = [item for item in items
                    if item.score_before != item.score_after
                    or item.band_before != item.band_after]
        rank_changed = [item for item in items if item.rank_after != item.rank_before]
        promoted = [item for item in adjusted if item.rank_after < item.rank_before]
        demoted = [item for item in adjusted if item.rank_after > item.rank_before]
        benign_promoted = [item for item in promoted if item.truth_class == "Benign"]
        return {
            "alerts": len(items), "adjusted": len(adjusted), "rank_changed": len(rank_changed),
            "promoted": len(promoted), "demoted": len(demoted),
            "band_changed": sum(1 for item in adjusted if item.band_before != item.band_after),
            "score_changed": sum(1 for item in adjusted
                                 if item.score_before != item.score_after),
            "attacks_promoted": sum(1 for item in promoted if item.truth_class != "Benign"),
            "benign_promoted": len(benign_promoted),
            "benign_demoted": sum(1 for item in demoted if item.truth_class == "Benign"),
            "best_rank_reached_by_a_benign_alert": min(
                (item.rank_after for item in benign_promoted), default=None),
            "mean_rank_change": round(
                sum(item.rank_after - item.rank_before for item in items) / len(items), 4)
            if items else 0.0,
        }

    return {name: describe(items) for name, items in groups.items()}


def safety_metrics(conn: sqlite3.Connection, control: list[QueuedAlert],
                   arm: list[QueuedAlert], *, critical_threshold: float) -> dict[str, Any]:
    """What the guardrails did, and what they preserved.

    ``signature_override`` is reported on its own because v1.0's core safety claim is that those
    alerts survive feedback untouched (invariant I3). When the database holds none - as the
    corrected dataset's ``signature_only = 0`` finding means it does - the count is 0 and the claim
    is untested *here*; it is S7's unit tests that guarantee it. Saying so is the honest report.
    """
    actions = dict(sorted(Counter(
        row["guardrail_action"] for row in
        conn.execute("SELECT guardrail_action FROM feedback_events")).items()))
    codes: Counter[str] = Counter()
    for row in conn.execute("SELECT guardrail_reason FROM feedback_events "
                            "WHERE guardrail_reason IS NOT NULL"):
        codes.update(part.strip() for part in str(row["guardrail_reason"]).split(";") if part)
    audit_codes = dict(sorted(Counter(
        row["event_type"] for row in conn.execute(
            "SELECT event_type FROM audit_log WHERE event_type LIKE 'GUARDRAIL%'")).items()))

    before = {a.alert_id: a for a in control}
    overrides = [a for a in arm if a.evidence_class == "signature_override"]
    override_changed = [a for a in overrides
                        if (a.combined_score, a.queue_class)
                        != (before[a.alert_id].combined_score, before[a.alert_id].queue_class)]
    criticals = [a for a in arm if before[a.alert_id].is_critical]
    breached = [a for a in criticals if a.combined_score < critical_threshold]
    suppressed = [a for a in arm
                  if a.combined_score < before[a.alert_id].combined_score
                  and a.truth_class != "Benign"]
    return {
        "feedback_events": sum(actions.values()),
        "guardrail_actions": actions,
        "guardrail_codes": dict(sorted(codes.items())),
        "audit_guardrail_events": audit_codes,
        "critical_alerts": len(criticals),
        "critical_preserved": len(criticals) - len(breached),
        "critical_preservation_rate": round(
            (len(criticals) - len(breached)) / len(criticals), 6) if criticals else None,
        "critical_floor_breaches": len(breached),
        "true_positives_suppressed": len(suppressed),
        # Reported separately, per the plan: invariant I3.
        "signature_override": {
            "alerts": len(overrides), "changed": len(override_changed),
            "preservation_rate": round(
                (len(overrides) - len(override_changed)) / len(overrides), 6)
            if overrides else None,
            "note": ("no signature_override alert exists in this database (signature_only = 0 on "
                     "the corrected dataset); I3 is guaranteed by S7's unit tests, not measured "
                     "here") if not overrides else None,
        },
    }


def score_arm(conn: sqlite3.Connection, truth: GroundTruth, *, critical_threshold: float,
              control: list[QueuedAlert] | None = None,
              sequence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Every metric for one arm. ``control`` is omitted when the arm *is* the control."""
    queue = read_queue(conn, truth)
    control = control if control is not None else queue
    metrics: dict[str, Any] = {
        "detection": detection_metrics(queue),
        "queue": queue_metrics(queue),
        "safety": safety_metrics(conn, control, queue, critical_threshold=critical_threshold),
    }
    if sequence is not None:
        metrics["movement"] = movement_metrics(control, queue, sequence)
    return metrics


def deltas(control: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    """arm - control, for the quantities the plan names. Positive is better in every entry here:
    a fall in false positives and a rise in reciprocal rank both read as a gain."""
    cq, aq = control["queue"], arm["queue"]
    out: dict[str, Any] = {
        "false_positives_in_top_50": (cq["false_positives_in_top_50"]
                                      - aq["false_positives_in_top_50"]),
        "mrr_true_positives": round(aq["mrr_true_positives"] - cq["mrr_true_positives"], 8),
        "mean_rank_true_positives": round(cq["mean_rank_true_positives"]
                                          - aq["mean_rank_true_positives"], 4),
    }
    for k, entry in aq["precision_at"].items():
        out[f"precision_at_{k}"] = round(entry["precision"] - cq["precision_at"][k]["precision"], 6)
    out["macro_f1_detection"] = round(arm["detection"]["macro_f1"]
                                      - control["detection"]["macro_f1"], 6)
    out["critical_floor_breaches"] = (arm["safety"]["critical_floor_breaches"]
                                      - control["safety"]["critical_floor_breaches"])
    out["true_positives_suppressed"] = (arm["safety"]["true_positives_suppressed"]
                                        - control["safety"]["true_positives_suppressed"])
    return out
