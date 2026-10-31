"""Human-authorized response plans. No endpoint executes or dispatches an action."""
from uuid import UUID
from fastapi import APIRouter,Query
from apps.api.contract.common import PageInfo
from apps.api.contract.responses import ResponsePage
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn,Principal,MutationRole
from packages.detection.response_approval import (
    ResponseRequest,ManualResponseRequest,ResponseDecisionRequest,ResponseView,ResponseMutation,
    ResponseConflict,list_responses,propose_response,decide_response,
)


router = APIRouter(prefix='/api/v2/tier2/cases',tags=['Response plans'])


def _error(exc):
    if isinstance(exc,PermissionError):
        return ApiError(403,'FORBIDDEN_ROLE',str(exc))
    if isinstance(exc,LookupError):
        return ApiError(404,'NOT_FOUND',str(exc))
    return ApiError(409,'RESPONSE_CONFLICT',str(exc))


@router.get('/{caseRef}/responses',response_model=ResponsePage,operation_id='listCaseResponses')
def responses(caseRef:UUID,conn:Conn,principal:Principal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    try:
        with conn:
            conn.execute('BEGIN')
            items,total,revision = list_responses(conn,caseRef,limit,offset)
            return ResponsePage(items=items,page=PageInfo(total=total,limit=limit,offset=offset,returned=len(items)),
                                case_revision=revision)
    except LookupError as exc:
        raise _error(exc) from exc


@router.post('/{caseRef}/responses/recommend',response_model=ResponseMutation,
             operation_id='recommendCaseResponse',dependencies=[MutationRole])
def recommend(caseRef:UUID,body:ResponseRequest,conn:Conn,principal:Principal):
    try:
        return propose_response(conn,caseRef,actor_id=principal.user_id,request=body)
    except (ResponseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc


@router.post('/{caseRef}/responses/manual',response_model=ResponseMutation,
             operation_id='proposeManualCaseResponse',dependencies=[MutationRole])
def manual(caseRef:UUID,body:ManualResponseRequest,conn:Conn,principal:Principal):
    try:
        return propose_response(conn,caseRef,actor_id=principal.user_id,request=body,manual=True)
    except (ResponseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc


@router.post('/{caseRef}/responses/{recommendationRef}/approve',response_model=ResponseMutation,
             operation_id='approveCaseResponse',dependencies=[MutationRole])
def approve(caseRef:UUID,recommendationRef:UUID,body:ResponseDecisionRequest,conn:Conn,principal:Principal):
    try:
        return decide_response(conn,caseRef,recommendationRef,actor_id=principal.user_id,decision='approved',request=body)
    except (ResponseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc


@router.post('/{caseRef}/responses/{recommendationRef}/reject',response_model=ResponseMutation,
             operation_id='rejectCaseResponse',dependencies=[MutationRole])
def reject(caseRef:UUID,recommendationRef:UUID,body:ResponseDecisionRequest,conn:Conn,principal:Principal):
    try:
        return decide_response(conn,caseRef,recommendationRef,actor_id=principal.user_id,decision='rejected',request=body)
    except (ResponseConflict,PermissionError,LookupError) as exc:
        raise _error(exc) from exc
