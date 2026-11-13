import { useEffect, useRef, useState } from "react";

import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";
import { Card, PageHeader, Pill } from "../../components/ui";

export function WorkspacesPage() {
  const state = useApi(signal => unwrap(api.GET("/api/admin/workspaces", { signal })), [],
    { keepPreviousData: true });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // X7 (S8-09): no pre-filled "Prepare ..." sentence; an empty reason records the action that was taken.
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"full" | "presentation" | "packet">("full");
  const reload = useRef(state.reload); reload.current = state.reload;
  useEffect(() => { const timer = setInterval(() => reload.current(), 5000); return () => clearInterval(timer); }, []);

  async function act(action: "prepare" | "reset" | "activate" | "start" | "pause" | "advance" | "flowChain",
                     id = "v3-1-replay", count: 1 | 5 | 150 = 1, enabled = true) {
    if (action === "reset" && !window.confirm(
      "Reset V3.1 Demo Replay to 0 alerts? Analysts are moved to the Operational workspace, and their open claims, verdicts, memory and cases in Replay are removed. The Operational workspace and official frozen evaluation remain unchanged.")) return;
    setBusy(`${action}:${id}`); setError(null);
    try {
      const defaults = { prepare: "Prepare isolated V3.1 analyst demonstration", reset: "Reset V3.1 Demo Replay",
        activate: `Activate workspace ${id}`, start: "Start replay playback", pause: "Pause replay playback",
        advance: `Advance replay by ${count}`, flowChain: "Set the CICFlowMeter flow chain" } as const;
      const body = { reason: reason.trim() || defaults[action] };
      if (action === "prepare") await unwrap(api.POST("/api/admin/workspaces/v3-1-replay/prepare", { body: { ...body, mode } }));
      else if (action === "flowChain") await unwrap(api.POST("/api/admin/detection/flow-chain", { body: { ...body, enabled } }));
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
      {data.workspaces[1]?.ready && !data.workspaces[1]?.active && <p role="status"
        className="rounded-sm border border-warn/50 bg-raised p-3 text-sm text-text">
        Replay is prepared but not active — Analysts currently see the Operational workspace.
        Click <strong>Activate</strong> on the Replay card to show it.
      </p>}
      <Card title="Detection chains" subtitle="Program settings. They apply to every workspace and to both data sources.">
        <div className="flex flex-wrap items-center gap-3 text-sm text-text">
          <button type="button" role="switch" aria-checked={data.detection.flowChainEnabled}
            aria-label="CICFlowMeter flow chain" disabled={busy !== null}
            onClick={() => void act("flowChain", "program", 1, !data.detection.flowChainEnabled)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:opacity-40 ${
              data.detection.flowChainEnabled ? "border-accent bg-accent" : "border-border bg-raised"}`}>
            <span aria-hidden="true" className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
              data.detection.flowChainEnabled ? "translate-x-6" : "translate-x-1"}`} />
          </button>
          <span>CICFlowMeter flow chain</span>
          <span className="text-xs text-muted">{data.detection.flowChainEnabled
            ? "on — flow records are grouped, queued and routed"
            : "off — flow records still arrive, but the program does not process them"}</span>
          <span className="text-xs font-semibold uppercase tracking-wide text-dim">{data.detection.flowChainEnabled ? "On" : "Off"}</span>
        </div>
      </Card>
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
                <option value="packet">Packet Replay · Suricata + flow chains, progressive arrivals</option>
              </select>
            </label>}
            {workspace.ready && <p>Mode: <strong className="text-text">{workspace.preparationMode === "presentation" ? "Presentation Replay" : workspace.preparationMode === "packet" ? "Packet Replay" : "Full Replay"}</strong></p>}
            {workspace.preparationMode === "packet"
              ? <p>Flows in the capture window: {workspace.rawRecords ?? "N/A"}</p>
              : <p>Raw frozen workload records: {workspace.rawRecords ?? "N/A"}</p>}
            {workspace.preparationMode === "packet"
              ? <p>Suricata alerts admitted: {workspace.stagedAlerts ?? "N/A"}</p>
              : <p>Staged alerts: {workspace.stagedAlerts ?? "N/A"}</p>}
            <p>Last prepared: {workspace.lastPreparedAt ?? "Never"}</p>
            {(workspace.preparationMode === "presentation" || workspace.preparationMode === "packet") && <div className="space-y-1 rounded-sm border border-border bg-raised p-3">
              {workspace.preparationMode === "presentation" && <p>Learning history: <strong className="text-text">{workspace.learningProcessed} processed</strong></p>}
              {workspace.preparationMode === "packet"
                ? <p>Capture steps arrived: <strong className="text-text">{workspace.holdoutArrived} / 160</strong></p>
                : <p>Holdout arrived: <strong className="text-text">{workspace.holdoutArrived} / 160</strong></p>}
              <p>Remaining: <strong className="text-text">{workspace.holdoutRemaining}</strong></p>
              <p>Playback: <strong className="text-text">{workspace.playbackState === "running" ? "Running" : workspace.playbackState === "complete" ? "Complete" : "Paused"}</strong></p>
              <p>Last arrival: {workspace.lastArrivalAt ?? "Not yet"}</p>
            </div>}
            <p className="text-xs">{workspace.preparationMode === "packet" ? "Recorded packet capture (CSE-CIC-IDS2018, 2018-02-14) replayed in capture order. Not live network traffic." : "Recorded presentation replay, not live network traffic. Official frozen evaluation results are separate."}</p>
          </>}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" disabled={busy !== null || workspace.active || !workspace.ready}
            onClick={() => void act("activate", workspace.id)}
            className="rounded-sm border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">Activate</button>
          {workspace.id === "v3-1-replay" && <>
            <button type="button" disabled={busy !== null || workspace.preparedFile || workspace.active}
              title={workspace.preparedFile ? "Reset Replay before preparing it again." : undefined}
              onClick={() => void act("prepare")}
              className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">Prepare Replay</button>
            <button type="button" disabled={busy !== null || !workspace.preparedFile}
              title={workspace.active ? "Moves Analysts to Operational, then resets Replay to 0 alerts." : undefined}
              onClick={() => void act("reset")}
              className="rounded-sm border border-danger/50 px-3 py-1.5 text-sm text-danger disabled:opacity-40">{busy === "reset:v3-1-replay" ? "Resetting…" : "Reset Replay"}</button>
            {(workspace.preparationMode === "presentation" || workspace.preparationMode === "packet") && <>
              <button type="button" disabled={busy !== null || !workspace.active || workspace.playbackState !== "paused" || !workspace.holdoutRemaining}
                onClick={() => void act("start")}
                className="rounded-sm border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">Start Arrivals</button>
              <button type="button" disabled={busy !== null || workspace.playbackState !== "running"}
                onClick={() => void act("pause")}
                className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">Pause</button>
              {(workspace.preparationMode === "packet" ? [1, 5] : [1, 5, 150]).map(count => <button key={count} type="button"
                disabled={busy !== null || !workspace.active || !workspace.holdoutRemaining}
                onClick={() => void act("advance", "v3-1-replay", count as 1 | 5 | 150)}
                className="rounded-sm border border-border px-3 py-1.5 text-sm text-text disabled:opacity-40">
                {workspace.preparationMode === "packet"
                  ? count === 1 ? "Next Step" : "Next 5 Steps"
                  : count === 1 ? "Next Alert" : count === 5 ? "Next 5" : "Load Remaining"}</button>)}
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
