import { Link } from "react-router";
import type { Schemas } from "../../api/client";
import type { paths } from "../../api/schema";

import { needsReview } from "./EffectiveReview";
import {workLabel} from './AnalystWork';

type Summary = Schemas["OperationalSummary"];
type Query = NonNullable<paths["/api/v2/alerts"]["get"]["parameters"]["query"]>;
export const queueViews = [
  { key: "all", pill: true, label: "All", group: "Scope", count: "totalAlerts", query: {} },
  { key: "critical", pill: true, label: "Critical", group: "Severity", count: "criticalAlerts", query: { priorityBand: "P1" } },
  { key: "high", pill: true, label: "High", group: "Severity", count: "highAlerts", query: { priorityBand: "P2" } },
  { key: "medium", pill: true, label: "Medium", group: "Severity", count: "mediumAlerts", query: { priorityBand: "P3" } },
  { key: "low", pill: true, label: "Low", group: "Severity", count: "lowAlerts", query: { priorityBand: "P4" } },
  { key: "tier2", pill: true, label: "Tier 2", group: "Triage", count: "tier2Cases", query: { handlingRoute: "tier2_case" } },
  // C2 (approved 2026-11-08): the server applies the C3 rule, so this view and the "Why Tier 2" panel agree.
  { key: "tier2-candidates", pill: true, label: "Candidates", group: "Triage", count: "tier2Candidates", query: { tier2Candidate: true, workScope: "active" } },
  { key: "grouped", pill: true, label: "Grouped", group: "Triage", count: "tier1Groups", query: { grouped: true, workScope: "active" } },
  { key: "completed", pill: true, label: "Completed", group: "Work", count: "completedWork", query: { workScope: "completed" } },
  // Reachable from the KPI cards and old links, not from the pill strip.
  { key: "active", label: "Active", group: "Other", pill: false, count: "activeAlerts", query: { workScope: "active" } },
  { key: "auto-escalated", label: "Auto-escalated", group: "Other", pill: false, count: "autoEscalated", query: { handlingRoute: "tier2_case", decisionSource: "system_policy" } },
  { key: "tier1", label: "Tier 1", group: "Other", pill: false, count: "tier1Review", query: { handlingRoute: "tier1_review", workScope: "active" } },
  { key: "expert", label: "Expert Review", group: "Other", pill: false, count: "expertReview", query: { routeClass: "EXPERT_REVIEW_REQUIRED" } },
  { key: "needs-review", label: "Needs Review", group: "Other", pill: false, count: "reviewRequired", query: { reviewRequired: true } },
  { key: "no-review", label: "No Immediate Review", group: "Other", pill: false, count: "noImmediateReview", query: { reviewDisposition: "no_immediate_review" } },
] as const satisfies readonly { key: string; label: string; group: string; pill?: boolean; count: keyof Summary; query: Query }[];
export const primaryViews = queueViews.filter(view => view.pill !== false);
export const overflowViews = [] as const;
export type QueueView = typeof queueViews[number]["key"];
export const attackCategories = [
  ["brute_force", "Brute Force"], ["botnet_c2", "Botnet / C2"], ["dos", "DoS"], ["ddos", "DDoS"],
  ["web_attack", "Web Attack"], ["infiltration", "Infiltration"], ["reconnaissance_port_scan", "Reconnaissance / Port Scan"],
  ["malware_exploit", "Malware / Exploit"], ["other_known_attack", "Other Known Attack"], ["unknown_needs_expert", "Unknown / Needs Expert"],
] as const;
export const categoryLabel = (value: string) => attackCategories.find(([key]) => key === value)?.[1] ?? "Not classified";
const number = (value: number | undefined) => value === undefined ? "—" : value.toLocaleString();
// D4 condition 3: the Tier 1 count shows groups and singles apart. Falls back to the total if the split is absent.
const tier1Split = (data?: Summary) => data?.tier1Groups === undefined || data?.tier1Singles === undefined ? null
  : `${number(data.tier1Groups)} flow groups · ${number(data.tier1Singles)} single`;
