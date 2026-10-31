"""Authenticated prospective structured assessments; no source/timestamp impersonation."""
from uuid import UUID
from fastapi import APIRouter, Query
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn, Principal, MutationRole
from packages.detection.context_store import FactRequest, FactPage, FactMutation, FactConflict, collect_fact, fact_page, resolved_for
from packages.detection.trusted_context import ResolvedTrustedContext

router=APIRouter(prefix='/api/v2',tags=['Trusted context'])


@router.get('/context/facts',response_model=FactPage,operation_id='listTrustedContextFacts')
def facts(conn:Conn,principal:Principal,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with conn:
        conn.execute('BEGIN')
        return fact_page(conn,limit,offset)


@router.post('/context/facts',response_model=FactMutation,dependencies=[MutationRole],operation_id='collectTrustedContextFact')
def collect(body:FactRequest,conn:Conn,principal:Principal):
    try: return collect_fact(conn,actor_id=principal.user_id,request=body)
    except LookupError as exc: raise ApiError(404,'NOT_FOUND',str(exc)) from exc
    except PermissionError as exc: raise ApiError(403,'FORBIDDEN_ROLE',str(exc)) from exc
    except FactConflict as exc: raise ApiError(409,'CONTEXT_CONFLICT',str(exc)) from exc
    except ValueError as exc: raise ApiError(400,'INVALID_CONTEXT',str(exc)) from exc


@router.get('/alerts/{alertRef}/context',response_model=ResolvedTrustedContext,operation_id='getTrustedAlertContext')
def context(alertRef:UUID,conn:Conn,principal:Principal):
    try:
        with conn:
            conn.execute('BEGIN')
            return resolved_for(conn,alertRef)
    except LookupError as exc: raise ApiError(404,'NOT_FOUND',str(exc)) from exc
