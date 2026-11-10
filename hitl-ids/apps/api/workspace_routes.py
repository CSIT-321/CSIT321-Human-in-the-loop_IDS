"""One product's administrator-controlled operational workspaces."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from apps.api import auth, workspaces


class WorkspaceCommand(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReplayPrepareCommand(WorkspaceCommand):
    mode: Literal['full', 'presentation', 'packet'] = 'full'


class ReplayAdvanceCommand(WorkspaceCommand):
    requestId: UUID
    count: Literal[1, 5, 150]


class DetectionFlowChainCommand(WorkspaceCommand):
    enabled: bool


class DetectionState(BaseModel):
    """Program-wide detector switches. They apply to every workspace and to both data sources."""
    flowChainEnabled: bool


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
    preparationMode: Literal['full', 'presentation', 'packet'] | None = None
    learningProcessed: int | None = None
    holdoutArrived: int | None = None
    holdoutRemaining: int | None = None
    playbackState: Literal['running', 'paused', 'complete'] | None = None
    lastArrivalAt: str | None = None


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
    detection: DetectionState


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
def prepare(body: ReplayPrepareCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.prepare(request, principal.username, body.reason, body.mode))


@router.post("/api/admin/workspaces/v3-1-replay/reset", response_model=WorkspaceState,
             operation_id="resetV31Replay")
def reset(body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.reset(request, principal.username, body.reason))


@router.post('/api/admin/workspaces/v3-1-replay/advance', response_model=WorkspaceState,
             operation_id='advancePresentationReplay')
def advance(body: ReplayAdvanceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.advance(request, body.count, principal.username,
        body.reason, str(body.requestId)))


@router.post('/api/admin/workspaces/v3-1-replay/start', response_model=WorkspaceState,
             operation_id='startPresentationReplay')
def start(body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.playback(request, principal.username, body.reason, 'start'))


@router.post('/api/admin/detection/flow-chain', response_model=WorkspaceState,
             operation_id='setDetectionFlowChain')
def set_detection_flow_chain(body: DetectionFlowChainCommand, request: Request, principal: Admin) -> WorkspaceState:
    """Program-wide: turn the CICFlowMeter chain on or off. Not tied to a workspace or a replay."""
    return WorkspaceState.model_validate(
        workspaces.set_detection_chain(request, principal.username, body.reason, body.enabled))


@router.post('/api/admin/workspaces/v3-1-replay/pause', response_model=WorkspaceState,
             operation_id='pausePresentationReplay')
def pause(body: WorkspaceCommand, request: Request, principal: Admin) -> WorkspaceState:
    return WorkspaceState.model_validate(workspaces.playback(request, principal.username, body.reason, 'pause'))
