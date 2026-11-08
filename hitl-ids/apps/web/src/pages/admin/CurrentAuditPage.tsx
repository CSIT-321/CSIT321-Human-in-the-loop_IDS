import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";
import { formatDateTime } from "../../design/format";

type Event = Schemas["CurrentAuditEvent"];
type Category = Event["eventCategory"];
type Source = Event["decisionSource"];
type ObjectType = Event["objectType"];

const categories: Category[] = ["WORKSPACE", "WORK", "VERDICT", "MEMORY", "REVIEW", "TIER2", "RESPONSE", "RESOLUTION"];
const sources: Source[] = ["analyst", "system_policy", "admin", "historical_migration"];
const objectTypes: ObjectType[] = ["workspace", "alert", "case", "lesson", "recommendation"];
const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const short = (value: string) => value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;

function EventRow({ event }: { event: Event }) {
  return <tr className="border-t border-border align-top" data-testid="audit-event">
    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted"><time dateTime={event.timestamp}>{formatDateTime(event.timestamp)}</time></td>
    <td className="px-3 py-3 text-sm">{event.actorType === "system" ? "System Policy" : event.actorName ?? "Unknown user"}</td>
    <td className="px-3 py-3 text-xs font-semibold text-accent">{event.eventCategory}</td>
    <td className="px-3 py-3 text-sm">{event.action}</td>
    <td className="px-3 py-3 text-sm"><div>{label(event.objectType)} <span className="font-mono" title={event.objectRef}>{short(event.objectRef)}</span></div>
      <div className="text-xs text-muted">{event.workspace}</div></td>
    <td className="min-w-56 px-3 py-3 text-sm"><p className="max-w-lg break-words">{event.summary}</p>
      <details className="mt-2 text-xs"><summary className="cursor-pointer text-accent">Event details</summary>
        <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 break-all">
          <dt>Event ref</dt><dd className="font-mono">{event.eventRef}</dd>
          <dt>Source</dt><dd>{event.sourceSubsystem}</dd>
          <dt>Decision source</dt><dd>{label(event.decisionSource)}</dd>
          {event.alertRef && <><dt>Alert ref</dt><dd className="font-mono">{event.alertRef}</dd></>}
          {event.caseRef && <><dt>Case ref</dt><dd className="font-mono">{event.caseRef}</dd></>}
          {event.lessonRef && <><dt>Lesson ref</dt><dd className="font-mono">{event.lessonRef}</dd></>}
          {Object.entries(event.detail ?? {}).filter(([, value]) => value != null).map(([key, value]) => <div className="contents" key={key}>
            <dt>{label(key)}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
          </div>)}
        </dl>
      </details></td>
    <td className="px-3 py-3 text-sm">{event.result ?? "Not applicable"}</td>
  </tr>;
}

