import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState } from "../../components/states";
import { Card } from "../../components/ui";
import { ReleaseControl } from "../../features/alert/AnalystWork";

const LIMIT = 50;

function since(claimedAt: string | null | undefined) {
  if (!claimedAt) return "";
  const minutes = Math.floor((Date.now() - Date.parse(claimedAt)) / 60000);
  return Number.isFinite(minutes) && minutes >= 0 ? `claimed ${minutes} min ago` : "";
}

/** Claimed alerts for the administrator (user decision 2026-11-08). The admin cannot open the Analyst
 *  Workstation, so this list is the admin's way to release a claim. The server decides canRelease. */
export function ClaimedAlerts({ onReleased }: { onReleased?: () => void }) {
  const resource = useApi(signal => unwrap(api.GET("/api/v2/alerts", {
    signal, params: { query: { workScope: "in_review", limit: LIMIT, offset: 0, sort: "priority_desc" } },
  })), []);
  return <Card title="Claimed alerts" subtitle="Alerts that an analyst owns now. An administrator release needs a reason and is audited.">
    <div className="space-y-2 p-4 text-sm">
      {resource.status === "loading" && <p className="text-muted">Loading claimed alerts…</p>}
      {resource.status === "error" && <ErrorState error={resource.error} onRetry={resource.reload} />}
      {resource.status === "success" && (resource.data.items.length === 0
        ? <p className="text-muted">No alert is claimed.</p>
        : <>
          {resource.data.page.total > resource.data.items.length &&
            <p className="text-muted">Showing {resource.data.items.length} of {resource.data.page.total} claimed alerts.</p>}
          <ul aria-label="Claimed alerts" className="divide-y divide-border">
            {resource.data.items.map(item => {
              const work = item.work;
              return <li key={item.operationalAlertRef} className="min-w-0 space-y-1 py-2">
                <p className="break-words"><span className="font-mono text-xs text-accent">{item.operationalAlertRef.slice(0, 8)}</span> {item.title}</p>
                <p className="text-xs text-muted">Owner: <strong className="text-text">{work?.ownerName ?? "Unknown"}</strong>
                  {work?.claimedAt && <> · {since(work.claimedAt)}</>}
                  {work?.idle && <span className="text-warn"> · idle</span>}</p>
                {work?.canRelease && <div className="text-xs"><ReleaseControl key={item.operationalAlertRef + ":" + work.revision}
                  work={work} alertRef={item.operationalAlertRef} onReleased={() => { resource.reload(); onReleased?.(); }} /></div>}
              </li>;
            })}
          </ul>
        </>)}
    </div>
  </Card>;
}
