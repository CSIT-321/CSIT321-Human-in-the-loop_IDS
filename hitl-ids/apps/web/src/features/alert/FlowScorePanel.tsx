import type { ReactNode } from "react";

import { api, unwrap } from "../../api/client";
import { useApi, type ApiResource } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import { BandBadge, Card, EVIDENCE_LABEL, KeyValues, ScorePair, SeverityBadge } from "../../components/ui";
import { formatPercent } from "../../design/format";
import { ScoreAdjustmentChain } from "../feedback/ScoreAdjustmentChain";
import { FamilyPanelCard } from "./FamilyPanelCard";
import { FeedbackHistoryCard } from "./FeedbackHistoryCard";
import { FlowPanelCard } from "./FlowPanelCard";

/** C5 (decision Q6, layout approved 2026-11-08): the approved console's flow and score cards, read only, for a flow
 *  alert. A flow alert's operational ref IS its legacy alert_ref, so the approved GETs take the same ref. Verdicts still
 *  go through the one Analyst Verdict form (D2); this tab has no write control. Each card loads on its own, so one
 *  failing GET never hides the others. */
export function FlowScorePanel({ alertRef }: { alertRef: string }) {
  const path = { params: { path: { alertRef } } };
  const detail = useApi(signal => unwrap(api.GET("/api/alerts/{alertRef}", { ...path, signal })), [alertRef]);
  const adjustment = useApi(signal => unwrap(api.GET("/api/alerts/{alertRef}/score-adjustment", { ...path, signal })), [alertRef]);
  const history = useApi(signal => unwrap(api.GET("/api/alerts/{alertRef}/feedback-history", { ...path, signal })), [alertRef]);

  return <section aria-label="Flow and score" className="space-y-4">
    <Part resource={adjustment}>{data => <Card title="Score adjustment"><ScoreAdjustmentChain adjustment={data} /></Card>}</Part>
    <Part resource={detail}>{data => <>
      <Card title="Score and band">
        <KeyValues rows={[
          ["Operational score", <ScorePair detection={data.alert.detectionScore} combined={data.alert.combinedScore} />],
          ["Severity", <SeverityBadge severity={data.alert.severity} />],
          ["Queue band", <BandBadge queueClass={data.alert.queueClass} />],
          ["Fusion scheme", `${EVIDENCE_LABEL[data.alert.evidenceClass]} · confidence ${formatPercent(data.alert.confidence)}`],
        ]} />
      </Card>
      <FlowPanelCard flow={data.flow} />
      <FamilyPanelCard family={data.family} />
    </>}</Part>
    <Part resource={history}>{data => <FeedbackHistoryCard history={data} />}</Part>
  </section>;
}

function Part<T>({ resource, children }: { resource: ApiResource<T>; children: (data: T) => ReactNode }) {
  if (resource.status === "loading") return <LoadingState />;
  if (resource.status === "error") return <ErrorState error={resource.error} onRetry={resource.reload} />;
  return <>{children(resource.data)}</>;
}
