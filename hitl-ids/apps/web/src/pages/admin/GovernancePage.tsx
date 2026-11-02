import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView } from "../../components/states";
import { Card, PageHeader, Pill } from "../../components/ui";

function Fact({ label, value }: { label: string; value: string | number | boolean }) {
  return <div className="min-w-0 border-b border-border py-2 text-sm sm:grid sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)] sm:gap-3">
    <dt className="text-muted">{label}</dt><dd className="break-words font-medium text-text">{typeof value === "boolean" ? value ? "Yes" : "No" : value}</dd>
  </div>;
}
const percent = (ratio: number) => `${(ratio * 100).toFixed(0)}%`;

export function GovernancePage() {
  const resource = useApi(signal => unwrap(api.GET("/api/admin/governance", { signal })), []);
  return <div className="min-w-0 space-y-5">
    <PageHeader title="HITL Governance" subtitle="Read-only current policies for Suricata, human review, and response approval." />
    <ApiView resource={resource}>{data => <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      <Card title="System Attack Classification"><dl className="p-4">
        <Fact label="Policy version" value={data.classification.version} />
        <Fact label="Detector source" value="Suricata" />
        <Fact label="Unknown fallback" value={data.classification.conflictPolicy === "unknown_needs_expert" ? "Unknown / Needs Expert" : "Not available"} />
        <p className="mt-3 text-sm text-muted">Unknown / Needs Expert → automatic Tier 2 Expert Review → formal Tier 2 Case.</p>
      </dl></Card>
      <Card title="System Routing"><dl className="p-4">
        <Fact label="Policy version" value={data.routing.version} />
        <Fact label="Tier 1" value="Routine human review" />
        <Fact label="Automatic Tier 2" value={data.routing.rules.includes("unknown_classification_requires_expert") ? "Unknown requires expert review" : "Not available"} />
        <Fact label="Attribution" value="System Policy" />
      </dl></Card>
      <Card title="Triage Memory"><div className="p-4"><dl>
        <Fact label="Policy version" value={data.memory.version} />
        <Fact label="Exact scope" value={data.memory.exactRequiredFields.join(", ")} />
        <Fact label="Narrow scope" value={data.memory.narrowRequiredFields.join(", ")} />
        <Fact label="Minimum support" value={data.memory.minimumSupport} />
        <Fact label="Minimum agreement" value={percent(data.memory.minimumAgreementRatio)} />
        <Fact label="Maximum conflicts" value={data.memory.maximumConflicts} />
        <Fact label="Default validity" value={`${data.memory.defaultValidityDays} days`} />
      </dl><p className="mt-3 text-sm text-muted">Human judgement becomes evidence. Reusable guidance requires the policy thresholds.</p></div></Card>
      <Card title="Automatic Human Learning"><div className="p-4"><dl>
        <Fact label="Status" value={data.automaticLearningEnabled ? "Enabled" : "Disabled"} />
        <Fact label="Current policy" value={data.autoLearning.version} />
        <Fact label="Eligible outcomes" value={data.autoLearning.eligibleOutcomes.join(", ").replaceAll("_", " ")} />
        <Fact label="Evidence scope" value={data.autoLearning.evidenceScope} />
        <Fact label="Activation scope" value={data.autoLearning.activationScope} />
        <Fact label="Independent support" value={data.memory.minimumSupport} />
        <Fact label="Agreement required" value={percent(data.memory.minimumAgreementRatio)} />
        <Fact label="Maximum conflicts" value={data.memory.maximumConflicts} />
        <Fact label="Fixed validity" value={`${data.memory.defaultValidityDays} days`} />
        <Fact label="Sliding renewal" value={data.autoLearning.slidingRenewal} />
        <Fact label="Automatic post-expiry reactivation" value={data.autoLearning.postExpiryReactivation} />
      </dl></div></Card>
      <Card title="Selective Review Safety"><div className="p-4"><dl>
        <Fact label="Policy version" value={data.selectiveReview.version} />
        <Fact label="Minimum support" value={data.selectiveReview.minimumSupport} />
        <Fact label="False Positive support" value={data.selectiveReview.falsePositiveMinimumSupport} />
        <Fact label="Minimum agreement" value={percent(data.selectiveReview.minimumAgreementRatio)} />
        <Fact label="Trusted context maximum age" value={`${data.selectiveReview.contextMaximumAgeHours} hours`} />
        <Fact label="Campaign threshold" value={data.selectiveReview.campaignAlertThreshold} />
        <Fact label="Deterministic audit sample" value={`${data.selectiveReview.auditSamplePercent}%`} />
      </dl><p className="mt-3 text-sm text-muted">Active Memory alone does not suppress review. Current safety conditions still apply.</p></div></Card>
      <Card title="Shared Analyst Work"><div className="p-4"><dl>
        <Fact label="Policy version" value={data.analystWork.version} />
        <Fact label="Arbitration window" value={`${data.analystWork.claimArbitrationWindowMs} ms`} />
      </dl><p className="mt-3 text-sm text-muted">Available alert → intentional selection → automatic claim arbitration. One distinct claimant becomes Owner; more than one causes Conflict with no owner. An already-owned alert opens as Viewer.</p></div></Card>
      <Card title="Response Boundary"><div className="space-y-3 p-4 text-sm">
        <p>Response Execution: <Pill tone="warn">{data.responseExecution === "disabled" ? "Disabled" : "Not available"}</Pill></p>
        <p>Human decisions: Approve or Reject.</p>
        <p>Approved recommendation: <strong>Approved — Not Executed</strong>.</p>
        <p className="text-muted">No firewall or SOAR execution is implied.</p>
      </div></Card>
    </div>}</ApiView>
  </div>;
}
