import { Link } from "react-router";
import type { Schemas } from "../../api/client";
import type { paths } from "../../api/schema";

import { needsReview } from "./EffectiveReview";

type Summary = Schemas["OperationalSummary"];
type Query = NonNullable<paths["/api/v2/alerts"]["get"]["parameters"]["query"]>;
export const queueViews = [
  { key: "all", label: "All", count: "totalAlerts", query: {} },
  { key: "tier2", label: "Tier 2", count: "tier2Cases", query: { handlingRoute: "tier2_case" } },
  { key: "tier1", label: "Tier 1", count: "tier1Review", query: { handlingRoute: "tier1_review" } },
  { key: "expert", label: "Expert Review", count: "expertReview", query: { routeClass: "EXPERT_REVIEW_REQUIRED" } },
  { key: "critical", label: "Critical", count: "criticalAlerts", query: { priorityBand: "P1" } },
  { key: "needs-review", label: "Needs Review", count: "reviewRequired", query: { reviewRequired: true } },
  { key: "no-review", label: "No Immediate Review", count: "noImmediateReview", query: { reviewDisposition: "no_immediate_review" } },
] as const satisfies readonly { key: string; label: string; count: keyof Summary; query: Query }[];
export type QueueView = typeof queueViews[number]["key"];
export const attackCategories = [
  ["brute_force", "Brute Force"], ["botnet_c2", "Botnet / C2"], ["dos", "DoS"], ["ddos", "DDoS"],
  ["web_attack", "Web Attack"], ["infiltration", "Infiltration"], ["reconnaissance_port_scan", "Reconnaissance / Port Scan"],
  ["malware_exploit", "Malware / Exploit"], ["other_known_attack", "Other Known Attack"], ["unknown_needs_expert", "Unknown / Needs Expert"],
] as const;
export const categoryLabel = (value: string) => attackCategories.find(([key]) => key === value)?.[1] ?? "Not classified";
const number = (value: number | undefined) => value === undefined ? "—" : value.toLocaleString();
const metrics = [
  ["critical", "Critical", "criticalAlerts", "Current priority band P1 / critical"],
  ["tier2", "Tier 2", "tier2Cases", "Current route is Tier 2 Case"],
  ["expert", "Expert Review", "expertReview", "Persisted Expert Review Required class or Unknown / Needs Expert classification"],
  ["needs-review", "Needs Review", "reviewRequired", "Effective attention requires human review, including audit samples"],
  ["no-review", "No Immediate Review", "noImmediateReview", "Effective attention is No Immediate Review; not a human verdict"],
  ["cases", "Open Tier 2 Cases", "openTier2Cases", "Cases with status open or investigating"],
  ["tier1", "Tier 1", "tier1Review", "Current route is Tier 1 Review"],
  ["all", "Total Alerts", "totalAlerts", "All persisted operational V2 alerts"],
] as const;

export function OperationalKpis({ data, onView }: { data?: Summary; onView: (view: QueueView) => void }) {
  return <section aria-label="Operational workload" className="shrink-0 border-b border-border bg-surface">
    <div className="ops-kpis">
      {metrics.map(([view, label, key, definition]) => {
        const content = <><span className="block text-[10px] font-semibold uppercase tracking-wide text-muted">{label}</span>
          <span className={`mt-1 block font-mono text-2xl font-semibold tabular-nums ${key === "criticalAlerts" ? "text-danger" : "text-text"}`}>{number(data?.[key])}</span></>;
        const className = "min-w-0 rounded-sm px-3 py-2 text-left hover:bg-raised focus-visible:outline-2 focus-visible:outline-primary";
        const accessible = `${label} ${number(data?.[key])}`;
        return view === "cases" ? <Link key={key} to="/analyst/tier2-cases" aria-label={accessible} title={definition} className={className}>{content}</Link>
          : <button key={key} aria-label={accessible} title={definition} onClick={() => onView(view)} className={className}>{content}</button>;
      })}
    </div>
    <p className="px-3 pb-1 text-[10px] text-dim">Entire operational dataset · categories overlap · queue filters do not change these counts</p>
  </section>;
}

