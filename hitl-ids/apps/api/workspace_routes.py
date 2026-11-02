"""One product's administrator-controlled operational workspaces."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from apps.api import auth, workspaces


class WorkspaceCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    active: bool
    ready: bool
    alertCount: int | None
    lastPreparedAt: str | None
    rawRecords: int | None
    stagedAlerts: int | None
    workloadSha256: str | None


class WorkspaceAction(BaseModel):
    actor: str
    action: str
    workspace: str
    reason: str
    created_at: str


class WorkspaceState(BaseModel):
    activeWorkspaceId: str
    activeWorkspaceName: str
    workspaces: list[WorkspaceInfo]
    actions: list[WorkspaceAction]


class WorkspaceCurrent(BaseModel):
    id: str
    name: str


router = APIRouter(tags=["Operational workspaces"])
Admin = Annotated[auth.Principal, Depends(auth.require_role("system_admin", readonly=True))]
Principal = Annotated[auth.Principal, Depends(auth.current_readonly_user)]


@router.get("/api/workspace/current", response_model=WorkspaceCurrent,
            operation_id="getCurrentWorkspace")
def current(request: Request, principal: Principal) -> WorkspaceCurrent:
    active = workspaces.selected_id(request)
    return WorkspaceCurrent(id=active, name=workspaces.NAMES[active])


@router.get("/api/admin/workspaces", response_model=WorkspaceState,
            operation_id="listOperationalWorkspaces")
def list_workspaces(request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.state(request))


@router.post("/api/admin/workspaces/{workspaceId}/activate", response_model=WorkspaceState,
             operation_id="activateOperationalWorkspace")
def activate(workspaceId: str, body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.activate(request, workspaceId, principal.username, body.reason))


@router.post("/api/admin/workspaces/v3-1-replay/prepare", response_model=WorkspaceState,
             operation_id="prepareV31Replay")
def prepare(body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.prepare(request, principal.username, body.reason))


@router.post("/api/admin/workspaces/v3-1-replay/reset", response_model=WorkspaceState,
             operation_id="resetV31Replay")
def reset(body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.reset(request, principal.username, body.reason))
