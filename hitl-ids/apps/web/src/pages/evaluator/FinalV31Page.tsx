import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, KeyValues, PageHeader, Pill, StatStrip } from "../../components/ui";

type Row = Schemas["FinalRecord"];
type Filters = { phase: string; population: string; stratum: string; pattern: string;
  baselineDisposition: string; adaptiveDisposition: string; deferral: string;
  memory: string; case: string; search: string };
const EMPTY: Filters = { phase: "", population: "", stratum: "", pattern: "", baselineDisposition: "",
  adaptiveDisposition: "", deferral: "", memory: "", case: "", search: "" };
const label = (value: string | null | undefined) => value ? value.replaceAll("_", " ").replaceAll("-", " ") : "N/A";
const short = (value: string | null | undefined) => value ? `${value.slice(0, 8)}…` : "N/A";
const basePath = (path: string) => path.startsWith("/admin/") ? "/admin/evaluation/final-v3-1" : "/evaluator/final-v3-1";

function Select({ title, value, options, change }: {
  title: string; value: string; options: readonly string[]; change: (value: string) => void;
}) {
  return <label className="min-w-0 text-xs text-muted">{title}
    <select aria-label={title} value={value} onChange={event => change(event.target.value)}
      className="mt-1 block w-full rounded-sm border border-border bg-raised px-2 py-1.5 text-sm text-text">
      <option value="">All</option>{options.map(option => <option key={option} value={option}>{label(option)}</option>)}
    </select>
  </label>;
}

function RecordsTable({ rows, base }: { rows: Row[]; base: string }) {
  return <div className="max-w-full overflow-x-auto"><table className="min-w-[1100px] w-full text-left text-xs">
    <thead className="text-muted"><tr>{["Index", "Phase", "Population", "Stratum", "Pattern", "Alert",
      "Attack category", "Priority", "Baseline", "Adaptive", "Memory lesson", "Tier 2 Case", "Outcome / deferral"]
      .map(title => <th key={title} className="whitespace-nowrap px-2 py-2 font-medium">{title}</th>)}</tr></thead>
    <tbody>{rows.map(row => <tr key={row.index} className="border-t border-border hover:bg-raised">
      <td className="px-2 py-2 font-mono"><Link to={`${base}/records/${row.index}`} className="text-accent hover:underline"
        aria-label={`Open record ${row.index}`}>{row.index}</Link></td>
      <td className="px-2 py-2">{label(row.phase)}</td><td className="px-2 py-2">{label(row.population)}</td>
      <td className="whitespace-nowrap px-2 py-2">{label(row.stratum)}</td><td className="px-2 py-2 font-mono">{row.pattern}</td>
      <td className="px-2 py-2 font-mono" title={row.alertRef}>{short(row.alertRef)}</td>
      <td className="px-2 py-2">{label(row.attackCategory)}</td><td className="px-2 py-2">{row.priority ?? "N/A"}</td>
      <td className="whitespace-nowrap px-2 py-2">{label(row.baselineDisposition)}</td>
      <td className="whitespace-nowrap px-2 py-2">{label(row.adaptiveDisposition)}</td>
      <td className="px-2 py-2 font-mono" title={row.matchedMemoryLessonRef ?? row.learningLessonRef ?? undefined}>
        {short(row.matchedMemoryLessonRef ?? row.learningLessonRef)}</td>
      <td className="px-2 py-2 font-mono" title={row.caseRef ?? undefined}>{short(row.caseRef)}</td>
      <td className="whitespace-nowrap px-2 py-2">{row.phase === "learning" ? label(row.humanOutcome) :
        <Pill tone={row.deferralClassification === "unsafe" ? "danger" : row.deferralClassification === "safe" ? "ok" : "muted"}>
          {label(row.deferralClassification)}</Pill>}</td>
    </tr>)}</tbody></table></div>;
}

