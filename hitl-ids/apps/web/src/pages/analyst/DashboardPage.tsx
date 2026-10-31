import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";

// Follow pagination; never present a single page as a global count. Preserve server order.
async function allPages<T>(get: (offset: number) => Promise<{items: T[]; page: {total: number}}>) {
  const items: T[] = [];
  for (;;) { const page = await get(items.length); items.push(...page.items); if (!page.items.length || items.length >= page.page.total) return items; }
}
function Metric({label, value, to}: {label:string; value:number; to:string}) {
  return <Link to={to} className="workspace-section block hover:border-accent"><p className="text-sm text-muted">{label}</p><p className="mt-3 text-3xl font-semibold text-accent">{value.toLocaleString()}</p><p className="mt-3 text-xs text-muted">Open queue →</p></Link>;
}
function Breakdown({title, values}: {title:string; values:string[]}) {
  const counts = values.reduce<Record<string,number>>((out, value) => {out[value] = (out[value] ?? 0) + 1; return out;}, {});
  return <section className="workspace-section"><h3 className="font-semibold">{title}</h3><ul className="mt-3 space-y-2">{Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([name,count])=><li key={name} className="flex justify-between gap-3 text-sm"><span>{name}</span><strong>{count}</strong></li>)}</ul>{!values.length && <p className="mt-3 text-muted">No incoming detector evidence yet.</p>}</section>;
}
export function DashboardPage() {
  const resource = useApi(async signal => {
    const [review, alerts, cases, inbox, memory] = await Promise.all([
      unwrap(api.GET("/api/v2/selective-review/metrics", {signal})),
      allPages(offset => unwrap(api.GET("/api/v2/alerts", {params:{query:{limit:100,offset}},signal}))),
      allPages(offset => unwrap(api.GET("/api/v2/tier2/cases", {params:{query:{limit:100,offset}},signal}))),
      allPages(offset => unwrap(api.GET("/api/v2/external-alerts", {params:{query:{limit:100,offset}},signal}))),
      allPages(offset => unwrap(api.GET("/api/v2/triage-memory", {params:{query:{limit:100,offset}},signal}))),
    ]);
    return {review,alerts,cases,inbox,memory};
  }, []);
  return <div className="space-y-7">
    <header><p className="label-mono">Operations / Human-in-the-loop</p><h1 className="mt-2 text-2xl font-semibold">Dashboard</h1><p className="mt-2 text-muted">Review what needs attention. Keep human decisions in control.</p></header>
    <ApiView resource={resource}>{({review,alerts,cases,inbox,memory}) => <>
      <section aria-label="Actionable operational status"><h2 className="mb-3 text-lg font-semibold">Needs your attention</h2><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Needs Human Review" value={review.mustReviewCount + review.recommendedReviewCount} to="/analyst/selective-review"/>
        <Metric label="Tier 2 Candidates" value={alerts.filter(a=>a.state.handlingRoute === "tier2_candidate").length} to="/analyst/workspace"/>
        <Metric label="Open Tier 2 Cases" value={cases.filter(c=>c.status === "open" || c.status === "investigating").length} to="/analyst/tier2-cases"/>
        <Metric label="Incoming Alerts" value={inbox.filter(a=>a.status !== "admitted").length} to="/analyst/inbox"/>
      </div><p className="mt-2 text-xs text-muted">Incoming counts records not yet admitted, including held records. Human review includes required and recommended attention.</p></section>
      <section className="workspace-section"><h2 className="text-lg font-semibold">Review automation</h2><p className="mt-2 text-sm text-warn">No Immediate Review is not a human verdict.</p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-3">{[["Must Review",review.mustReviewCount],["Recommended Review",review.recommendedReviewCount],["No Immediate Review",review.noImmediateReviewCount],["Conflict-triggered recalls",review.conflictTriggeredRecallCount],["Audit samples",review.sampledOverrideCount]].map(([label,count])=><div key={label}><dt className="text-sm text-muted">{label}</dt><dd className="text-xl font-semibold">{count}</dd></div>)}</dl><p className="mt-3 text-xs text-muted">{review.dataBasis}</p></section>
      <section><h2 className="text-lg font-semibold">Security activity</h2><p className="mb-3 mt-1 text-sm text-muted">Incoming alert evidence only; these are not platform-wide detection totals.</p><div className="grid gap-4 lg:grid-cols-3">
        <Breakdown title="Top detections" values={inbox.map(a=>a.signature)}/><Breakdown title="Detection categories" values={inbox.map(a=>a.category)}/><Breakdown title="Detector source distribution" values={inbox.map(a=>a.detector)}/>
      </div><p className="mt-3 text-xs text-muted">Suricata is the primary operational source. XGBoost is supported as a secondary / historical detector. Custom signatures remain legacy compatibility evidence.</p></section>
      <section><h2 className="mb-3 text-lg font-semibold">Human learning</h2><div className="grid gap-4 sm:grid-cols-3">{[["Active Memory","active"],["Eligible for Activation","eligible_for_activation"],["Conflict Review","conflict_review"]].map(([label,status])=><Metric key={status} label={label!} value={memory.filter(m=>m.status===status).length} to="/analyst/triage-memory"/>)}</div></section>
      <section className="workspace-section"><h2 className="text-lg font-semibold">Trends & analytics</h2><p className="my-2 text-sm text-muted">Operational time-series trends are not supplied by the current API.</p><Link className="text-accent underline" to="/analyst/analytics">Explore available analytics →</Link></section>
    </>}</ApiView>
  </div>;
}
