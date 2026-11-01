"""Authenticated Tier 1 human verdict; reads never migrate or mutate."""
from uuid import UUID
from fastapi import APIRouter,Query
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn,Principal,MutationRole
from apps.api.read_only import ReadConn,ReadPrincipal
from packages.detection.analyst_verdict import VerdictCommand,VerdictView,VerdictHistory,VerdictMutation,VerdictConflict,read_verdict,verdict_history,record_verdict

router=APIRouter(prefix='/api/v2/alerts',tags=['Analyst verdict'])

def error(exc):
    code,status=('NOT_FOUND',404) if isinstance(exc,LookupError) else ('FORBIDDEN_ROLE',403) if isinstance(exc,PermissionError) else ('VERDICT_CONFLICT',409)
    return ApiError(status,code,str(exc))

@router.get('/{alertRef}/verdict',response_model=VerdictView,operation_id='getAnalystVerdict')
def current(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal):
    try:
        with conn:
            conn.execute('BEGIN');return read_verdict(conn,alertRef,principal.user_id)
    except LookupError as exc: raise error(exc) from exc

@router.get('/{alertRef}/verdict-history',response_model=VerdictHistory,operation_id='getAnalystVerdictHistory')
def history(alertRef:UUID,conn:ReadConn,principal:ReadPrincipal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    try:
        with conn:
            conn.execute('BEGIN');return verdict_history(conn,alertRef,limit,offset)
    except LookupError as exc: raise error(exc) from exc

@router.post('/{alertRef}/verdict',response_model=VerdictMutation,dependencies=[MutationRole],operation_id='recordAnalystVerdict')
def record(alertRef:UUID,body:VerdictCommand,conn:Conn,principal:Principal):
    try: return record_verdict(conn,alertRef,actor_id=principal.user_id,request=body)
    except (LookupError,PermissionError,VerdictConflict) as exc: raise error(exc) from exc
