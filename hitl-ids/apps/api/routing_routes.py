"""Authenticated V2-only routing. No ingestion or policy mutation endpoints."""
from typing import Annotated
from uuid import UUID
import sqlite3

from fastapi import APIRouter, Depends, Query
from apps.api import auth
from apps.api.contract.common import Page, PageInfo
from apps.api.contract.routing import RoutingView, RoutingResponse
from apps.api.deps import ApiError, get_connection
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.adapters.operational_v2 import read_triage
from packages.detection.routing import (
    RoutingRequest, RoutingAction, RoutingConflict, allowed_actions, decode_audit,
    route_alert, state_version,
)

router = APIRouter(prefix='/api/v2/alerts', tags=['V2 routing'])
Conn = Annotated[sqlite3.Connection, Depends(get_connection)]
Principal = Annotated[auth.Principal, Depends(auth.current_user)]
MutationRole = Depends(auth.require_role('security_analyst', 'system_admin'))


def _id(conn, ref):
    row = conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?', (str(ref),)).fetchone()
    if row is None:
        raise ApiError(404, 'NOT_FOUND', 'V2 alert not found')
    return row[0]


def _view(conn, alert_id, principal):
    row = conn.execute('SELECT * FROM operational_alerts_v2 WHERE id=?', (alert_id,)).fetchone()
    state = read_triage(conn, alert_id)
    audit = conn.execute('SELECT * FROM operational_routing_audit WHERE operational_alert_id=? '
                         'ORDER BY id DESC LIMIT 1', (alert_id,)).fetchone()
    return RoutingView(operational_alert_ref=row['operational_alert_ref'], title=row['detection_title'],
        detector_name=row['detector_name'], state=state, state_version=state_version(state),
        review_reasons=[state.review_reason], latest_decision=decode_audit(audit) if audit else None,
        allowed_actions=list(allowed_actions(state)) if principal.role in ('security_analyst', 'system_admin') else [])


@router.get('', response_model=Page[RoutingView], operation_id='listV2Routing')
def list_routing(conn: ReadConn, principal: ReadPrincipal, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0)):
    with conn:
        conn.execute('BEGIN')
        total = conn.execute('SELECT count(*) FROM operational_alerts_v2').fetchone()[0]
        ids = conn.execute('SELECT id FROM operational_alerts_v2 ORDER BY id LIMIT ? OFFSET ?', (limit, offset))
        items = [_view(conn, row[0], principal) for row in ids.fetchall()]
        return Page(items=items, page=PageInfo(total=total, limit=limit, offset=offset, returned=len(items)))


@router.get('/{alertRef}/triage-state', response_model=RoutingView, operation_id='getV2Routing')
def get_routing(alertRef: UUID, conn: ReadConn, principal: ReadPrincipal):
    with conn:
        conn.execute('BEGIN')
        return _view(conn, _id(conn, alertRef), principal)


def _decide(ref, request, conn, principal, action: RoutingAction):
    try:
        audit, replayed = route_alert(conn, _id(conn, ref), actor_id=principal.user_id,
                                     action=action, request=request)
    except PermissionError as exc:
        raise ApiError(403, 'FORBIDDEN_ROLE', str(exc)) from exc
    except RoutingConflict as exc:
        raise ApiError(409, 'ROUTING_CONFLICT', str(exc)) from exc
    with conn:
        conn.execute('BEGIN')
        return RoutingResponse(view=_view(conn, audit.operational_alert_id, principal), audit=audit, replayed=replayed)


@router.post('/{alertRef}/admit-tier1', response_model=RoutingResponse, dependencies=[MutationRole], operation_id='admitV2Tier1')
def admit(alertRef: UUID, body: RoutingRequest, conn: Conn, principal: Principal):
    return _decide(alertRef, body, conn, principal, 'admit_tier1')


@router.post('/{alertRef}/tier2/approve', response_model=RoutingResponse, dependencies=[MutationRole], operation_id='approveV2Tier2')
def approve(alertRef: UUID, body: RoutingRequest, conn: Conn, principal: Principal):
    return _decide(alertRef, body, conn, principal, 'approve_tier2')


@router.post('/{alertRef}/tier2/reject', response_model=RoutingResponse, dependencies=[MutationRole], operation_id='rejectV2Tier2')
def reject(alertRef: UUID, body: RoutingRequest, conn: Conn, principal: Principal):
    return _decide(alertRef, body, conn, principal, 'reject_tier2')


@router.post('/{alertRef}/tier2/escalate', response_model=RoutingResponse, dependencies=[MutationRole], operation_id='escalateV2Tier2')
def escalate(alertRef: UUID, body: RoutingRequest, conn: Conn, principal: Principal):
    return _decide(alertRef, body, conn, principal, 'manual_escalate')
