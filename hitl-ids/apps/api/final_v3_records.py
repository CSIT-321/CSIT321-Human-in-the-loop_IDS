"""Validated read-only Final V3.1 projection; never opens an operational database."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


REPOSITORY = Path(__file__).resolve().parents[3]
PRIMARY = {"stable_matching_benign": 80, "unseen_benign": 20,
           "malicious": 20, "suspicious": 20}
STRATA = {"stable_learning": 24, "drift_learning": 6, "negative_learning": 10,
          **PRIMARY, "unknown_tier2": 10, "drift_conflict": 10}


class ArtifactUnavailable(Exception):
    pass


class ArtifactMismatch(Exception):
    pass


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class FrozenMemoryMatch(FrozenModel):
    lessonRef: str
    outcome: str
    status: str
    support: int
    conflicts: int
    agreement: float
    guidanceActive: bool
    matchedFields: list[str]
    mismatchedFields: list[str]
    unavailableFields: list[str]


class FinalRecord(FrozenModel):
    index: int
    alertRef: str
    phase: str
    population: str | None
    stratum: str
    pattern: str
    analyst: str
    plannedRoute: str
    timestamp: str
    signature: str
    signatureId: int
    nativeCategory: str
    nativeSeverity: int
    sourceIp: str
    sourcePort: int
    destinationIp: str
    destinationPort: int
    protocol: str
    flowId: int
    attackCategory: str | None = None
    priority: float | None = None
    route: str | None = None
    caseRef: str | None = None
    baselineDisposition: str | None = None
    adaptiveDisposition: str | None = None
    baselineReviewRequired: bool | None = None
    adaptiveReviewRequired: bool | None = None
    baselineReasonCodes: list[str] = []
    adaptiveReasonCodes: list[str] = []
    matchedMemoryLessonRef: str | None = None
    memoryMatches: list[FrozenMemoryMatch] = []
    oracleOutcome: str | None = None
    deferralClassification: str | None = None
    humanOutcome: str | None = None
    verdictRef: str | None = None
    learningLessonRef: str | None = None
    learningLessonStatus: str | None = None
    learningSupport: int | None = None
    learningConflicts: int | None = None
    drift: dict[str, Any] | None = None


class MemoryImpact(FrozenModel):
    lessonRef: str
    pattern: str
    outcome: str
    support: int
    conflicts: int
    agreement: float
    status: str
    holdoutExactMatches: int
    matched: int
    used: int
    deferred: int
    blocked: int
    auditSampled: int
    affectedIndices: list[int]
    conflictWithdrawn: bool


class FinalSummary(FrozenModel):
    run: str
    status: str
    runtimeSha: str
    total: int
    learning: int
    holdout: int
    primary: int
    supplementary: int
    unknown: int
    drift: int
    strata: dict[str, int]
    primaryBaselineImmediateReview: int
    primaryAdaptiveImmediateReview: int
    primaryReviewReduction: int
    primaryReviewReductionRate: float
    primarySafeDeferrals: int
    primaryUnsafeDeferrals: int
    allHoldoutInitialDeferrals: int
    allHoldoutUnsafeDeferrals: int
    postContradictionUnsafeDeferrals: int
    postContradictionPopulation: int
    unknownFormalTier2Cases: int
    driftTimeline: list[dict[str, Any]]


class FinalRecordPage(FrozenModel):
    items: list[FinalRecord]
    total: int
    limit: int
    offset: int


class MemoryImpactPage(FrozenModel):
    items: list[MemoryImpact]


class Projection(FrozenModel):
    summary: FinalSummary
    records: list[FinalRecord]
    memory: list[MemoryImpact]


def _read(path: Path, *, lines: bool = False) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()] if lines else json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactUnavailable(f"Frozen V3.1 artifact unavailable or malformed: {path.name}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactMismatch(message)


def _indexed(items: list[dict], key: str, count: int, label: str) -> dict:
    _require(isinstance(items, list) and len(items) == count, f"{label}: expected {count} rows")
    try:
        result = {item[key]: item for item in items}
    except (KeyError, TypeError) as exc:
        raise ArtifactMismatch(f"{label}: missing {key}") from exc
    _require(len(result) == count, f"{label}: duplicate {key}")
    return result


def load_projection(root: Path = REPOSITORY) -> Projection:
    protocol = root / "evaluation/protocol-v3.1"
    run = root / "evaluation/protocol-v3.1-run-001"
    structure = _read(protocol / "expected/workload-structure.json")
    workload = _read(protocol / "workload/operational-workload.jsonl", lines=True)
    report = _read(run / "report/records.json")
    metrics = _read(run / "report/metrics.json")
    memory_table = _read(run / "report/memory-table.json")
    drift = _read(run / "report/drift-timeline.json")
    outcomes = _read(run / "adaptive/outcomes.jsonl", lines=True)
    feedback = _read(run / "adaptive/feedback.jsonl", lines=True)
    learning_end = _read(run / "adaptive/learning-end.json")
    metadata = _read(run / "experiment-metadata.json")
    try:
        by_index = _indexed(structure, "index", 200, "structure")
        _indexed(structure, "alertRef", 200, "structure")
        _require(set(by_index) == set(range(1, 201)), "workload indices must be 1..200")
        _require(len(workload) == 200, "EVE workload must contain 200 records")
        _require(Counter(row["phase"] for row in structure) == {"learning": 40, "holdout": 160},
                 "phase totals disagree")
        _require(Counter(row["stratum"] for row in structure) == STRATA, "stratum totals disagree")
        by_report = _indexed(report, "index", 160, "holdout report")
        _indexed(report, "alertRef", 160, "holdout report")
        _require(set(by_report) == set(range(41, 201)), "missing or extra holdout result")
        by_outcome = _indexed(outcomes, "alertRef", 200, "adaptive outcomes")
        _require(set(by_outcome) == {row["alertRef"] for row in structure}, "outcome identities disagree")
        learning_feedback = [row for row in feedback if row.get("phase") == "learning"]
        by_feedback = _indexed(learning_feedback, "index", 40, "learning feedback")
        _indexed(learning_feedback, "alertRef", 40, "learning feedback")
        _require(len(feedback) == 42, "feedback must contain 40 learning and 2 drift events")
        by_drift = _indexed(drift, "eventIndex", 10, "drift timeline")
        _require(set(by_drift) == set(range(191, 201)), "drift indices disagree")
        _indexed(memory_table, "lessonRef", 20, "memory table")
        learning_lessons = learning_end["lessons"]
        by_lesson = {row["lesson"]["lessonRef"]: row for row in learning_lessons}
        _require(len(by_lesson) == len(learning_lessons), "duplicate learning lesson")
        records = []
        for index in range(1, 201):
            identity = by_index[index]
            event = workload[index - 1]
            ref = identity["alertRef"]
            _require(event["flow_id"] == 330000 + index and
                     event["event_type"] == "alert", f"EVE workload line {index} disagrees")
            result = by_report.get(index)
            human = by_feedback.get(index)
            if index <= 40:
                _require(identity["phase"] == "learning" and result is None and human is not None,
                         f"learning identity {index} disagrees")
                _require(human["alertRef"] == ref and human["pattern"] == identity["pattern"],
                         f"learning feedback {index} disagrees")
            else:
                _require(identity["phase"] == "holdout" and result is not None and human is None,
                         f"holdout identity {index} disagrees")
                _require(all(result[field] == identity[field] for field in ("alertRef", "stratum", "pattern")) and
                         result["oracleOutcome"] == by_outcome[ref]["outcome"],
                         f"holdout report {index} disagrees")
            verdict = ((human or {}).get("verdict") or {}).get("verdict") or {}
            feedback_lessons = ((human or {}).get("memory") or {}).get("lessons") or []
            matching_lesson = next((row for row in feedback_lessons if row["lesson"]["contextSnapshot"]["detectionTitle"] ==
                                    event["alert"]["signature"]), None) if human else None
            matches = []
            for match in (result or {}).get("memoryMatches") or []:
                memory = match["memory"]
                matches.append(FrozenMemoryMatch(
                    lessonRef=memory["lesson"]["lessonRef"], outcome=memory["lesson"]["outcome"],
                    status=memory["status"], support=memory["supportCount"],
                    conflicts=memory["conflictCount"], agreement=memory["agreementRatio"],
                    guidanceActive=match["guidanceActive"], matchedFields=match["matchedFields"],
                    mismatchedFields=match["mismatchedFields"], unavailableFields=match["unavailableFields"]))
            records.append(FinalRecord(
                index=index, alertRef=ref, phase=identity["phase"],
                population=("primary" if identity["stratum"] in PRIMARY else "supplementary") if result else None,
                stratum=identity["stratum"], pattern=identity["pattern"], analyst=identity["analyst"],
                plannedRoute=identity["plannedRoute"], timestamp=event["timestamp"],
                signature=event["alert"]["signature"], signatureId=event["alert"]["signature_id"],
                nativeCategory=event["alert"]["category"], nativeSeverity=event["alert"]["severity"],
                sourceIp=event["src_ip"], sourcePort=event["src_port"],
                destinationIp=event["dest_ip"], destinationPort=event["dest_port"],
                protocol=event["proto"], flowId=event["flow_id"],
                attackCategory=((result or {}).get("classification") or {}).get("attackCategory"),
                priority=(result or {}).get("priority"), route=(result or {}).get("route"),
                caseRef=(result or {}).get("caseRef"),
                baselineDisposition=(result or {}).get("baselineDisposition"),
                adaptiveDisposition=(result or {}).get("adaptiveDisposition"),
                baselineReviewRequired=(result or {}).get("baselineReviewRequired"),
                adaptiveReviewRequired=(result or {}).get("adaptiveReviewRequired"),
                baselineReasonCodes=(result or {}).get("baselineReasonCodes") or [],
                adaptiveReasonCodes=(result or {}).get("adaptiveReasonCodes") or [],
                matchedMemoryLessonRef=(result or {}).get("matchedMemoryLessonRef"), memoryMatches=matches,
                oracleOutcome=by_outcome[ref]["outcome"],
                deferralClassification=(result or {}).get("deferralClassification"),
                humanOutcome=verdict.get("outcome"), verdictRef=verdict.get("verdictRef"),
                learningLessonRef=(matching_lesson or {}).get("lesson", {}).get("lessonRef"),
                learningLessonStatus=(matching_lesson or {}).get("status"),
                learningSupport=(matching_lesson or {}).get("supportCount"),
                learningConflicts=(matching_lesson or {}).get("conflictCount"),
                drift=by_drift.get(index)))
        primary = [row for row in records if row.population == "primary"]
        holdout = records[40:]
        unknown = [row for row in records if row.stratum == "unknown_tier2"]
        pm, am, safety = metrics["primary"], metrics["allHoldoutSupplementary"], metrics["safety"]
        _require(len(primary) == pm["population"] == 140 and len(holdout) == am["population"] == 160,
                 "metric denominators disagree")
        _require(sum(row.baselineReviewRequired is True for row in primary) == pm["baselineImmediateReview"] and
                 sum(row.adaptiveReviewRequired is True for row in primary) == pm["adaptiveImmediateReview"] and
                 Counter(row.deferralClassification for row in primary)["safe"] == pm["safeDeferrals"] and
                 Counter(row.deferralClassification for row in primary)["unsafe"] == pm["unsafeDeferrals"],
                 "primary metrics disagree")
        _require(pm["baselineImmediateReview"] - pm["adaptiveImmediateReview"] ==
                 pm["immediateReviewReductionCount"] and
                 abs(pm["immediateReviewReductionRate"]["value"] -
                     pm["immediateReviewReductionCount"] / len(primary)) < 1e-9,
                 "primary reduction disagrees")
        _require(sum(row.adaptiveDisposition == "no_immediate_review" for row in holdout) == am["totalDeferrals"] and
                 Counter(row.deferralClassification for row in holdout)["unsafe"] == am["unsafeDeferrals"],
                 "all-Holdout metrics disagree")
        _require(sum(bool(row.caseRef) for row in unknown) == safety["formalTier2Cases"] == 10,
                 "Unknown Tier 2 case count disagrees")
        later = [row for row in drift if row["eventIndex"] not in (191, 196)]
        _require(len(later) == 8 and sum(row["disposition"] == "no_immediate_review" for row in later) ==
                 safety["postContradictionUnsafeDeferrals"], "drift safety count disagrees")
        impacts = []
        for lesson in memory_table:
            ref = lesson["lessonRef"]
            matched = [row for row in holdout if any(item.lessonRef == ref for item in row.memoryMatches)]
            used = [row for row in holdout if row.matchedMemoryLessonRef == ref]
            _require(ref in by_lesson, f"memory lesson {ref} missing from learning end")
            impacts.append(MemoryImpact(
                lessonRef=ref, pattern=lesson["learningPattern"], outcome=lesson["outcome"],
                support=lesson["support"], conflicts=lesson["conflicts"],
                agreement=by_lesson[ref]["agreementRatio"], status=lesson["status"],
                holdoutExactMatches=lesson["holdoutExactMatches"], matched=len(matched), used=len(used),
                deferred=sum(row.adaptiveDisposition == "no_immediate_review" for row in used),
                blocked=sum(row.adaptiveDisposition != "no_immediate_review" for row in matched),
                auditSampled=sum("AUDIT_SAMPLE" in " ".join(row.adaptiveReasonCodes) for row in matched),
                affectedIndices=[row.index for row in matched],
                conflictWithdrawn=any(row["pattern"] == lesson["learningPattern"] and
                                      row["afterFeedbackStatus"] == "conflict_review" for row in drift)))
        return Projection(
            summary=FinalSummary(
                run="Final Evaluation V3.1 — Run 001", status="COMPLETED / FROZEN",
                runtimeSha=metadata["runtimeSha"], total=len(records), learning=len(records) - len(holdout),
                holdout=len(holdout), primary=len(primary), supplementary=len(holdout) - len(primary),
                unknown=len(unknown), drift=len(drift),
                strata=dict(Counter(row.stratum for row in records)),
                primaryBaselineImmediateReview=pm["baselineImmediateReview"],
                primaryAdaptiveImmediateReview=pm["adaptiveImmediateReview"],
                primaryReviewReduction=pm["immediateReviewReductionCount"],
                primaryReviewReductionRate=pm["immediateReviewReductionRate"]["value"],
                primarySafeDeferrals=pm["safeDeferrals"], primaryUnsafeDeferrals=pm["unsafeDeferrals"],
                allHoldoutInitialDeferrals=am["totalDeferrals"],
                allHoldoutUnsafeDeferrals=am["unsafeDeferrals"],
                postContradictionUnsafeDeferrals=safety["postContradictionUnsafeDeferrals"],
                postContradictionPopulation=len(later), unknownFormalTier2Cases=safety["formalTier2Cases"],
                driftTimeline=drift), records=records, memory=impacts)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ArtifactMismatch(f"Frozen V3.1 artifact relationships are invalid: {exc}") from exc
