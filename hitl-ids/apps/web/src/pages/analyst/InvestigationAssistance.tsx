import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { TrustedContextPanel } from "./TrustedContextPanel";

const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";

export function InvestigationAssistance({ caseRef, revision, prefix, onSelect }: {
  caseRef: string; revision: number; prefix: string; onSelect?: (ref: string) => void;
}) {
  const resource = useApi(signal => unwrap(api.GET("/api/v2/tier2/cases/{caseRef}/assistance", {
    params: { path: { caseRef } }, signal,
  })), [caseRef, revision]);
  if (resource.status === "loading") return <p role="status">Loading investigation assistance...</p>;
  if (resource.status === "error") return <div><p role="alert">Investigation assistance: {resource.error.message}</p><button className={button} onClick={resource.reload}>Retry assistance</button></div>;
  const { brief, relatedAlerts, suggestedSteps, assistancePolicyVersion, correlationWindowHours, maximumRelated } = resource.data;
  const snapshot = brief.atCaseCreation;
  const alert = snapshot.detector;
  const bundle = brief.suricataEvidenceAtCreation;
  const classification = brief.classificationAtAdmission;
  const verdict = brief.currentTier1Verdict;
  return <section aria-label="Investigation Assistance" className="min-w-0 space-y-5 border-t border-border pt-4 text-sm [overflow-wrap:anywhere]">
    <p className="text-xs text-muted">{assistancePolicyVersion} · Advisory only. No Finding, linking or response is performed automatically.</p>
    <section aria-label="Investigation Brief" className="space-y-3">
      <h2 className="text-base font-semibold">Investigation Brief</h2>
      <h3 className="font-semibold">At Case Creation</h3>
      <dl className="grid min-w-0 gap-3 sm:grid-cols-2">
        <div><dt className="text-muted">Why Tier 2</dt><dd>{snapshot.routingDecision.decisionSource === "system_policy" ? "Automatic system routing" : "Manual analyst escalation"}: {snapshot.escalationReason}</dd></div>
        <div><dt className="text-muted">Original System Routing at Admission</dt><dd>{brief.systemRoutingAtAdmission?.routeClass ?? "Unavailable"}</dd><dd>{brief.systemRoutingAtAdmission?.reasons.join("; ")}</dd></div>
        <div><dt className="text-muted">Detection / Source</dt><dd>{alert.detectionTitle} · {alert.detectorName} / {alert.detectorSource}</dd></div>
        <div><dt className="text-muted">Classification at Admission</dt><dd>{classification?.status ?? "Unavailable"} · {classification?.attackCategory ?? (classification?.status === "informational_policy_signal" ? "Informational / policy signal" : "Not recorded")}</dd></div>
        <div><dt className="text-muted">Native severity / category</dt><dd>{alert.nativeSeverity} / {alert.detectionCategory ?? "Not recorded"}</dd></div>
        <div><dt className="text-muted">Priority at Creation</dt><dd>{snapshot.triage.priorityBand ?? "Unassigned"} / {snapshot.triage.operationalPriority ?? "Unassigned"}</dd></div>
        <div><dt className="text-muted">Network tuple</dt><dd>{alert.sourceIp}:{alert.sourcePort ?? "Unknown"} → {alert.destinationIp}:{alert.destinationPort ?? "Unknown"} / {alert.protocol}</dd></div>
        <div><dt className="text-muted">Primary event time</dt><dd>{alert.occurredAt}</dd></div>
      </dl>
      {classification && <details><summary className="cursor-pointer">Classification evidence and reasons at Admission</summary>
        <p>{classification.policyVersion} · {classification.source}</p>
        <ul className="list-inside list-disc">{classification.reasons.map(text => <li key={text}>{text}</li>)}</ul>
        {classification.conflictingCategories.length > 0 && <p>Conflicting categories: {classification.conflictingCategories.join(", ")}</p>}
        <ul className="list-inside list-disc">{classification.matches.map((match, index) => <li key={index}>{match.ruleId} · Signature {match.signatureId} · {match.field}: {match.value} · {match.category ?? "Informational"} · Record {match.sourceRecordRef}</li>)}</ul>
      </details>}
      {bundle ? <div className="space-y-2">
        <p>Sensor: {bundle.sensorId} · Capture: {bundle.captureScope ?? "Not recorded"}</p>
        <p>Evidence: {bundle.records.length} records · Types: {bundle.evidenceTypes.join(", ")}</p>
        <p>Primary record: {bundle.primaryRecordRef}</p>
        <p>Primary signature: {bundle.relatedSignatures.find(signature => signature.sourceRecordRef === bundle.primaryRecordRef)?.signature ?? "Not recorded"}</p>
        <p>Suricata signatures ({bundle.relatedSignatures.length})</p>
        <ul className="list-inside list-disc">{bundle.relatedSignatures.map(signature => <li key={signature.sourceRecordRef}>{signature.signatureId}: {signature.signature} · Native severity {signature.nativeSeverity} / {signature.nativeCategory}</li>)}</ul>
      </div> : <p>Suricata bundle not recorded. See immutable detector evidence below.</p>}
      <h3 className="font-semibold">Current Case and Human Context</h3>
      <p>Status: {brief.currentCaseStatus} · Revision: {brief.currentCaseRevision}</p>
      <p>Current Tier 1 Verdict: {verdict?.outcome.replaceAll("_", " ") ?? "Not recorded"}</p>
      <p className="text-xs text-muted">{brief.tier1VerdictExplanation}</p>
      {verdict && <p>{verdict.reason} · {verdict.actorName} · {verdict.createdAt} · Verdict revision {verdict.revision}</p>}
      <details><summary className="cursor-pointer">Current trusted context and provenance</summary><TrustedContextPanel context={brief.currentTrustedContext} /></details>
      <h3 className="font-semibold">Uncertainty and Evidence Limitations</h3>
      <ul className="list-inside list-disc space-y-1">{brief.uncertainties.map(text => <li key={text}>{text}</li>)}</ul>
    </section>
    <section aria-label="Potentially Related Alerts" className="space-y-3 border-t border-border pt-4">
      <h2 className="text-base font-semibold">Potentially Related Alerts</h2>
      <p className="text-xs text-muted">Within ±{correlationWindowHours} hours of the primary event; at most {maximumRelated}. Relationships suggest review and do not confirm an incident or campaign.</p>
      {relatedAlerts.length === 0 && <p>No eligible related alerts in this window.</p>}
      {relatedAlerts.map(alert => <article key={alert.operationalAlertRef} className="min-w-0 space-y-2 border-b border-border pb-3">
        <Link className="text-accent underline" to={`${prefix}/v2-triage?alertRef=${alert.operationalAlertRef}`}>{alert.title}</Link>
        <p>{alert.sourceIp} → {alert.destinationIp} · {alert.occurredAt}</p>
        <p>{alert.attackCategory ?? "Informational / policy signal"} · {alert.priorityBand ?? "Unassigned"} / {alert.operationalPriority ?? "Unassigned"} · {alert.handlingRoute}</p>
        <ul className="list-inside list-disc">{alert.relationshipReasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        {onSelect && <button className={button} onClick={() => onSelect(alert.operationalAlertRef)}>Review link to Case</button>}
      </article>)}
    </section>
    <section aria-label="Suggested Investigation Steps" className="space-y-3 border-t border-border pt-4">
      <h2 className="text-base font-semibold">Suggested Investigation Steps</h2>
      <p className="text-xs text-muted">Rule-based suggestions for human review; none of these steps has been executed by assistance.</p>
      <ol className="list-inside list-decimal space-y-2">{suggestedSteps.map(text => <li key={text}>{text}</li>)}</ol>
    </section>
  </section>;
}
