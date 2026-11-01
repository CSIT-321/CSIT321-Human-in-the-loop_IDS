import type { Schemas } from "../../api/client";

export const reviewLabels = {
  must_review: "Human Review Required",
  recommended_review: "Recommended Review",
  no_immediate_review: "No Immediate Review",
};
export const reviewLabel = (view: Schemas["RoutingView"]) => reviewLabels[view.effectiveReview?.disposition ?? "must_review"];
export const needsReview = (view: Schemas["RoutingView"]) => view.effectiveReview?.reviewRequired ?? true;
export function reviewProjection(view: Schemas["ReviewView"]): Schemas["EffectiveReview"] {
  return { disposition: view.disposition, reviewRequired: view.disposition !== "no_immediate_review",
    reasonCodes: view.reasonCodes, explanation: view.explanation, recalled: view.recalled, version: view.version };
}
