"""Authenticated V2-only routing. No ingestion or policy mutation endpoints."""
from typing import Annotated, Literal
from uuid import UUID
import sqlite3
import json

from fastapi import APIRouter, Depends, Query
from apps.api import auth
from apps.api.contract.common import Page, PageInfo
from apps.api.contract.routing import RoutingView, RoutingResponse, EscalateCaseResponse, OperationalSummary, QueueDetectionSummary
from apps.api import operational_queue
from packages.detection.tier2_escalation import EscalateCaseRequest, escalate_case
from packages.detection.tier2_cases import CaseConflict
from apps.api.deps import ApiError, get_connection
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.adapters.operational_v2 import read_triage, read_projection
from packages.contracts.operational_v2 import OperationalAlertV2, HandlingRouteV2, PriorityBandV2
from packages.contracts.suricata_bundle import AttackCategory
from packages.detection.selective_review import Disposition, effective_review
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


def _view(conn, alert_id, principal, review=None):
    row = conn.execute('SELECT * FROM operational_alerts_v2 WHERE id=?', (alert_id,)).fetchone()
    state = read_triage(conn, alert_id)
    audit = conn.execute('SELECT * FROM operational_routing_audit WHERE operational_alert_id=? '
                         'ORDER BY id DESC LIMIT 1', (alert_id,)).fetchone()
    case = conn.execute('SELECT case_ref FROM tier2_cases WHERE primary_operational_alert_id=?', (alert_id,)).fetchone()
    system = conn.execute('SELECT classification,routing_decision FROM operational_system_routing WHERE operational_alert_id=?', (alert_id,)).fetchone()
    bundle = json.loads(row['detector_evidence']).get('structured_evidence', {}).get('suricataBundle')
    return RoutingView(effective_review=review or effective_review(conn, row['operational_alert_ref']),
        classification=json.loads(system['classification']) if system else None,
        detection_summary=QueueDetectionSummary(source_ip=row['source_ip'], destination_ip=row['destination_ip'],
            destination_port=row['destination_port'], occurred_at=row['occurred_at'],
            related_signature_count=len(bundle['relatedSignatures']) if bundle else None,
            evidence_types=bundle['evidenceTypes'] if bundle else []),
        system_routing=json.loads(system['routing_decision']) if system else None, operational_alert_ref=row['operational_alert_ref'], title=row['detection_title'],
        detector_name=row['detector_name'], detector_source=row['detector_source'], state=state, state_version=state_version(state),
        review_reasons=[state.review_reason], latest_decision=decode_audit(audit) if audit else None,
        allowed_actions=list(allowed_actions(state)) if principal.role in ('security_analyst', 'system_admin') else [],
        case_ref=case['case_ref'] if case else None)


@router.get('', response_model=Page[RoutingView], operation_id='listV2Routing')
def list_routing(conn: ReadConn, principal: ReadPrincipal, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0),
                 handlingRoute: HandlingRouteV2 | None = None, reviewRequired: bool | None = None,
                 reviewDisposition: Disposition | None = None,
                 priorityBand: PriorityBandV2 | None = None,
                 routeClass: Literal['ROUTINE_REVIEW', 'CRITICAL_ESCALATION', 'EXPERT_REVIEW_REQUIRED'] | None = None,
                 attackCategory: AttackCategory | None = None, q: str | None = Query(None, max_length=200),
                 sort: Literal['priority_desc'] = 'priority_desc'):
    """Filter the full V2 dataset before paging. Order: Operational Priority DESC (null last),
    occurredAt instant DESC, operationalAlertRef ASC. Attention is evaluated read-only."""
    with conn:
        conn.execute('BEGIN')
        reviews = {}
        total, ids = operational_queue.queue_page(conn, limit=limit, offset=offset, reviews=reviews,
            handling_route=handlingRoute, review_required=reviewRequired, priority_band=priorityBand,
            review_disposition=reviewDisposition,
            route_class=routeClass, attack_category=attackCategory, q=q)
        items = [_view(conn, alert_id, principal, reviews.get(alert_id)) for alert_id in ids]
        return Page(items=items, page=PageInfo(total=total, limit=limit, offset=offset, returned=len(items)))


@router.get('/summary', response_model=OperationalSummary, operation_id='getV2AlertsSummary')
def get_summary(conn: ReadConn, principal: ReadPrincipal):
    """Whole-dataset current operational counts; categories intentionally overlap.
    One read-only snapshot; evaluate effective attention without changing stored state."""
    with conn:
        conn.execute('BEGIN')
        return operational_queue.summary(conn)


@router.get('/{alertRef}/triage-state', response_model=RoutingView, operation_id='getV2Routing')
def get_routing(alertRef: UUID, conn: ReadConn, principal: ReadPrincipal):
    with conn:
        conn.execute('BEGIN')
        return _view(conn, _id(conn, alertRef), principal)


@router.get('/{alertRef}/evidence', response_model=OperationalAlertV2, operation_id='getV2AlertEvidence')
def get_evidence(alertRef: UUID, conn: ReadConn, principal: ReadPrincipal):
    """Immutable source-neutral evidence; the read-only dependency never migrates or writes."""
    with conn:
        conn.execute('BEGIN')
        return read_projection(conn, _id(conn, alertRef))


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


@router.post('/{alertRef}/tier2/escalate-case', response_model=EscalateCaseResponse,
             dependencies=[MutationRole], operation_id='escalateV2Tier2Case')
def escalate_with_case(alertRef: UUID, body: EscalateCaseRequest, conn: Conn, principal: Principal):
    try:
        result = escalate_case(conn, alertRef, actor_id=principal.user_id, request=body)
    except PermissionError as exc:
        raise ApiError(403, 'FORBIDDEN_ROLE', str(exc)) from exc
    except LookupError as exc:
        raise ApiError(404, 'NOT_FOUND', str(exc)) from exc
    except (RoutingConflict, CaseConflict) as exc:
        raise ApiError(409, 'ROUTING_CONFLICT', str(exc)) from exc
    with conn:
        conn.execute('BEGIN')
        return EscalateCaseResponse(view=_view(conn, result.case.snapshot.detector.id, principal),
            audit=result.case.snapshot.routing_decision, case=result.case, event_id=result.event_id, replayed=result.replayed)
