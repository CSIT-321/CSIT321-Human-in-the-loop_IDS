"""Current HITL governance and operational health, with no policy editing."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from apps.api import auth, operational_queue, workspaces
from apps.api.contract.admin_current import (
    AdminGovernance, AdminOverview, AdminUser, AdminUsers, ClaimPolicyView, MemoryCounts,
)
from apps.api.contract.current_audit import AuditCategory, CurrentAuditPage
from apps.api.current_audit import list_current
from apps.api.read_only import ReadConn
from packages.detection.analyst_work import policy as claim_policy
from packages.detection.attack_classification import load_classification_policy
from packages.detection.selective_review_policy import load_policy as load_selective_policy
from packages.detection.system_routing import load_system_routing_policy
from packages.detection.triage_memory import load_auto_policy, load_config as load_memory_config, read_memory

router = APIRouter(prefix='/api/admin', tags=['Current Admin'])
Admin = Annotated[auth.Principal, Depends(auth.require_role('system_admin', readonly=True))]


@router.get('/overview', response_model=AdminOverview, operation_id='getCurrentAdminOverview')
def overview(request: Request, conn: ReadConn, principal: Admin) -> AdminOverview:
    with conn:
        conn.execute('BEGIN')
        operational = operational_queue.summary(conn)
        refs = [row[0] for row in conn.execute('SELECT lesson_ref FROM triage_memory_lessons')]
        statuses = [read_memory(conn, ref).status for ref in refs]
    workspace_id = workspaces.selected_id(request)
    return AdminOverview(
        active_workspace_id=workspace_id, active_workspace_name=workspaces.NAMES[workspace_id],
        workspace_ready=True, database_ready=True, workspace_alert_count=operational.total_alerts,
        operational=operational,
        memory=MemoryCounts(total=len(statuses), active=statuses.count('active'),
                            conflict_review=statuses.count('conflict_review')),
        classification_policy_version=load_classification_policy().version,
        routing_policy_version=load_system_routing_policy().version,
        memory_policy_version=load_memory_config().version,
        selective_review_policy_version=load_selective_policy().version,
    )


@router.get('/governance', response_model=AdminGovernance, operation_id='getCurrentHitlGovernance')
def governance(principal: Admin) -> AdminGovernance:
    return AdminGovernance(
        classification=load_classification_policy(), routing=load_system_routing_policy(),
        memory=load_memory_config(), auto_learning=load_auto_policy(),
        selective_review=load_selective_policy(), analyst_work=ClaimPolicyView.model_validate(claim_policy()),
    )


@router.get('/users', response_model=AdminUsers, operation_id='listCurrentAdminUsers')
def users(conn: ReadConn, principal: Admin) -> AdminUsers:
    with conn:
        conn.execute('BEGIN')
        rows = conn.execute('''SELECT username,display_name,role,status,last_login FROM users
                               WHERE role IN ('security_analyst','system_admin')
                                 AND NOT (
                                   (username='v3-analyst-1' AND display_name='V3 Analyst 1' AND email='v3-replay-1@example.test') OR
                                   (username='v3-analyst-2' AND display_name='V3 Analyst 2' AND email='v3-replay-2@example.test') OR
                                   (username='v3-analyst-3' AND display_name='V3 Analyst 3' AND email='v3-replay-3@example.test'))
                               ORDER BY username''').fetchall()
    return AdminUsers(items=[AdminUser(**dict(row)) for row in rows])


@router.get('/audit/current', response_model=CurrentAuditPage, operation_id='listCurrentHitlAudit')
def current_audit(request: Request, conn: ReadConn, principal: Admin,
                  limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
                  category: AuditCategory | None = None, actor: str | None = Query(None, max_length=100),
                  decision_source: str | None = Query(None, pattern='^(analyst|system_policy|historical_migration|admin)$'),
                  object_type: str | None = Query(None, pattern='^(workspace|alert|case|lesson|recommendation)$'),
                  search: str | None = Query(None, max_length=120),
                  workspace: str | None = Query(None, pattern='^(operational|v3-1-replay|global)$')) -> CurrentAuditPage:
    selected = workspaces.selected_id(request)
    _, control, _ = workspaces.paths(request)
    with conn:
        conn.execute('BEGIN')
        return list_current(conn, control, selected, limit=limit, offset=offset,
            category=category, actor=actor, decision_source=decision_source,
            object_type=object_type, search=search, event_workspace=workspace)
