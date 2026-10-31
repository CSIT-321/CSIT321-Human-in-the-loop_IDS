"""Authenticated opt-in collection; export/report GETs perform SELECTs only."""
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends
from apps.api import auth
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn, Principal, MutationRole
from packages.contracts.operational_v2 import V2Contract
from packages.detection import prospective_collection as service
from packages.evaluation.prospective_recorded import RecordedArchive, export_connection, evaluate_recorded

router=APIRouter(prefix='/api/v2/collection',tags=['Prospective collection'])
AdminRole=Depends(auth.require_role('system_admin'))


class CollectionDocument(V2Contract):
    payload: dict[str,Any]


def invoke(callback):
    try: return callback()
    except LookupError as exc: raise ApiError(404,'NOT_FOUND',str(exc)) from exc
    except PermissionError as exc: raise ApiError(403,'FORBIDDEN_ROLE',str(exc)) from exc
    except service.CollectionConflict as exc: raise ApiError(409,'COLLECTION_CONFLICT',str(exc)) from exc
    except ValueError as exc: raise ApiError(400,'INVALID_COLLECTION',str(exc)) from exc


@router.get('/runs',response_model=service.RunPage,operation_id='listCollectionRuns')
def runs(conn:Conn,principal:Principal):
    with conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return service.list_runs(conn)


@router.post('/runs',response_model=service.RunView,dependencies=[AdminRole],operation_id='createCollectionRun')
def create(body:service.RunCreate,conn:Conn,principal:Principal):
    return invoke(lambda:service.create_run(conn,principal.user_id,body))


@router.get('/runs/{runRef}',response_model=service.RunView,operation_id='getCollectionRun')
def run(runRef:UUID,conn:Conn,principal:Principal):
    with conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return invoke(lambda:service.read_run(conn,runRef))


@router.post('/runs/{runRef}/open',response_model=service.RunView,dependencies=[AdminRole],operation_id='openCollectionRun')
def open_run(runRef:UUID,body:service.RunCommand,conn:Conn,principal:Principal):
    return invoke(lambda:service.change_run(conn,runRef,principal.user_id,'open',body))


@router.post('/runs/{runRef}/close',response_model=service.RunView,dependencies=[AdminRole],operation_id='closeCollectionRun')
def close_run(runRef:UUID,body:service.RunCommand,conn:Conn,principal:Principal):
    return invoke(lambda:service.change_run(conn,runRef,principal.user_id,'close',body))


@router.post('/runs/{runRef}/evaluated',response_model=service.RunView,dependencies=[AdminRole],operation_id='recordCollectionEvaluation')
def evaluated(runRef:UUID,body:service.RunCommand,conn:Conn,principal:Principal):
    return invoke(lambda:service.change_run(conn,runRef,principal.user_id,'evaluated',body))


@router.post('/runs/{runRef}/observations',response_model=service.RunView,dependencies=[MutationRole],operation_id='recordCollectionObservation')
def observe(runRef:UUID,body:service.ObservationRequest,conn:Conn,principal:Principal):
    return invoke(lambda:service.observe(conn,runRef,principal.user_id,body))


@router.get('/runs/{runRef}/export',response_model=RecordedArchive,operation_id='exportRecordedCollection')
def export(runRef:UUID,conn:Conn,principal:Principal):
    with conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return invoke(lambda:export_connection(conn,runRef))


@router.get('/runs/{runRef}/report',response_model=CollectionDocument,operation_id='evaluateRecordedCollection')
def report(runRef:UUID,conn:Conn,principal:Principal):
    with conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return invoke(lambda:CollectionDocument(payload=evaluate_recorded(export_connection(conn,runRef))))
