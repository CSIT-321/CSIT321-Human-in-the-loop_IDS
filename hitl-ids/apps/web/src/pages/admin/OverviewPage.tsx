import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState } from "../../components/states";
import { Card, PageHeader, Pill } from "../../components/ui";

type Overview = Schemas["AdminOverview"];
const shown = (value: string | number | null | undefined) => value == null ? "Not available" :
  typeof value === "number" ? value.toLocaleString() : value;

function Measure({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div className="min-w-0 rounded-sm border border-border bg-raised px-3 py-2">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="mt-1 break-words font-mono text-lg font-semibold text-text">{shown(value)}</dd>
  </div>;
}

export function OverviewPage() {
  const resource = useApi(signal => unwrap(api.GET("/api/admin/overview", { signal })), []);
  const data: Overview | undefined = resource.status === "success" ? resource.data : undefined;
  const operational = data?.operational;
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Overview" subtitle="Current Suricata and Human-in-the-Loop operational state in the active workspace." />
    <button className="rounded-sm border border-border bg-raised px-3 py-1.5 text-sm hover:bg-surface" onClick={resource.reload}>Refresh overview</button>
    {resource.status === "error" && <ErrorState error={resource.error} onRetry={resource.reload} />}
    <Card title="System" subtitle="Availability of this API and the selected workspace; these are not production health probes.">
      <dl className="grid min-w-0 gap-2 p-4 sm:grid-cols-2 xl:grid-cols-5">
        <Measure label="API status" value={resource.status === "success" ? "Responding" : resource.status === "loading" ? "Checking" : "Not available"} />
        <Measure label="Database availability" value={data?.databaseReady ? "Available" : undefined} />
        <Measure label="Active Workspace" value={data?.activeWorkspaceName} />
        <Measure label="Workspace availability" value={data?.workspaceReady ? "Available" : undefined} />
        <Measure label="Workspace alert count" value={data?.workspaceAlertCount} />
      </dl>
    </Card>
    <Card title="Operational Work" subtitle="Current operational alerts and exclusive Tier 1 work, not historical flow scoring.">
      <dl className="grid min-w-0 gap-2 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Measure label="Operational Alerts" value={operational?.totalAlerts} />
        <Measure label="Available Work" value={operational?.availableWork} />
        <Measure label="In Review" value={operational?.inReviewWork} />
        <Measure label="Completed" value={operational?.completedWork} />
        <Measure label="Escalated" value={operational?.escalatedWork} />
        <Measure label="Open Tier 2 Cases" value={operational?.openTier2Cases} />
        <Measure label="No Immediate Review" value={operational?.noImmediateReview} />
      </dl>
    </Card>
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      <Card title="HITL" subtitle="Human learning in the active workspace.">
        <dl className="grid min-w-0 gap-2 p-4 sm:grid-cols-2">
          <Measure label="Memory lessons" value={data?.memory.total} />
          <Measure label="Active lessons" value={data?.memory.active} />
          <Measure label="Conflict Review lessons" value={data?.memory.conflictReview} />
          <Measure label="Memory policy version" value={data?.memoryPolicyVersion} />
          <Measure label="Selective Review policy version" value={data?.selectiveReviewPolicyVersion} />
        </dl>
      </Card>
      <Card title="Detection & Routing" subtitle="Current system policy, separate from historical Signature/XGBoost runs.">
        <div className="space-y-3 p-4 text-sm">
          <p>Detector: <Pill tone="accent">{data?.detectorSource ?? "Not available"}</Pill></p>
          <p className="break-words">Classification policy: <strong>{shown(data?.classificationPolicyVersion)}</strong></p>
          <p className="break-words">Routing policy: <strong>{shown(data?.routingPolicyVersion)}</strong></p>
        </div>
      </Card>
    </div>
    <p className="text-xs text-muted">This post-V3.1 Admin surface was not part of the frozen Final V3.1 evaluation.</p>
  </div>;
}