export function FinalV31Page() {
  const base = basePath(useLocation().pathname);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [searchDraft, setSearchDraft] = useState("");
  const [offset, setOffset] = useState(0);
  const update = (key: keyof Filters, value: string) => { setFilters(old => ({ ...old, [key]: value })); setOffset(0); };
  const query = { limit: 25, offset,
    phase: (filters.phase || undefined) as "learning" | "holdout" | undefined,
    population: (filters.population || undefined) as "primary" | "supplementary" | undefined,
    stratum: filters.stratum || undefined, pattern: filters.pattern || undefined,
    baselineDisposition: filters.baselineDisposition || undefined,
    adaptiveDisposition: filters.adaptiveDisposition || undefined,
    deferral: (filters.deferral || undefined) as "safe" | "unsafe" | "not-deferred" | undefined,
    memory: (filters.memory || undefined) as "matched" | "unmatched" | undefined,
    case: (filters.case || undefined) as "has" | "none" | undefined, search: filters.search || undefined };
  const summary = useApi(signal => unwrap(api.GET("/api/evaluation/final-v3-1", { signal })), []);
  const records = useApi(signal => unwrap(api.GET("/api/evaluation/final-v3-1/records", {
    params: { query }, signal })), [offset, ...Object.values(filters)]);
  const impact = useApi(signal => unwrap(api.GET("/api/evaluation/final-v3-1/memory-impact", { signal })), []);
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Final Evaluation V3.1" subtitle="Run 001 · Completed / Frozen · official read-only evidence" />
    <p className="text-sm text-muted">Demo Replay uses the same workload interactively. Official effectiveness comes only from these immutable controlled results.</p>
    <ApiView resource={summary}>{data => <>
      <StatStrip label="Frozen workload composition" stats={[
        { label: "Total", value: data.total }, { label: "Learning", value: data.learning },
        { label: "Holdout", value: data.holdout }, { label: "Primary", value: data.primary },
        { label: "Unknown", value: data.unknown }, { label: "Drift", value: data.drift },
      ]} />
      <StatStrip label={`Official primary effectiveness, denominator ${data.primary}`} stats={[
        { label: "Baseline review", value: data.primaryBaselineImmediateReview },
        { label: "Adaptive review", value: data.primaryAdaptiveImmediateReview },
        { label: "Reduction", value: `${data.primaryReviewReduction} / ${(100 * data.primaryReviewReductionRate).toFixed(2)}%` },
        { label: "Safe deferrals", value: data.primarySafeDeferrals },
        { label: "Primary unsafe", value: data.primaryUnsafeDeferrals },
      ]} />
      <Card title="Workload composition" subtitle={`Primary effectiveness is measured on ${data.primary} Primary Holdout alerts.`}>
        <div className="grid gap-4 text-sm text-text md:grid-cols-3">
          <div><strong>{data.total} Total workload</strong><p className="mt-2 pl-3">{data.learning} Learning</p><p className="pl-3">{data.holdout} Holdout</p></div>
          <div><strong>{data.primary} Primary Holdout</strong><div className="mt-2 pl-3 text-muted">
            {(["stable_matching_benign", "unseen_benign", "malicious", "suspicious"] as const)
              .map(key => <p key={key}>{data.strata[key]} {label(key)}</p>)}</div></div>
          <div><strong>{data.supplementary} Supplementary Holdout</strong><div className="mt-2 pl-3 text-muted">
            <p>{data.unknown} Unknown Tier 2 controls</p><p>{data.drift} Drift / Conflict controls</p></div></div>
        </div><p className="mt-3 text-xs text-dim">Runtime {data.runtimeSha}</p>
      </Card>
      <Card title="All-Holdout safety" subtitle="Supplementary controls are shown separately from the primary denominator.">
        <p className="text-sm text-text">Initial deferrals: {data.allHoldoutInitialDeferrals} · Initial unsafe deferrals:
          <strong className="text-danger"> {data.allHoldoutUnsafeDeferrals}</strong> · Post-contradiction unsafe: {data.postContradictionUnsafeDeferrals} / {data.postContradictionPopulation} · Unknown formal Tier 2 Cases: {data.unknownFormalTier2Cases} / {data.unknown}</p>
      </Card>
    </>}</ApiView>
    <Card title="Evaluation records" subtitle="Server-filtered evidence. Click an index to inspect the frozen input and outcome.">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
        <Select title="Phase" value={filters.phase} options={["learning", "holdout"]} change={v => update("phase", v)} />
        <Select title="Population" value={filters.population} options={["primary", "supplementary"]} change={v => update("population", v)} />
        <Select title="Stratum" value={filters.stratum} options={summary.status === "success" ? Object.keys(summary.data.strata) : []} change={v => update("stratum", v)} />
        <Select title="Pattern" value={filters.pattern} options={impact.status === "success" ? impact.data.items.map(item => item.pattern) : []} change={v => update("pattern", v)} />
        <Select title="Baseline disposition" value={filters.baselineDisposition} options={["must_review", "recommended_review", "no_immediate_review"]} change={v => update("baselineDisposition", v)} />
        <Select title="Adaptive disposition" value={filters.adaptiveDisposition} options={["must_review", "recommended_review", "no_immediate_review"]} change={v => update("adaptiveDisposition", v)} />
        <Select title="Deferral" value={filters.deferral} options={["safe", "unsafe", "not-deferred"]} change={v => update("deferral", v)} />
        <Select title="Memory" value={filters.memory} options={["matched", "unmatched"]} change={v => update("memory", v)} />
        <Select title="Tier 2 Case" value={filters.case} options={["has", "none"]} change={v => update("case", v)} />
        <form className="text-xs text-muted" onSubmit={event => { event.preventDefault(); update("search", searchDraft.trim()); }}>Search
          <div className="mt-1 flex"><input aria-label="Search records" value={searchDraft} onChange={event => setSearchDraft(event.target.value)}
            className="min-w-0 flex-1 rounded-l-sm border border-border bg-raised px-2 py-1.5 text-sm text-text" placeholder="Alert, IP, signature…" />
            <button className="rounded-r-sm border border-border bg-raised px-2 text-sm text-accent">Go</button></div>
        </form>
      </div>
      <div className="mt-4"><ApiView resource={records}>{data => <>
        <p className="mb-2 text-xs text-muted" role="status">{data.total} matching records · showing {data.items.length}</p>
        {data.items.length ? <RecordsTable rows={data.items} base={base} /> : <EmptyState title="No records match these filters" />}
        <div className="mt-3 flex items-center gap-3 text-sm">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))} className="text-accent disabled:opacity-40">Previous</button>
          <span className="text-muted">Page {Math.floor(offset / 25) + 1} of {Math.max(1, Math.ceil(data.total / 25))}</span>
          <button disabled={offset + 25 >= data.total} onClick={() => setOffset(offset + 25)} className="text-accent disabled:opacity-40">Next</button>
        </div>
      </>}</ApiView></div>
    </Card>
    <Card title="Memory Impact" subtitle="Matched = context match; Used = policy selected; Deferred = no immediate review; Blocked = matched but review required; Recalled = conflict withdrew guidance.">
      <ApiView resource={impact}>{data => <div className="max-w-full overflow-x-auto"><table className="min-w-[900px] w-full text-left text-xs">
        <thead><tr>{["Lesson", "Pattern", "Outcome", "Support", "Conflicts", "Agreement", "Status", "Matched", "Used", "Deferred", "Blocked", "Audit sampled", "Conflict withdrawal", "Matching records"]
          .map(x => <th key={x} className="px-2 py-2 text-muted">{x}</th>)}</tr></thead>
        <tbody>{data.items.map(item => <tr key={item.lessonRef} className="border-t border-border">
          <td className="px-2 py-2 font-mono" title={item.lessonRef}>{short(item.lessonRef)}</td><td className="px-2 py-2">{item.pattern}</td>
          <td className="px-2 py-2">{label(item.outcome)}</td><td className="px-2 py-2">{item.support}</td>
          <td className="px-2 py-2">{item.conflicts}</td><td className="px-2 py-2">{item.agreement.toFixed(2)}</td>
          <td className="px-2 py-2">{label(item.status)}</td><td className="px-2 py-2">{item.matched}</td>
          <td className="px-2 py-2">{item.used}</td><td className="px-2 py-2">{item.deferred}</td>
          <td className="px-2 py-2">{item.blocked}</td><td className="px-2 py-2">{item.auditSampled}</td>
          <td className="px-2 py-2">{item.conflictWithdrawn ? "Yes" : "No"}</td>
          <td className="px-2 py-2"><details><summary className="cursor-pointer text-accent">{item.affectedIndices.length} records</summary>
            <div className="mt-1 max-h-32 overflow-y-auto">{item.affectedIndices.map(index => <Link key={index} to={`${base}/records/${index}`}
              className="mr-2 inline-block text-accent hover:underline">{index}</Link>)}</div></details></td>
        </tr>)}</tbody></table></div>}</ApiView>
    </Card>
    <ApiView resource={summary}>{data => <Card title="Drift proof" subtitle="The two initial unsafe deferrals remain visible; authoritative feedback withdrew guidance.">
      <div className="grid gap-3 md:grid-cols-2">{Array.from(new Set(data.driftTimeline.map(item => String(item.pattern)))).map(pattern => {
        const events = data.driftTimeline.filter(item => item.pattern === pattern);
        const first = events[0];
        return <div key={pattern} className="rounded-sm border border-border p-3 text-sm text-text"><strong>{pattern}</strong>
          <p>First contradiction <Link className="text-accent" to={`${base}/records/${String(first?.eventIndex)}`}>record {String(first?.eventIndex)}</Link>:
            {" "}{label(String(first?.disposition))} → {label(String(first?.oracleOutcome))}</p>
          <p>Lesson: {label(String(first?.beforeStatus))} → {label(String(first?.afterFeedbackStatus))}</p>
          <p>Later alerts: {events.slice(1).length} must review</p>
        </div>;
      })}</div>
    </Card>}</ApiView>
  </div>;
}