export function QueueTabs({ active, data, onView }: { active: QueueView; data?: Summary; onView: (view: QueueView) => void }) {
  return <div role="tablist" aria-label="Operational queue views" className="ops-queue-tabs flex flex-wrap gap-1" onKeyDown={event => {
    const position = queueViews.findIndex(view => view.key === active);
    const index = event.key === "ArrowRight" ? (position + 1) % queueViews.length : event.key === "ArrowLeft" ? (position + queueViews.length - 1) % queueViews.length
      : event.key === "Home" ? 0 : event.key === "End" ? queueViews.length - 1 : -1;
    const next = queueViews[index];
    if (next) { event.preventDefault(); onView(next.key); document.getElementById("queue-view-" + next.key)?.focus(); }
  }}>
    {queueViews.map(view => <button key={view.key} id={"queue-view-" + view.key} role="tab" aria-selected={active === view.key}
      tabIndex={active === view.key ? 0 : -1} aria-controls="operational-queue-panel" onClick={() => onView(view.key)}
      className={`whitespace-nowrap rounded-sm border px-2 py-1 text-[10px] ${active === view.key ? "border-primary bg-raised text-text" : "border-border text-muted hover:text-text"}`}>
      {view.label} <span className="ml-1 font-mono tabular-nums">{number(data?.[view.count])}</span>
    </button>)}
  </div>;
}

export function QueueItem({ item }: { item: Schemas["RoutingView"] }) {
  const state = item.state;
  const band = state.priorityBand;
  const bandLabel = band === "P1" || band === "critical" ? "Critical" : band === "P2" ? "High" : band === "P3" ? "Medium" : band === "P4" ? "Low" : band ?? "Unassigned";
  const route = state.handlingRoute;
  const expert = item.systemRouting?.routeClass === "EXPERT_REVIEW_REQUIRED" || item.classification?.attackCategory === "unknown_needs_expert";
  const routeLabel = route === "tier2_case" ? "Tier 2" : route === "tier1_review" ? "Tier 1" : route === "no_immediate_review" ? "No Immediate Review" : route === "tier2_candidate" ? "Recovery pending" : "Unassigned";
  const detail = item.detectionSummary;
  return <>
    <span className="flex items-start justify-between gap-2">
      <span className="min-w-0 space-y-1 pt-1"><span className={`block text-[10px] font-semibold uppercase tracking-wide ${bandLabel === "Critical" ? "text-danger" : "text-muted"}`}>{bandLabel} · {routeLabel}</span>
        {expert ? <span className="block text-[10px] font-semibold text-accent">EXPERT</span> : item.systemRouting && <span className="block text-[10px] text-muted">{item.systemRouting.routeClass === "CRITICAL_ESCALATION" ? "Critical Escalation" : state.decisionSource === "analyst" && route === "tier2_case" ? "Manual Override" : "Routine Review"}</span>}</span>
      <span title="Operational Priority — urgency for SOC action; not detector confidence or severity" aria-label={`Operational Priority: ${state.operationalPriority ?? "Unassigned"}`} className="shrink-0 text-right">
        <span className="block font-mono text-3xl font-semibold leading-none tabular-nums">{state.operationalPriority ?? "—"}</span>
        <span className="mt-1 block text-[9px] text-muted">Operational Priority</span>
      </span>
    </span>
    <span className="block break-words font-semibold">{item.title}</span>
    {!needsReview(item) && <span className="block text-ok">No Immediate Review</span>}
    <span className="block text-muted">{item.classification?.status === "informational_policy_signal" ? "Informational / Policy Signal" : categoryLabel(item.classification?.attackCategory ?? "")}</span>
    {detail && <span className="block break-all font-mono text-[10px]">{detail.sourceIp} → {detail.destinationIp}{detail.destinationPort != null ? ":" + detail.destinationPort : ""}</span>}
    <span className="block text-[10px] text-muted">{item.detectorSource === "current_flow" ? "Legacy Flow Detector" : item.detectorName}
      {detail?.relatedSignatureCount != null && ` · ${detail.relatedSignatureCount} signature${detail.relatedSignatureCount === 1 ? "" : "s"}`}
      {!!detail?.evidenceTypes.length && ` · ${detail.evidenceTypes.filter(type => type !== "alert").map(type => type.toUpperCase()).join(" + ") || "Alert"}`}</span>
    <span className="sr-only">Review Required: {needsReview(item) ? "Yes" : "No"}</span>
  </>;
}
