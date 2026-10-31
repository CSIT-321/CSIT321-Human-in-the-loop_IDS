"""Case-only investigation API, isolated from legacy verdict and response workflows."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Query
from apps.api.contract.common import Page, PageInfo
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn, Principal, MutationRole
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.tier2_cases import (
    CaseView, CaseEvent, CaseMutation, CreateCaseRequest, CaseCommand, LinkCaseRequest,
    FindingRequest, CaseConflict, create_case, mutate_case, read_case, read_events,
)

router = APIRouter(prefix='/api/v2', tags=['Tier 2 cases'])


def _error(exc):
    if isinstance(exc, PermissionError):
        return ApiError(403,'FORBIDDEN_ROLE',str(exc))
    if isinstance(exc, LookupError):
        return ApiError(404,'NOT_FOUND',str(exc))
    return ApiError(409,'CASE_CONFLICT',str(exc))


@router.post('/alerts/{alertRef}/tier2/case',response_model=CaseMutation,
             operation_id='createTier2Case',dependencies=[MutationRole])
def create(alertRef: UUID, body: CreateCaseRequest, conn: Conn, principal: Principal):
    try:
        return create_case(conn,alertRef,actor_id=principal.user_id,request=body)
    except (CaseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc


@router.get('/tier2/cases',response_model=Page[CaseView],operation_id='listTier2Cases')
def list_cases(conn: ReadConn, principal: ReadPrincipal, limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0)):
    with conn:
        conn.execute('BEGIN')
        total = conn.execute('SELECT count(*) FROM tier2_cases').fetchone()[0]
        refs = conn.execute('SELECT case_ref FROM tier2_cases ORDER BY id DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        items = [read_case(conn,row[0]) for row in refs]
        return Page(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)))


@router.get('/tier2/cases/{caseRef}',response_model=CaseView,operation_id='getTier2Case')
def get_case(caseRef: UUID,conn: ReadConn,principal: ReadPrincipal):
    try:
        with conn:
            conn.execute('BEGIN')
            return read_case(conn,caseRef)
    except LookupError as exc:
        raise _error(exc) from exc


@router.get('/tier2/cases/{caseRef}/events',response_model=Page[CaseEvent],operation_id='listTier2CaseEvents')
def events(caseRef: UUID,conn: ReadConn,principal: ReadPrincipal,limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),
           action: Literal['create','link','note','finding','start'] | None=None):
    try:
        with conn:
            conn.execute('BEGIN')
            items,total = read_events(conn,caseRef,limit,offset,action)
            return Page(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)))
    except LookupError as exc:
        raise _error(exc) from exc


def _mutate(conn,principal,ref,action,body):
    try:
        return mutate_case(conn,ref,actor_id=principal.user_id,action=action,request=body)
    except (CaseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc


@router.post('/tier2/cases/{caseRef}/alerts',response_model=CaseMutation,
             operation_id='linkTier2CaseAlert',dependencies=[MutationRole])
def link(caseRef: UUID,body: LinkCaseRequest,conn: Conn,principal: Principal):
    return _mutate(conn,principal,caseRef,'link',body)


@router.post('/tier2/cases/{caseRef}/notes',response_model=CaseMutation,
             operation_id='addTier2CaseNote',dependencies=[MutationRole])
def note(caseRef: UUID,body: CaseCommand,conn: Conn,principal: Principal):
    return _mutate(conn,principal,caseRef,'note',body)


@router.post('/tier2/cases/{caseRef}/findings',response_model=CaseMutation,
             operation_id='recordTier2CaseFinding',dependencies=[MutationRole])
def finding(caseRef: UUID,body: FindingRequest,conn: Conn,principal: Principal):
    return _mutate(conn,principal,caseRef,'finding',body)


@router.post('/tier2/cases/{caseRef}/start-investigation',response_model=CaseMutation,
             operation_id='startTier2Investigation',dependencies=[MutationRole])
def start(caseRef: UUID,body: CaseCommand,conn: Conn,principal: Principal):
    return _mutate(conn,principal,caseRef,'start',body)