export function FinalV31DetailPage() {
  const index = Number(useParams().index);
  const base = basePath(useLocation().pathname);
  const record = useApi(signal => unwrap(api.GET("/api/evaluation/final-v3-1/records/{index}", {
    params: { path: { index } }, signal })), [index]);
  return <div className="min-w-0 space-y-5"><PageHeader title={`Final V3.1 · Record ${index}`} subtitle="Official frozen evidence · read-only" />
    <Link to={base} className="text-sm text-accent">← All records</Link>
    <ApiView resource={record}>{row => <>
      <Card title="Identity"><KeyValues rows={[["Index", row.index], ["AlertRef", <span className="break-all font-mono">{row.alertRef}</span>],
        ["Phase", label(row.phase)], ["Population", label(row.population)], ["Stratum", label(row.stratum)],
        ["Pattern", row.pattern], ["Synthetic analyst", row.analyst], ["Planned route", label(row.plannedRoute)]]} /></Card>
      <Card title="Frozen Suricata input"><KeyValues rows={[["Timestamp", row.timestamp], ["Signature", row.signature],
        ["Signature ID", row.signatureId], ["Native category", row.nativeCategory], ["Native severity", row.nativeSeverity],
        ["Source", `${row.sourceIp}:${row.sourcePort}`], ["Destination", `${row.destinationIp}:${row.destinationPort}`],
        ["Protocol", row.protocol], ["Flow ID", row.flowId]]} /></Card>
      {row.phase === "learning" ? <Card title="Learning evidence" subtitle="Human feedback generated Memory evidence. Holdout comparisons are N/A.">
        <KeyValues rows={[["Human outcome", label(row.humanOutcome)], ["Verdict reference", row.verdictRef ?? "Not recorded"],
          ["Lesson", row.learningLessonRef ?? "Not recorded"], ["Status at feedback", label(row.learningLessonStatus)],
          ["Support at feedback", row.learningSupport ?? "Not recorded"], ["Conflicts at feedback", row.learningConflicts ?? "Not recorded"],
          ["Baseline / Adaptive", "N/A — Learning phase"]]} /></Card> : <>
        <Card title="System result"><KeyValues rows={[["Attack category", label(row.attackCategory)],
          ["Operational priority", row.priority ?? "N/A"], ["Route", label(row.route)], ["Tier 2 Case", row.caseRef ?? "N/A"]]} /></Card>
        <div className="grid gap-4 lg:grid-cols-2"><Card title="Baseline"><KeyValues rows={[["Disposition", label(row.baselineDisposition)],
          ["Review required", String(row.baselineReviewRequired)], ["Reason codes", row.baselineReasonCodes.join(", ") || "N/A"]]} /></Card>
          <Card title="Adaptive"><KeyValues rows={[["Disposition", label(row.adaptiveDisposition)],
            ["Review required", String(row.adaptiveReviewRequired)], ["Reason codes", row.adaptiveReasonCodes.join(", ") || "N/A"]]} /></Card></div>
        <Card title="Memory evidence"><p className="text-sm text-text">Policy-selected lesson: {row.matchedMemoryLessonRef ?? "None"}</p>
          <div className="mt-3 space-y-3">{row.memoryMatches.length ? row.memoryMatches.map(match =>
            <div key={match.lessonRef} className="border-t border-border pt-2 text-xs text-muted">
              <p className="font-mono text-text">{match.lessonRef}</p><p>{label(match.status)} · {label(match.outcome)} · guidance {String(match.guidanceActive)}</p>
              <p>Support {match.support} · conflicts {match.conflicts} · agreement {match.agreement.toFixed(2)}</p>
              <p>Matched: {match.matchedFields.join(", ") || "None"}</p><p>Mismatched: {match.mismatchedFields.join(", ") || "None"}</p>
              <p>Unavailable: {match.unavailableFields.join(", ") || "None"}</p>
            </div>) : <p className="text-sm text-muted">No contextual Memory match.</p>}</div>
        </Card>
        <Card title="Deferral and oracle outcome" subtitle="Visible only to Admin and Evaluator; never sent to Analyst Workstation.">
          <KeyValues rows={[["Deferral", label(row.deferralClassification)], ["Oracle outcome", label(row.oracleOutcome)]]} />
          {row.deferralClassification === "unsafe" && <p className="mt-3 text-sm text-danger">Initial unsafe deferral. Later withdrawal does not erase this result.</p>}
        </Card>
        {row.drift && <Card title="Frozen drift timeline"><KeyValues rows={Object.entries(row.drift)
          .map(([key, value]) => [label(key), value === null ? "N/A" : String(value)])} /></Card>}
      </>}
    </>}</ApiView>
  </div>;
}