const shown = (data: Summary | undefined, key: keyof Summary) => key === "tier1Review" ? tier1Split(data) ?? number(data?.[key]) : number(data?.[key]);
const metrics = [
  ["active", "Active Alerts", "activeAlerts", "Alerts without completed or escalated Tier 1 work; attention and Tier 2 remain separate"],
  ["critical", "Critical", "criticalAlerts", "Current priority band P1 / critical"],
  ["tier2", "Tier 2", "tier2Cases", "Current route is Tier 2 Case"],
  ["expert", "Expert Review", "expertReview", "Persisted Expert Review Required class or Unknown / Needs Expert classification"],
  ["needs-review", "Needs Review", "reviewRequired", "Effective attention requires human review, including audit samples"],
  ["no-review", "No Immediate Review", "noImmediateReview", "Effective attention is No Immediate Review; not a human verdict"],
  ["cases", "Open Tier 2 Cases", "openTier2Cases", "Cases with status open or investigating"],
  ["tier1", "Active Tier 1", "tier1Review", "Tier 1 route with unfinished human work"],
  ["all", "Total Alerts", "totalAlerts", "All persisted operational alerts"],
] as const;

export function OperationalKpis({ data, onView, active }: { data?: Summary; onView: (view: QueueView) => void; active?: QueueView }) {
  return <section aria-label="Operational workload" className="shrink-0 border-b border-border bg-surface">
    <div className="ops-kpis">
      {metrics.map(([view, label, key, definition]) => {
        const content = <><span className="block text-[10px] font-semibold uppercase tracking-wide text-muted">{label}</span>
          <span className={`mt-1 block font-mono ${key === "tier1Review" && tier1Split(data) ? "text-sm" : "text-2xl"} font-semibold tabular-nums ${key === "criticalAlerts" ? "text-danger" : "text-text"}`}>{shown(data, key)}</span></>;
        const pressed = active === view;
        const className = `min-w-0 rounded-sm px-3 py-2 text-left hover:bg-raised focus-visible:outline-2 focus-visible:outline-primary ${pressed ? "bg-raised outline outline-1 outline-primary" : ""}`;
        const accessible = `${label} ${shown(data, key)}`;
        return view === "cases" ? <Link key={key} to="/analyst/tier2-cases" aria-label={accessible} title={definition} className={className}>{content}</Link>
          : <button key={key} aria-label={accessible} aria-pressed={pressed} title={definition} onClick={() => onView(view)} className={className}>{content}</button>;
      })}
    </div>
    <p className="px-3 pb-1 text-[10px] text-dim">Active Alerts / Active Tier 1 exclude completed and escalated work. Other counts cover the entire operational dataset; attention is not work completion.</p>
  </section>;
}

export function QueueTabs({ active, data, onView }: { active: QueueView; data?: Summary; onView: (view: QueueView) => void }) {
  // Same tab look as before, fewer tabs: scope, severity bands, candidates, grouped, completed.
  const count = (view: { count: keyof Summary; key: string }) => view.key === "tier1" ? number(data?.tier1Review) : shown(data, view.count);
  const pills = queueViews.filter(view => view.pill !== false);
  const activeIndex = pills.findIndex(view => view.key === active);
  const open = (view: { key: string }) => onView(view.key as QueueView);
  return <div role="tablist" aria-label="Operational queue views" className="flex flex-wrap gap-1" onKeyDown={event => {
    const from = activeIndex < 0 ? 0 : activeIndex;
    const index = event.key === "ArrowRight" || event.key === "ArrowDown" ? (from + 1) % pills.length
      : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (from + pills.length - 1) % pills.length
      : event.key === "Home" ? 0 : event.key === "End" ? pills.length - 1 : -1;
    const next = pills[index];
    if (next) { event.preventDefault(); open(next); document.getElementById("queue-view-" + next.key)?.focus(); }
  }}>
    {pills.map(view => <button key={view.key} id={"queue-view-" + view.key} role="tab" aria-selected={active === view.key}
      aria-label={`${view.label} ${count(view)}`} tabIndex={active === view.key || (activeIndex < 0 && view.key === "all") ? 0 : -1}
      aria-controls="operational-queue-panel" onClick={() => open(view)}
      title={view.key === "tier2-candidates" ? "Tier 2 candidates: recommended, not yet escalated" : view.label}
      className={`whitespace-nowrap rounded-sm border px-2 py-1 text-[10px] ${active === view.key ? "border-primary bg-raised text-text" : "border-border text-muted hover:text-text"}`}>
      {view.label} <span className="ml-1 font-mono tabular-nums">{count(view)}</span>
    </button>)}
  </div>;
}

