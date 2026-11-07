"""Explicit POST-only work claims; inspection never arbitrates ownership."""
import sqlite3
from uuid import UUID
from fastapi import APIRouter, Header, Query, Request, Response
from apps.api.deps import ApiError
from apps.api import workspaces
from apps.api.routing_routes import Conn, Principal, MutationRole, _id
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.analyst_work import ClaimCommand, ClaimResult, WorkView, WorkEvent, WorkConflict, claim, read_work, history
from packages.detection.analyst_work import ReleaseCommand, ReleaseResult, release

router=APIRouter(prefix='/api/v2/alerts',tags=['Shared analyst work'])

@router.get('/{alertRef}/work',response_model=WorkView,operation_id='getAnalystWork')
def get_work(alertRef:UUID,request:Request,response:Response,conn:ReadConn,principal:ReadPrincipal):
    response.headers['X-Operational-Workspace']=workspaces.selected_id(request)
    with conn:
        conn.execute('BEGIN')
        return read_work(conn,_id(conn,alertRef),principal.user_id)

@router.get('/{alertRef}/work/events',response_model=list[WorkEvent],operation_id='getAnalystWorkHistory')
def get_history(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with conn:
        conn.execute('BEGIN')
        return history(conn,_id(conn,alertRef),limit,offset)

@router.post('/{alertRef}/work/claim',response_model=ClaimResult,dependencies=[MutationRole],operation_id='claimAnalystWork')
def post_claim(alertRef:UUID,body:ClaimCommand,request:Request,conn:Conn,principal:Principal,
               expected_workspace:str|None=Header(None,alias='X-Operational-Workspace')):
    if expected_workspace is not None and expected_workspace!=workspaces.selected_id(request):
        raise ApiError(409,'WORKSPACE_CHANGED','The active workspace changed. Refresh the queue and select an alert again.')
    try:
        result=claim(conn,alertRef,actor_id=principal.user_id,request=body)
    except PermissionError as exc: raise ApiError(403,'FORBIDDEN_ROLE',str(exc)) from exc
    except LookupError as exc: raise ApiError(404,'NOT_FOUND',str(exc)) from exc
    except WorkConflict as exc: raise ApiError(409,'WORK_CONFLICT',str(exc)) from exc
    except sqlite3.OperationalError as exc:
        if 'locked' not in str(exc).lower() and 'busy' not in str(exc).lower(): raise
        raise ApiError(409,'WORK_RETRY','The work request could not be confirmed. Refresh the queue and retry with the same request.') from exc
    if result.outcome!='claimed':
        message=('Another analyst attempted to claim this alert at the same time. No ownership was assigned. Please select an alert again.'
                 if result.outcome=='contended' else 'This alert is no longer eligible for Tier 1 claiming. Refresh the shared queue.')
        raise ApiError(409,'CLAIM_CONTENTION' if result.outcome=='contended' else 'WORK_INELIGIBLE',message,result.model_dump(mode='json',by_alias=True))
    return result


@router.post('/{alertRef}/work/release',response_model=ReleaseResult,dependencies=[MutationRole],operation_id='releaseAnalystWork')
def post_release(alertRef:UUID,body:ReleaseCommand,conn:Conn,principal:Principal):
    """Decision D5: the owner releases their claim; an administrator releases any claim with a reason."""
    try:
        return release(conn,alertRef,actor_id=principal.user_id,request=body)
    except PermissionError as exc: raise ApiError(403,'FORBIDDEN_ROLE',str(exc)) from exc
    except LookupError as exc: raise ApiError(404,'NOT_FOUND',str(exc)) from exc
    except WorkConflict as exc: raise ApiError(409,'WORK_CONFLICT',str(exc)) from exc
    except ValueError as exc: raise ApiError(400,'RELEASE_REASON_REQUIRED',str(exc)) from exc
