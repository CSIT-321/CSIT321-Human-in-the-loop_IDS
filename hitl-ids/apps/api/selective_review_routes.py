"""Explicit evaluation and human recall; no caller-supplied safety context."""
from uuid import UUID
from fastapi import APIRouter,Query
from apps.api.contract.common import Page,PageInfo
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn,Principal,MutationRole
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.selective_review import (
    Disposition,ReviewCommand,ReviewView,ReviewMutation,ReviewEvent,ReviewMetrics,ReviewConflict,
    read_review,decide_review,list_reviews,review_history,review_metrics,
)

router=APIRouter(prefix='/api/v2',tags=['Selective review'])


def _error(exc):
    if isinstance(exc,LookupError):return ApiError(404,'NOT_FOUND',str(exc))
    if isinstance(exc,PermissionError):return ApiError(403,'FORBIDDEN_ROLE',str(exc))
    return ApiError(409,'REVIEW_CONFLICT',str(exc))


@router.get('/selective-review/metrics',response_model=ReviewMetrics,operation_id='selectiveReviewMetrics')
def metrics(conn:ReadConn,principal:ReadPrincipal):
    with conn:
        conn.execute('BEGIN')
        return review_metrics(conn)


@router.get('/selective-review',response_model=Page[ReviewView],operation_id='listSelectiveReviews')
def queue(conn:ReadConn,principal:ReadPrincipal,disposition:Disposition|None=None,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with conn:
        conn.execute('BEGIN')
        items,total=list_reviews(conn,disposition,limit,offset)
        return Page(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)))


@router.get('/alerts/{alertRef}/selective-review',response_model=ReviewView,operation_id='getSelectiveReview')
def detail(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal):
    try:
        with conn:
            conn.execute('BEGIN')
            return read_review(conn,alertRef)
    except LookupError as exc:raise _error(exc) from exc


@router.get('/alerts/{alertRef}/selective-review/events',response_model=Page[ReviewEvent],operation_id='selectiveReviewHistory')
def history(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    try:
        with conn:
            conn.execute('BEGIN')
            items,total=review_history(conn,alertRef,limit,offset)
            return Page(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)))
    except LookupError as exc:raise _error(exc) from exc


def _decide(ref,conn,principal,request,action):
    try:return decide_review(conn,ref,actor_id=principal.user_id,request=request,action=action)
    except (LookupError,PermissionError,ReviewConflict) as exc:raise _error(exc) from exc


@router.post('/alerts/{alertRef}/selective-review/evaluate',response_model=ReviewMutation,dependencies=[MutationRole],operation_id='applySelectiveReview')
def evaluate(alertRef:UUID,body:ReviewCommand,conn:Conn,principal:Principal):
    return _decide(alertRef,conn,principal,body,'apply')


@router.post('/alerts/{alertRef}/selective-review/require-human',response_model=ReviewMutation,dependencies=[MutationRole],operation_id='requireHumanReview')
def require(alertRef:UUID,body:ReviewCommand,conn:Conn,principal:Principal):
    return _decide(alertRef,conn,principal,body,'require_review')
