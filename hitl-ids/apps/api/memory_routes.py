"""Authenticated human memory reviews and read-only historical guidance."""
from uuid import UUID
from fastapi import APIRouter,Query
from apps.api.contract.common import Page,PageInfo
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn,Principal,MutationRole
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.triage_memory import (
    MemoryReviewRequest,MemoryDecisionRequest,MemoryMutation,MemoryView,MemoryAudit,MemoryMatch,
    MemoryConflict,record_review,decide_memory,read_memory,list_memory,memory_history,lookup_memory,
)

router=APIRouter(prefix='/api/v2',tags=['Triage memory'])


def _error(exc):
    if isinstance(exc,LookupError):
        return ApiError(404,'NOT_FOUND',str(exc))
    if isinstance(exc,PermissionError):
        return ApiError(403,'FORBIDDEN_ROLE',str(exc))
    return ApiError(409,'MEMORY_CONFLICT',str(exc))


def _page(conn,fn,args,limit,offset):
    try:
        with conn:
            conn.execute('BEGIN')
            items,total=fn(conn,*args,limit,offset)
            return Page(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)))
    except LookupError as exc:
        raise _error(exc) from exc


@router.post('/alerts/{alertRef}/triage-memory/candidate',response_model=MemoryMutation,dependencies=[MutationRole],operation_id='recordMemoryHumanReview')
def review(alertRef:UUID,body:MemoryReviewRequest,conn:Conn,principal:Principal):
    try:
        return record_review(conn,alertRef,actor_id=principal.user_id,request=body)
    except (MemoryConflict,LookupError,PermissionError) as exc:
        raise _error(exc) from exc


@router.get('/triage-memory',response_model=Page[MemoryView],operation_id='listTriageMemory')
def lessons(conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    return _page(conn,list_memory,(),limit,offset)


@router.get('/triage-memory/{lessonRef}',response_model=MemoryView,operation_id='getTriageMemory')
def detail(lessonRef:UUID,conn:ReadConn,principal:ReadPrincipal):
    try:
        with conn:
            conn.execute('BEGIN')
            return read_memory(conn,lessonRef)
    except LookupError as exc:
        raise _error(exc) from exc


@router.get('/triage-memory/{lessonRef}/events',response_model=Page[MemoryAudit],operation_id='listTriageMemoryEvents')
def events(lessonRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    return _page(conn,memory_history,(lessonRef,),limit,offset)


def _decide(ref,conn,principal,body,action):
    try:
        return decide_memory(conn,ref,actor_id=principal.user_id,action=action,request=body)
    except (MemoryConflict,LookupError,PermissionError) as exc:
        raise _error(exc) from exc


@router.post('/triage-memory/{lessonRef}/activate',response_model=MemoryMutation,dependencies=[MutationRole],operation_id='activateTriageMemory')
def activate(lessonRef:UUID,body:MemoryDecisionRequest,conn:Conn,principal:Principal):
    return _decide(lessonRef,conn,principal,body,'activate')


@router.post('/triage-memory/{lessonRef}/reject',response_model=MemoryMutation,dependencies=[MutationRole],operation_id='rejectTriageMemory')
def reject(lessonRef:UUID,body:MemoryDecisionRequest,conn:Conn,principal:Principal):
    return _decide(lessonRef,conn,principal,body,'reject')


@router.get('/alerts/{alertRef}/triage-memory/matches',response_model=Page[MemoryMatch],operation_id='matchTriageMemory')
def matches(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    return _page(conn,lookup_memory,(alertRef,),limit,offset)