export function QueueItem({ item }: { item: Schemas["RoutingView"] }) {
  const state = item.state;
  const band = state.priorityBand;
  const bandLabel = band === "P1" || band === "critical" ? "Critical" : band === "P2" ? "High" : band === "P3" ? "Medium" : band === "P4" ? "Low" : band ?? "Unassigned";
  const route = state.handlingRoute;
  const expert = item.systemRouting?.routeClass === "EXPERT_REVIEW_REQUIRED" || item.classification?.attackCategory === "unknown_needs_expert";
  const routeLabel = route === "tier2_case" ? "Tier 2" : route === "tier1_review" ? "Tier 1" : route === "no_immediate_review" ? "No Immediate Review" : route === "tier2_candidate" ? "Historical routing record" : "Unassigned";
  const detail = item.detectionSummary;
  return <>
    <span className="flex items-start justify-between gap-2">
      <span className="min-w-0 space-y-1 pt-1"><span className={`block text-[10px] font-semibold uppercase tracking-wide ${bandLabel === "Critical" ? "text-danger" : "text-muted"}`}>{bandLabel} · {routeLabel}</span>
        {expert ? <span className="block text-[10px] font-semibold text-accent">EXPERT</span> : item.systemRouting && <span className="block text-[10px] text-muted">{state.decisionSource === "analyst" && route === "tier2_case" ? "Manual Override" : route === "tier2_case" && state.decisionSource === "system_policy" ? "Auto-escalated" : item.systemRouting.routeClass === "CRITICAL_ESCALATION" ? "Critical Escalation" : "Routine Review"}</span>}</span>
      <span title="Operational Priority — urgency for SOC action; not detector confidence or severity" aria-label={`Operational Priority: ${state.operationalPriority ?? "Unassigned"}`} className="shrink-0 text-right">
        <span className="block font-mono text-3xl font-semibold leading-none tabular-nums">{state.operationalPriority ?? "—"}</span>
        <span className="mt-1 block text-[9px] text-muted">Operational Priority</span>
      </span>
    </span>
    <span className="block break-words font-semibold">{item.title}</span>
    {item.tier2RecommendationOpen && <span className="block rounded-sm border border-accent/40 bg-accent/10 px-1.5 py-1 text-[10px]">
      <span className="block font-semibold tracking-wide text-accent">TIER 2 RECOMMENDED</span>
      {state.tier2RecommendationReasons[0] && <span className="block break-words text-muted">{state.tier2RecommendationReasons[0]}</span>}
    </span>}
    {item.work?.status&&<span className="block break-words font-semibold text-accent">{workLabel(item.work)}{item.work.status==='completed'&&item.work.verdictOutcome?` · ${item.work.verdictOutcome.replaceAll('_',' ')}`:''}</span>}
    {!needsReview(item) && <span className="block text-ok">No Immediate Review</span>}
    <span className="block text-muted">{item.classification?.status === "informational_policy_signal" ? "Informational / Policy Signal" : categoryLabel(item.classification?.attackCategory ?? "")}</span>
    {detail && <span className="block break-all font-mono text-[10px]">{detail.sourceIp} → {detail.destinationIp}{detail.destinationPort != null ? ":" + detail.destinationPort : ""}</span>}
    <span className="block text-[10px] text-muted">{item.detectorSource === "current_flow" ? "Legacy Flow Detector" : item.detectorName}
      {item.groupMemberCount != null && ` · Group of ${item.groupMemberCount}`}
      {detail?.relatedSignatureCount != null && ` · ${detail.relatedSignatureCount} signature${detail.relatedSignatureCount === 1 ? "" : "s"}`}
      {!!detail?.evidenceTypes.length && ` · ${detail.evidenceTypes.filter(type => type !== "alert").map(type => type.toUpperCase()).join(" + ") || "Alert"}`}</span>
    <span className="sr-only">Review Required: {needsReview(item) ? "Yes" : "No"}</span>
  </>;
}
