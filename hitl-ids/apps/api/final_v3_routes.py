"""One read-only official evaluation projection shared by Admin and Evaluator."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from apps.api import auth
from apps.api.deps import ApiError, not_found
from apps.api.final_v3_records import (
    ArtifactMismatch, ArtifactUnavailable, FinalRecord, FinalRecordPage,
    FinalSummary, MemoryImpactPage, load_projection,
)

router = APIRouter(tags=["evaluation"])
Reader = Annotated[auth.Principal, Depends(auth.require_role("system_admin", "evaluator", readonly=True))]


def _projection():
    try:
        return load_projection()
    except ArtifactUnavailable as exc:
        raise ApiError(503, "FINAL_EVALUATION_ARTIFACTS_UNAVAILABLE",
                       "Final V3.1 frozen artifacts are not available in this deployment.") from exc
    except ArtifactMismatch as exc:
        raise ApiError(503, "FINAL_EVALUATION_ARTIFACTS_INVALID",
                       "Final V3.1 frozen artifacts disagree; records cannot be served.",
                       {"reason": str(exc)}) from exc


@router.get("/api/evaluation/final-v3-1", response_model=FinalSummary,
            operation_id="getFinalV31Summary")
def summary(principal: Reader) -> FinalSummary:
    return _projection().summary


@router.get("/api/evaluation/final-v3-1/records", response_model=FinalRecordPage,
            operation_id="listFinalV31Records")
def records(
    principal: Reader, limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
    phase: Literal["learning", "holdout"] | None = None,
    population: Literal["primary", "supplementary"] | None = None,
    stratum: str | None = None, pattern: str | None = None,
    baselineDisposition: str | None = None, adaptiveDisposition: str | None = None,
    deferral: Literal["safe", "unsafe", "not-deferred"] | None = None,
    memory: Literal["matched", "unmatched"] | None = None,
    case: Literal["has", "none"] | None = None, search: str | None = None,
) -> FinalRecordPage:
    items = _projection().records
    if phase:
        items = [row for row in items if row.phase == phase]
    if population:
        items = [row for row in items if row.population == population]
    if stratum:
        items = [row for row in items if row.stratum == stratum]
    if pattern:
        items = [row for row in items if row.pattern == pattern]
    if baselineDisposition:
        items = [row for row in items if row.baselineDisposition == baselineDisposition]
    if adaptiveDisposition:
        items = [row for row in items if row.adaptiveDisposition == adaptiveDisposition]
    if deferral:
        items = [row for row in items if row.deferralClassification == deferral]
    if memory:
        items = [row for row in items if bool(row.memoryMatches) == (memory == "matched")]
    if case:
        items = [row for row in items if bool(row.caseRef) == (case == "has")]
    if search:
        term = search.strip().casefold()
        items = [row for row in items if any(term in value.casefold() for value in (
            row.alertRef, row.pattern, row.sourceIp, row.destinationIp,
            row.signature, row.attackCategory or ""))]
    return FinalRecordPage(items=items[offset:offset + limit], total=len(items), limit=limit, offset=offset)


@router.get("/api/evaluation/final-v3-1/records/{index}", response_model=FinalRecord,
            operation_id="getFinalV31Record")
def record(index: int, principal: Reader) -> FinalRecord:
    if not 1 <= index <= 200:
        raise not_found("Final V3.1 record", index)
    return _projection().records[index - 1]


@router.get("/api/evaluation/final-v3-1/memory-impact", response_model=MemoryImpactPage,
            operation_id="getFinalV31MemoryImpact")
def memory_impact(principal: Reader) -> MemoryImpactPage:
    return MemoryImpactPage(items=_projection().memory)
