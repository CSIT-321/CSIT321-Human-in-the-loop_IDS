import { useEffect, useRef, useState } from "react";

import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";
import { Card, PageHeader, Pill } from "../../components/ui";

export function WorkspacesPage() {
  const state = useApi(signal => unwrap(api.GET("/api/admin/workspaces", { signal })), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("Prepare isolated V3.1 analyst demonstration");
  const [mode, setMode] = useState<"full" | "presentation">("full");
  const reload = useRef(state.reload); reload.current = state.reload;
  useEffect(() => { const timer = setInterval(() => reload.current(), 2000); return () => clearInterval(timer); }, []);

  async function act(action: "prepare" | "reset" | "activate" | "start" | "pause" | "advance",
                     id = "v3-1-replay", count: 1 | 5 | 150 = 1) {
    if (action === "reset" && !window.confirm(
      "Reset V3.1 Demo Replay? This permanently removes only its isolated operational alerts, verdicts, memory and cases. The Operational workspace and official frozen evaluation remain unchanged.")) return;
    setBusy(`${action}:${id}`); setError(null);
    try {
      const body = { reason: reason.trim() || "Administrator workspace action" };
      if (action === "prepare") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/prepare", { body: { ...body, mode } }));
      else if (action === "reset") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/reset", { body }));
      else if (action === "start") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/start", { body }));
      else if (action === "pause") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/pause", { body }));
      else if (action === "advance") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/advance", {
        body: { ...body, count, requestId: crypto.randomUUID() },
      }));
      else await unwrap(api.POST("/api/admin/workspaces/{workspaceId}/activate", {
        params: { path: { workspaceId: id } }, body,
      }));
      state.reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(null); }
  }

  return <div className="min-w-0 space-y-5">
    <PageHeader title="Operational Workspace" subtitle="Choose which isolated operational database Analysts use in this product." />
    <ApiView resource={state}>{data => <>
      <Card title="Active workspace"><p className="text-xl font-semibold text-text">{data.activeWorkspaceName}</p>
        <p className="mt-2 text-sm text-muted">Analyst requests resolve this selection in the backend. A request already in progress finishes in its original workspace.</p>
      </Card>
      <label className="block max-w-xl text-xs text-muted">Reason for administrative action
        <input aria-label="Reason for workspace action" value={reason} onChange={event => setReason(event.target.value)}
          className="mt-1 block w-full rounded-sm border border-border bg-raised px-3 py-2 text-sm text-text" />
      </label>
      {error && <p role="alert" className="rounded-sm border border-danger p-3 text-sm text-danger">{error}</p>}
      <div className="grid gap-4 lg:grid-cols-2">{data.workspaces.map(workspace => <Card key={workspace.id}
        title={<span className="flex items-center gap-2">{workspace.name}<Pill tone={workspace.active ? "ok" : "muted"}>{workspace.active ? "Active" : "Inactive"}</Pill></span>}>
        <div className="space-y-2 text-sm text-muted">
          <p>Database: <strong className="text-text">{workspace.ready ? "Ready" : "Not prepared"}</strong></p>
          <p>Operational alerts: <strong className="text-text">{workspace.alertCount ?? "N/A"}</strong></p>
          {workspace.id === "v3-1-replay" && <>
            {!workspace.ready && <label className="block text-sm text-text">Preparation mode
              <select aria-label="Replay preparation mode" value={mode} onChange={event => setMode(event.target.value as typeof mode)}
                className="mt-1 block w-full rounded-sm border border-border bg-raised px-3 py-2">
                <option value="full">Full Replay · all 200 now</option>
                <option value="presentation">Presentation Replay · progressive Holdout</option>
              </select>
            </label>}
            {workspace.ready && <p>Mode: <strong className="text-text">{workspace.preparationMode === "presentation" ? "Presentation Replay" : "Full Replay"}</strong></p>}
            <p>Raw frozen workload records: {workspace.rawRecords ?? "N/A"}</p>
            <p>Staged alerts: {workspace.stagedAlerts ?? "N/A"}</p>
            <p>Last prepared: {workspace.lastPreparedAt ?? "Never"}</p>
            {workspace.preparationMode === "presentation" && <div className="space-y-1 rounded-sm border border-border bg-raised p-3">
              <p>Learning history: <strong className="text-text">{workspace.learningProcessed} processed</strong></p>
              <p>Holdout arrived: <strong className="text-text">{workspace.holdoutArrived} / 160</strong></p>
              <p>Remaining: <strong className="text-text">{workspace.holdoutRemaining}</strong></p>
              <p>Playback: <strong className="text-text">{workspace.playbackState === "running" ? "Running" : workspace.playbackState === "complete" ? "Complete" : "Paused"}</strong></p>
              <p>Last arrival: {workspace.lastArrivalAt ?? "Not yet"}</p>
            </div>}
            <p className="text-xs">Recorded presentation replay, not live network traffic. Official frozen evaluation results are separate.</p>
          </>}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" disabled={busy !== null || workspace.active || !workspace.ready}
            onClick={() => void act("activate", workspace.id)}
            className="rounded-sm border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">Activate</button>
          {workspace.id === "v3-1-replay" && <>
            <button type="button" disabled={busy !== null || workspace.ready || workspace.active}
              onClick={() => void act("prepare")}
              className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">Prepare Replay</button>
            <button type="button" disabled={busy !== null || !workspace.ready || workspace.active}
              onClick={() => void act("reset")}
              className="rounded-sm border border-danger/50 px-3 py-1.5 text-sm text-danger disabled:opacity-40">Reset Replay</button>
            {workspace.preparationMode === "presentation" && <>
              <button type="button" disabled={busy !== null || !workspace.active || workspace.playbackState !== "paused" || !workspace.holdoutRemaining}
                onClick={() => void act("start")}
                className="rounded-sm border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">Start Arrivals</button>
              <button type="button" disabled={busy !== null || workspace.playbackState !== "running"}
                onClick={() => void act("pause")}
                className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">Pause</button>
              {[1, 5, 150].map(count => <button key={count} type="button"
                disabled={busy !== null || !workspace.active || !workspace.holdoutRemaining}
                onClick={() => void act("advance", "v3-1-replay", count as 1 | 5 | 150)}
                className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">
                {count === 1 ? "Next Alert" : count === 5 ? "Next 5" : "Load Remaining"}</button>)}
            </>}
          </>}
        </div>
      </Card>)}</div>
      <Card title="Recent workspace actions" subtitle="Administrator action history is stored outside both operational databases.">
        {data.actions.length ? <div className="space-y-2 text-xs text-muted">{data.actions.map((entry, index) =>
          <p key={`${entry.created_at}-${index}`} className="border-b border-border pb-2">
            <span className="font-mono text-text">{entry.created_at}</span> · {entry.actor} · {entry.action} · {entry.workspace} · {entry.reason}
          </p>)}</div> : <p className="text-sm text-muted">No workspace actions recorded.</p>}
      </Card>
    </>}</ApiView>
  </div>;
}
