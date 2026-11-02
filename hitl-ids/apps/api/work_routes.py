"""Explicit POST-only work claims; inspection never arbitrates ownership."""
import sqlite3
from uuid import UUID
from fastapi import APIRouter, Query
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn, Principal, MutationRole, _id
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.analyst_work import ClaimCommand, ClaimResult, WorkView, WorkEvent, WorkConflict, claim, read_work, history

router=APIRouter(prefix='/api/v2/alerts',tags=['Shared analyst work'])

@router.get('/{alertRef}/work',response_model=WorkView,operation_id='getAnalystWork')
def get_work(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal):
    with conn:
        conn.execute('BEGIN')
        return read_work(conn,_id(conn,alertRef),principal.user_id)

@router.get('/{alertRef}/work/events',response_model=list[WorkEvent],operation_id='getAnalystWorkHistory')
def get_history(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with conn:
        conn.execute('BEGIN')
        return history(conn,_id(conn,alertRef),limit,offset)

@router.post('/{alertRef}/work/claim',response_model=ClaimResult,dependencies=[MutationRole],operation_id='claimAnalystWork')
def post_claim(alertRef:UUID,body:ClaimCommand,conn:Conn,principal:Principal):
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
