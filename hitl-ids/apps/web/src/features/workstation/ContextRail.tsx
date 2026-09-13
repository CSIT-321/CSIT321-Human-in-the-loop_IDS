/**
 * The workstation's right column: context for the selected alert, from real data only.
 *
 * - A flow diagram instead of a network topology: the 5-tuple is all the recording holds.
 * - What the recorded flows say about each address (B5) instead of threat-intel feeds.
 * - The alert's family instead of guessed "related alerts".
 * - Quick actions that exist: pivot to an address, copy the indicator, open the full page. No
 *   blocklist, isolate or ticket buttons — there is nothing to respond to in a recording.
 */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { LoadingState } from "../../components/states";
import { formatNumber } from "../../design/format";
import { FEEDBACK_CATEGORIES } from "../feedback/categories";
import { shortFlowTime } from "./QueuePane";

type Detail = Schemas["AlertDetail"];

/** '["Brute Force",21,"tcp","SIG-FTP-BRUTE-FORCE"]' -> "Brute Force · port 21 · tcp · SIG-FTP-BRUTE-FORCE". */
function readableFamilyKey(key: string): string {
  try {
    const parts: unknown = JSON.parse(key);
    if (!Array.isArray(parts)) return key;
    return parts
      .map((part, index) => (index === 1 && typeof part === "number" ? `port ${part}` : String(part)))
      .filter((part) => part !== "-")
      .join(" · ");
  } catch {
    return key;
  }
}

/** The family in a glance: what it is, how big, and whether its learning gate has opened. */
function FamilySummary({ family }: { family: Detail["family"] }) {
  const dominant = FEEDBACK_CATEGORIES.find((category) => category.value === family.dominantCategory);
  const applied = (family.appliedAdjustment ?? 0) !== 0 || (family.appliedOffset ?? 0) !== 0;
  return (
    <div className="space-y-2">
      <p className="text-[13px] font-medium text-text">{readableFamilyKey(family.familyKey ?? "")}</p>
      <dl className="grid grid-cols-2 gap-1 font-mono text-[11px]">
        <div className="rounded-sm bg-bg px-1.5 py-1">
          <dt className="text-[9px] uppercase text-dim">Members</dt>
          <dd className="tabular-nums text-text">{formatNumber(family.members ?? 0)}</dd>
        </div>
        <div className="rounded-sm bg-bg px-1.5 py-1">
          <dt className="text-[9px] uppercase text-dim">Learning gate</dt>
          <dd className={family.gateOpen ? "text-ok" : "text-muted"}>{family.gateOpen ? "Open" : "Closed"}</dd>
        </div>
      </dl>
      {dominant !== undefined && (
        <p className="font-mono text-[11px] text-muted">
          Verdict in force across the family: <span className="text-text">{dominant.label}</span>
          {family.agreementRatio !== null && family.agreementRatio !== undefined &&
            ` · ${Math.round(family.agreementRatio * 100)}% agree`}
        </p>
      )}
      {family.gateReason !== null && family.gateReason !== undefined && (
        <p className="text-[12px] text-dim">{family.gateReason}</p>
      )}
      {applied && family.note !== null && family.note !== undefined && (
        <p className="text-[12px] text-warn">{family.note}</p>
      )}
    </div>
  );
}

function RailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-4 py-3">
      <h3 className="label-mono mb-2.5">{title}</h3>
      {children}
    </section>
  );
}

function FlowDiagram({ flow }: { flow: Detail["flow"] }) {
  return (
    <div className="flex items-stretch gap-2 font-mono text-[11px]">
      <div className="min-w-0 flex-1 rounded-sm border border-border bg-bg px-2 py-1.5">
        <p className="text-[9px] uppercase tracking-wider text-dim">Source</p>
        <p className="truncate text-accent">{flow.srcIp}</p>
        <p className="text-muted">:{flow.srcPort}</p>
      </div>
      <div className="flex shrink-0 flex-col items-center justify-center text-dim">
        <span className="text-[9px] uppercase tracking-wider">{flow.protocol}</span>
        <span aria-hidden className="text-base leading-none text-muted">
          →
        </span>
        <span className="text-[9px] tabular-nums">{formatNumber(flow.packets)} pkts</span>
      </div>
      <div className="min-w-0 flex-1 rounded-sm border border-border bg-bg px-2 py-1.5">
        <p className="text-[9px] uppercase tracking-wider text-dim">Destination</p>
        <p className="truncate text-accent">{flow.dstIp}</p>
        <p className="text-severity-medium">:{flow.dstPort}</p>
      </div>
    </div>
  );
}

