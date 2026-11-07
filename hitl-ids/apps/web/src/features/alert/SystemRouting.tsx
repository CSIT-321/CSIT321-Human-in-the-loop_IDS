import type { Schemas } from "../../api/client";
import { KeyValues } from "../../components/ui";

export const attackLabel = (category: string | null) => category === "unknown_needs_expert" ? "Unknown / Needs Expert" : category?.replaceAll("_", " ") ?? "Informational / Policy Signal";
export const routeClassLabel = (value: string) => ({ ROUTINE_REVIEW: "Routine Review", CRITICAL_ESCALATION: "Critical Escalation", EXPERT_REVIEW_REQUIRED: "Expert Review Required" }[value] ?? value);
export const currentRouteLabel = (value: string) => value === "tier1_review" ? "Tier 1" : value === "tier2_case" ? "Tier 2" : value === "tier2_candidate" ? "Historical routing record" : value.replaceAll("_", " ");

export const routingSummaryLabel = (view: Schemas["RoutingView"]) =>
  view.state.decisionSource === "analyst" && view.state.handlingRoute === "tier2_case" ? "Manual Escalation / Override"
    : view.systemRouting ? routeClassLabel(view.systemRouting.routeClass) : "Historical routing";

export function SystemRouting({ view }: { view: Schemas["RoutingView"] }) {
  const decision = view.systemRouting;
  const classification = view.classification;
  const candidateReasons = view.state.tier2RecommendationReasons ?? [];
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
    {decision && candidateReasons.length > 0 && <section aria-label="Tier 2 candidate reasons" className="space-y-1">
      <h4 className="text-sm font-semibold">Why Tier 2 is recommended</h4>
      <ul className="space-y-1 text-sm">{candidateReasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    </section>}
    {decision && <p className="text-xs text-muted">Context is read once, when the alert is routed. A fact recorded later does not change this recommendation.</p>}
    {classification && <details className="text-xs"><summary className="cursor-pointer text-accent">Classification basis</summary>
      <p className="mt-2">{classification.status} · {classification.source.replaceAll("_", " ")} · {classification.policyVersion}</p>
      <ul className="mt-2 space-y-1">{classification.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    </details>}
  </section>;
}