export function CurrentAuditPage() {
  const [category, setCategory] = useState<Category | "">("");
  const [source, setSource] = useState<Source | "">("");
  const [objectType, setObjectType] = useState<ObjectType | "">("");
  const [workspace, setWorkspace] = useState<"" | "operational" | "v3-1-replay" | "global">("");
  const [actorInput, setActorInput] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [actor, setActor] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 25;
  const resource = useApi(signal => unwrap(api.GET("/api/admin/audit/current", {
    signal, params: { query: { limit, offset, category: category || undefined, decisionSource: source || undefined,
      objectType: objectType || undefined, actor: actor || undefined, search: search || undefined,
      workspace: workspace || undefined } },
  })), [limit, offset, category, source, objectType, actor, search, workspace]);
  const page = resource.status === "success" ? resource.data : undefined;

  return <div className="min-w-0 space-y-5">
    <PageHeader title="Current HITL Audit" subtitle="Read-only timeline of durable current product decisions in the selected operational workspace." />
    <Link className="text-sm text-accent underline" to="/admin/evaluation">Back to Evaluation &amp; Audit</Link>
    <Card title="Filters" subtitle="Applied on the server before pagination. Workspace control actions are global.">
      <div className="grid min-w-0 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
        <label className="min-w-0 text-sm">Category
          <select aria-label="Category" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={category}
            onChange={event => { setCategory(event.target.value as Category | ""); setOffset(0); }}>
            <option value="">All categories</option>{categories.map(value => <option key={value} value={value}>{value}</option>)}
          </select></label>
        <label className="min-w-0 text-sm">Decision source
          <select aria-label="Decision source" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={source}
            onChange={event => { setSource(event.target.value as Source | ""); setOffset(0); }}>
            <option value="">All sources</option>{sources.map(value => <option key={value} value={value}>{label(value)}</option>)}
          </select></label>
        <label className="min-w-0 text-sm">Object type
          <select aria-label="Object type" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={objectType}
            onChange={event => { setObjectType(event.target.value as ObjectType | ""); setOffset(0); }}>
            <option value="">All objects</option>{objectTypes.map(value => <option key={value} value={value}>{label(value)}</option>)}
          </select></label>
        <label className="min-w-0 text-sm">Workspace
          <select aria-label="Workspace" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={workspace}
            onChange={event => { setWorkspace(event.target.value as typeof workspace); setOffset(0); }}>
            <option value="">Selected + global</option>
            <option value={page?.activeWorkspace ?? "operational"}>{page?.activeWorkspace === "v3-1-replay" ? "V3.1 Demo Replay" : "Operational"}</option>
            <option value="global">Global control</option>
          </select></label>
        <label className="min-w-0 text-sm">Actor name
          <input aria-label="Actor name" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={actorInput}
            maxLength={100} onChange={event => setActorInput(event.target.value)} placeholder="Filter human actor" /></label>
        <label className="min-w-0 text-sm sm:col-span-2">Alert / Case / Lesson ref
          <input aria-label="Reference search" className="mt-1 w-full rounded-sm border border-border bg-surface p-2" value={searchInput}
            maxLength={120} onChange={event => setSearchInput(event.target.value)} placeholder="Full or partial reference" /></label>
        <button className="self-end rounded-sm border border-border bg-raised px-3 py-2 text-sm hover:bg-surface"
          onClick={() => { setActor(actorInput.trim()); setSearch(searchInput.trim()); setOffset(0); }}>Apply text filters</button>
      </div>
    </Card>
    {resource.status === "error" && <ErrorState error={resource.error} onRetry={resource.reload} />}
    {/* X7 (S8-08): on an error the timeline says so instead of "Loading" forever. */}
    <Card title="Timeline" subtitle={`Active workspace: ${page?.activeWorkspace ?? (resource.status === "error" ? "Unavailable" : "Loading")}. Newest durable events first.`}>
      <div className="min-w-0">
        <p className="px-4 pt-3 text-xs text-muted">{page ? `${page.total} matching events` : resource.status === "error" ? "Events unavailable." : "Loading events…"}</p>
        <div className="max-w-full overflow-x-auto">
          <table className="min-w-[1080px] w-full text-left">
            <thead><tr className="text-xs uppercase text-muted">{["Time", "Actor", "Category", "Action", "Object", "Summary", "Result"].map(column =>
              <th className="px-3 py-2" key={column} scope="col">{column}</th>)}</tr></thead>
            <tbody>{page?.items.map(event => <EventRow key={event.eventRef} event={event} />)}</tbody>
          </table>
        </div>
        {page && page.items.length === 0 && <p className="p-4 text-sm text-muted">No durable events match these filters.</p>}
        {page && page.total > limit && <div className="flex items-center justify-between gap-3 p-4 text-sm">
          <button className="rounded-sm border border-border px-3 py-1 disabled:opacity-50" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
          <span>{offset + 1}–{Math.min(offset + limit, page.total)} of {page.total}</span>
          <button className="rounded-sm border border-border px-3 py-1 disabled:opacity-50" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)}>Next</button>
        </div>}
      </div>
    </Card>
    <p className="text-xs text-muted">Current HITL Audit is a product event projection. Historical Feedback / Legacy Audit and frozen Final V3.1 Evaluation are separate records.</p>
  </div>;
}
