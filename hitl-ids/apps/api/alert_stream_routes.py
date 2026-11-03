"""Read-only, workspace-bound arrival notifications for committed operational alerts."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from apps.api import auth, workspaces

router = APIRouter()


def _read(path: Path, query: str, parameters: tuple = ()) -> list[sqlite3.Row]:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn.execute(query, parameters).fetchall()


def _selection(control: Path) -> tuple[str, int]:
    if not control.exists():
        return "operational", 0
    rows = _read(control, """SELECT s.workspace,
        COALESCE((SELECT max(id) FROM actions WHERE action='workspace_activated'), 0) AS epoch
        FROM selection s WHERE s.id=1""")
    return (str(rows[0]["workspace"]), int(rows[0]["epoch"])) if rows else ("operational", 0)


# An admission and its routing evidence commit together. Reading this join means a
# notification never precedes the actual queue row and never materializes one on GET.
_ARRIVALS = """FROM external_operational_admission admission
    JOIN operational_alerts_v2 alert ON alert.id=admission.operational_alert_id
    JOIN operational_triage_state_v2 state ON state.operational_alert_id=alert.id
    JOIN operational_system_routing system ON system.operational_alert_id=alert.id
    WHERE system.routing_audit_id=admission.routing_audit_id
      AND system.policy_audit_id=admission.policy_audit_id"""


def _last_id(database: Path) -> int:
    rows = _read(database, f"SELECT COALESCE(max(admission.id),0) AS id {_ARRIVALS}")
    return int(rows[0]["id"])


def _arrivals(database: Path, cursor: int) -> list[sqlite3.Row]:
    return _read(database, f"""SELECT admission.id, admission.created_at,
        alert.operational_alert_ref {_ARRIVALS} AND admission.id>? ORDER BY admission.id LIMIT 100""", (cursor,))


async def stream_arrivals(request: Request, database: Path, control: Path,
                          workspace_id: str, epoch: int):
    selected, current_epoch = _selection(control)
    if (selected, current_epoch) != (workspace_id, epoch):
        yield "event: workspace_changed\ndata: " + json.dumps({"workspaceId": selected}) + "\n\n"
        return
    cursor = _last_id(database)
    yield ": connected\n\n"
    ticks = 0
    while not await request.is_disconnected():
        await asyncio.sleep(1)
        selected, current_epoch = _selection(control)
        if (selected, current_epoch) != (workspace_id, epoch):
            yield "event: workspace_changed\ndata: " + json.dumps({"workspaceId": selected}) + "\n\n"
            return
        for row in _arrivals(database, cursor):
            cursor = int(row["id"])
            payload = {"eventId": f"{workspace_id}:{cursor}", "workspaceId": workspace_id,
                       "operationalAlertRef": row["operational_alert_ref"],
                       "timestamp": row["created_at"]}
            yield f"id: {payload['eventId']}\nevent: alert_arrived\ndata: {json.dumps(payload)}\n\n"
        ticks += 1
        if ticks % 15 == 0:
            yield ": heartbeat\n\n"
        # Force periodic JWT and account revalidation by a fresh authorized GET.
        if ticks >= 60:
            return


@router.get("/api/v2/alerts/stream", operation_id="streamOperationalAlertArrivals")
def stream_operational_alert_arrivals(request: Request,
                                      principal: auth.Principal = Depends(auth.current_stream_user)) -> StreamingResponse:
    del principal
    database = workspaces.active_database(request)
    _, control, _ = workspaces.paths(request)
    workspace_id = workspaces.selected_id(request)
    _, epoch = _selection(control)
    return StreamingResponse(stream_arrivals(request, database, control, workspace_id, epoch),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
                                      "X-Operational-Workspace": workspace_id})
