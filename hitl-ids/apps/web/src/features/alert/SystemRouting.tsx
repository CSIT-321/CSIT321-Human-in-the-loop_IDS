import type { Schemas } from "../../api/client";
import { KeyValues } from "../../components/ui";

export const attackLabel = (category: string | null) => category === "unknown_needs_expert" ? "Unknown / Needs Expert" : category?.replaceAll("_", " ") ?? "Informational / Policy Signal";
export const routeClassLabel = (value: string) => ({ ROUTINE_REVIEW: "Routine Review", CRITICAL_ESCALATION: "Critical Escalation", EXPERT_REVIEW_REQUIRED: "Expert Review Required" }[value] ?? value);
export const currentRouteLabel = (value: string) => value === "tier1_review" ? "Tier 1" : value === "tier2_case" ? "Tier 2" : value.replaceAll("_", " ");

export const routingSummaryLabel = (view: Schemas["RoutingView"]) =>
  view.state.decisionSource === "analyst" && view.state.handlingRoute === "tier2_case" ? "Manual Escalation / Override"
    : view.systemRouting ? routeClassLabel(view.systemRouting.routeClass) : "Historical routing";

export function SystemRouting({ view }: { view: Schemas["RoutingView"] }) {
  const decision = view.systemRouting;
  const classification = view.classification;
  return <section aria-label="System Routing" className="space-y-3">
    <h3 className="label-mono">System Routing</h3>
    <KeyValues rows={[
      ["Current Route", currentRouteLabel(view.state.handlingRoute)],
      ["Route Class", routingSummaryLabel(view)],
      ["Decision Source", view.state.decisionSource === "analyst" ? "Analyst — manual override" : decision ? "System Policy" : view.state.decisionSource.replaceAll("_", " ")],
      ["Routing Policy Version", decision?.policyVersion ?? "Historical record; system routing not applied"],
    ]} />
    {view.state.decisionSource === "analyst" && decision && <p className="text-xs text-muted">Initial system route: {currentRouteLabel(decision.route)} ({routeClassLabel(decision.routeClass)}). The analyst override is recorded separately.</p>}
    {decision && <ul aria-label="Routing Reasons" className="space-y-2 text-sm">{decision.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
    {classification && <details className="text-xs"><summary className="cursor-pointer text-accent">Classification basis</summary>
      <p className="mt-2">{classification.status} · {classification.source.replaceAll("_", " ")} · {classification.policyVersion}</p>
      <ul className="mt-2 space-y-1">{classification.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    </details>}
  </section>;
}