function IpContext({ ip, label }: { ip: string; label: string }) {
  const entity = useApi(
    (signal) => unwrap(api.GET("/api/entities/ip/{ip}", { params: { path: { ip }, query: { limit: 3 } }, signal })),
    [ip],
  );
  return (
    <div className="space-y-1.5">
      <p className="flex items-baseline justify-between gap-2">
        <span className="truncate font-mono text-xs text-accent">{ip}</span>
        <span className="font-mono text-[10px] uppercase text-dim">{label}</span>
      </p>
      {entity.status === "loading" && <p className="font-mono text-[11px] text-dim">loading…</p>}
      {entity.status === "error" && <p className="text-[11px] text-danger">{entity.error.message}</p>}
      {entity.status === "success" && (
        <>
          <dl className="grid grid-cols-2 gap-1 font-mono text-[11px]">
            <div className="rounded-sm bg-bg px-1.5 py-1">
              <dt className="text-[9px] uppercase text-dim">Alerts</dt>
              <dd className="tabular-nums text-text">{formatNumber(entity.data.alerts)}</dd>
            </div>
            <div className="rounded-sm bg-bg px-1.5 py-1">
              <dt className="text-[9px] uppercase text-dim">Flagged</dt>
              <dd className="tabular-nums text-warn">{formatNumber(entity.data.flagged)}</dd>
            </div>
          </dl>
          <p className="font-mono text-[10px] text-dim">
            seen {shortFlowTime(entity.data.firstSeen)} → {shortFlowTime(entity.data.lastSeen)}
          </p>
          {(entity.data.topPeers ?? []).length > 0 && (
            <ul aria-label={`Top peers of ${ip}`} className="space-y-0.5 font-mono text-[11px]">
              {(entity.data.topPeers ?? []).map((peer) => (
                <li key={peer.value} className="flex justify-between gap-2 text-muted">
                  <span className="truncate">{peer.value}</span>
                  <span className="tabular-nums text-dim">
                    {formatNumber(peer.count)} flows
                    {peer.flagged > 0 && <span className="text-warn"> · {formatNumber(peer.flagged)} flagged</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link
            to={`/analyst/workstation?search=${encodeURIComponent(ip)}`}
            className="inline-block font-mono text-[11px] text-accent hover:text-text"
          >
            All alerts for this address →
          </Link>
        </>
      )}
    </div>
  );
}

export function ContextRail({ detail, detailError }: { detail: Detail | null; detailError: boolean }) {
  const [copied, setCopied] = useState(false);

  if (detail === null) {
    return (
      <aside aria-label="Alert context" className="hidden min-h-0 border-l border-border bg-surface p-4 xl:block">
        {detailError ? (
          <p className="text-sm text-muted">No context: the alert did not load.</p>
        ) : (
          <LoadingState label="Loading context…" />
        )}
      </aside>
    );
  }

  const flow = detail.flow;
  const indicator = `${flow.srcIp}:${flow.srcPort} -> ${flow.dstIp}:${flow.dstPort}/${flow.protocol}`;
  const hasFamily = detail.family.familyKey !== null && detail.family.familyKey !== undefined;

  return (
    <aside aria-label="Alert context" className="hidden min-h-0 overflow-y-auto border-l border-border bg-surface xl:block">
      <RailSection title="Flow">
        <FlowDiagram flow={flow} />
      </RailSection>
      <RailSection title="Addresses in the recording">
        <div className="space-y-4">
          <IpContext ip={flow.srcIp} label="source" />
          <IpContext ip={flow.dstIp} label="destination" />
        </div>
      </RailSection>
      <RailSection title="Family">
        {hasFamily ? (
          <FamilySummary family={detail.family} />
        ) : (
          <p className="text-[13px] text-muted">This alert belongs to no family.</p>
        )}
      </RailSection>
      <RailSection title="Quick actions">
        <div className="grid gap-1.5">
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard?.writeText(indicator).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              });
            }}
            className="rounded-sm border border-border bg-raised px-2.5 py-1.5 text-left font-mono text-[11px] text-text hover:border-border-strong"
          >
            {copied ? "Copied" : "Copy flow indicator"}
          </button>
          <Link
            to={`/analyst/alerts/${detail.alert.alertRef}`}
            className="rounded-sm border border-border bg-raised px-2.5 py-1.5 font-mono text-[11px] text-text hover:border-border-strong"
          >
            Open full alert page
          </Link>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-dim">
          No blocklist, isolate or ticket actions: these are recorded flows, not a live network.
        </p>
      </RailSection>
    </aside>
  );
}
