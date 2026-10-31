"""Authenticated eligibility review and admission; no raw-event ingestion endpoint."""
from fastapi import APIRouter, Query
from apps.api.contract.common import Page, PageInfo
from apps.api.contract.external_admission import ExternalAdmissionView, ExternalAdmissionResponse
from apps.api.deps import ApiError
from apps.api.routing_routes import Conn, Principal, MutationRole
from apps.api.read_only import ReadConn, ReadPrincipal
from packages.detection.external_admission import (
    AdmissionRequest, EligibilityRequest, AdmissionConflict, latest_review, admission_record,
    review_eligibility, admit_external, validate_source,
)

router = APIRouter(prefix='/api/v2/external-alerts', tags=['External admission'])


def _view(conn, inbox_id, principal):
    source = conn.execute('SELECT * FROM external_alert_inbox WHERE id=?', (inbox_id,)).fetchone()
    if source is None:
        raise ApiError(404, 'NOT_FOUND', 'External inbox row not found')
    source = dict(source)
    review = latest_review(conn, inbox_id)
    admitted = admission_record(conn, inbox_id)
    projection = conn.execute('SELECT id,operational_alert_ref FROM operational_alerts_v2 WHERE external_inbox_id=?',
                              (inbox_id,)).fetchone()
    status, reason = 'staged', 'Explicit eligibility review required'
    valid = True
    try:
        validate_source(source)
    except AdmissionConflict:
        valid = False
        status, reason = 'failed', 'Source integrity or policy validation failed; admission blocked'
    if valid and review:
        status = 'eligible' if review['decision'] == 'accepted' else 'held'
        reason = review['reason']
    if projection and not admitted:
        status, reason = 'held', 'Pre-existing V2 projection requires manual reconciliation'
    if admitted:
        status, reason = 'admitted', 'Operational admission completed'
    authorized = principal.role in ('security_analyst', 'system_admin')
    return ExternalAdmissionView(
        external_inbox_id=inbox_id, canonical_alert_id=source['canonical_alert_id'],
        detector='Suricata', signature=source['detection_title'], category=source['detection_category'],
        native_severity=source['native_severity'], confidence=None, source_ip=source['source_ip'],
        destination_ip=source['destination_ip'], source_port=source['source_port'],
        destination_port=source['destination_port'], protocol=source['protocol'],
        occurred_at=source['occurred_at'], occurred_at_timezone_offset=source['occurred_at_timezone_offset'],
        status=status, status_reason=reason, staging_decision=source['admission_decision'],
        proposed_priority=source['proposed_operational_priority'], proposal_policy_version=source['admission_policy_version'],
        review_id=review['id'] if review else None, review_decision=review['decision'] if review else None,
        review_reason=review['reason'] if review else None, review_actor_id=review['actor_id'] if review else None,
        operational_alert_ref=projection['operational_alert_ref'] if projection else None,
        operational_alert_id=projection['id'] if projection else None,
        admitted_at=admitted['created_at'] if admitted else None,
        admission_actor_id=admitted['actor_id'] if admitted else None,
        can_review=authorized and valid and not projection, can_admit=authorized and status == 'eligible')


@router.get('', response_model=Page[ExternalAdmissionView], operation_id='listExternalAdmissions')
def list_external(conn: ReadConn, principal: ReadPrincipal, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    with conn:
        conn.execute('BEGIN')
        total = conn.execute('SELECT count(*) FROM external_alert_inbox').fetchone()[0]
        ids = conn.execute('SELECT id FROM external_alert_inbox ORDER BY id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        items = [_view(conn, row[0], principal) for row in ids]
        return Page(items=items, page=PageInfo(total=total, limit=limit, offset=offset, returned=len(items)))


@router.get('/{inboxId}', response_model=ExternalAdmissionView, operation_id='getExternalAdmission')
def get_external(inboxId: int, conn: ReadConn, principal: ReadPrincipal):
    with conn:
        conn.execute('BEGIN')
        return _view(conn, inboxId, principal)


def _error(exc):
    if isinstance(exc, PermissionError):
        return ApiError(403, 'FORBIDDEN_ROLE', str(exc))
    if isinstance(exc, LookupError):
        return ApiError(404, 'NOT_FOUND', str(exc))
    return ApiError(409, 'ADMISSION_CONFLICT', str(exc))


@router.post('/{inboxId}/eligibility', response_model=ExternalAdmissionView,
             operation_id='reviewExternalEligibility', dependencies=[MutationRole])
def review(inboxId: int, body: EligibilityRequest, conn: Conn, principal: Principal):
    try:
        review_eligibility(conn, inboxId, actor_id=principal.user_id, request=body)
    except (AdmissionConflict, PermissionError, LookupError) as exc:
        raise _error(exc) from exc
    return get_external(inboxId, conn, principal)


@router.post('/{inboxId}/admit', response_model=ExternalAdmissionResponse,
             operation_id='admitExternalAlert', dependencies=[MutationRole])
def admit(inboxId: int, body: AdmissionRequest, conn: Conn, principal: Principal):
    try:
        _, replayed = admit_external(conn, inboxId, actor_id=principal.user_id, request=body)
    except (AdmissionConflict, PermissionError, LookupError) as exc:
        raise _error(exc) from exc
    return ExternalAdmissionResponse(view=get_external(inboxId, conn, principal), replayed=replayed)
