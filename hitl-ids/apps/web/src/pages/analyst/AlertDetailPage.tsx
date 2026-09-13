/**
 * One alert, in full (plan step S12 — the demo's centrepiece).
 *
 * The page reads three resources — the alert with its four evidence panels, its score-adjustment
 * chain, and its verdict history — and re-reads all three after a verdict is recorded.
 *
 * The refetch rule matters: `useLastGood` keeps the last successful value of each resource on screen
 * while a refresh is in flight. The verdict form holds the guardrail's outcome in its own state, and
 * replacing the page with a spinner would unmount it at exactly the moment the analyst is meant to
 * read it. Only a first load shows a spinner; only a first-load failure is an error.
 */

import { Link, useParams } from "react-router";
import { useState } from "react";

import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import {
  BandBadge,
  Card,
  EvidenceBadge,
  KeyValues,
  PageHeader,
  Pill,
  ScorePair,
  SeverityBadge,
} from "../../components/ui";
import { formatNumber, formatPercent, formatScore, humanise } from "../../design/format";
import { EvidencePanelCard } from "../../features/alert/EvidencePanelCard";
import { FamilyPanelCard } from "../../features/alert/FamilyPanelCard";
import { FeedbackHistoryCard } from "../../features/alert/FeedbackHistoryCard";
import { FlowPanelCard } from "../../features/alert/FlowPanelCard";
import { MlPanelCard } from "../../features/alert/MlPanelCard";
import { SignaturePanelCard } from "../../features/alert/SignaturePanelCard";
import { useLastGood } from "../../features/alert/useLastGood";
import { FeedbackPanel } from "../../features/feedback/FeedbackPanel";
import { ScoreAdjustmentChain } from "../../features/feedback/ScoreAdjustmentChain";

function BackToQueue() {
  return (
    <Link to="/analyst/queue" className="text-sm text-accent hover:text-text">
      ← Back to queue
    </Link>
  );
}

export function AlertDetailPage() {
  const params = useParams<{ alertRef: string }>();
  const alertRef = params.alertRef ?? "";
  const [version, setVersion] = useState(0);

  const detailResource = useApi(
    (signal) => unwrap(api.GET("/api/alerts/{alertRef}", { params: { path: { alertRef } }, signal })),
    [alertRef, version],
  );
  const adjustmentResource = useApi(
    (signal) =>
      unwrap(api.GET("/api/alerts/{alertRef}/score-adjustment", { params: { path: { alertRef } }, signal })),
    [alertRef, version],
  );
  const historyResource = useApi(
    (signal) =>
      unwrap(api.GET("/api/alerts/{alertRef}/feedback-history", { params: { path: { alertRef } }, signal })),
    [alertRef, version],
  );

  const detail = useLastGood(detailResource);
  const adjustment = useLastGood(adjustmentResource);
  const history = useLastGood(historyResource);

  if (detail === null) {
    return (
      <div className="space-y-6">
        <BackToQueue />
        {detailResource.status === "error" ? (
          <ErrorState error={detailResource.error} onRetry={detailResource.reload} />
        ) : (
          <LoadingState />
        )}
      </div>
    );
  }

  const alert = detail.alert;
  const refreshing =
    detailResource.status === "loading" ||
    adjustmentResource.status === "loading" ||
    historyResource.status === "loading";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <BackToQueue />
        {refreshing && (
          <span role="status" aria-live="polite" className="text-xs text-muted">
            Refreshing…
          </span>
        )}
      </div>

      <PageHeader
        title={alert.sourceRecordId}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <BandBadge queueClass={alert.queueClass} />
            <EvidenceBadge evidenceClass={alert.evidenceClass} />
            <SeverityBadge severity={alert.severity} />
            {detail.evidence.tier2Candidate && <Pill tone="danger">→ Tier 2 candidate</Pill>}
            <span className="font-mono text-xs text-dim">{alert.alertRef}</span>
          </span>
        }
      />

      <Card title="Scores">
        <KeyValues
          rows={[
            [
              "Detection score",
              <span className="font-mono tabular-nums">{formatScore(alert.detectionScore)}</span>,
            ],
            [
              "Operational score",
              <ScorePair detection={alert.detectionScore} combined={alert.combinedScore} />,
            ],
            ["Model confidence", formatPercent(alert.confidence)],
            ["Status", humanise(alert.status)],
            ["Needs review", alert.requiresReview ? "Yes" : "No"],
            ["Verdicts recorded", formatNumber(detail.feedbackCount)],
          ]}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <FlowPanelCard flow={detail.flow} />
        <SignaturePanelCard signature={detail.signature} />
        <MlPanelCard ml={detail.ml} />
        <EvidencePanelCard evidence={detail.evidence} />
      </div>

      <FamilyPanelCard family={detail.family} />

      <Card title="Score adjustment">
        {adjustment !== null ? (
          <ScoreAdjustmentChain adjustment={adjustment} />
        ) : adjustmentResource.status === "error" ? (
          <ErrorState error={adjustmentResource.error} onRetry={adjustmentResource.reload} />
        ) : (
          <LoadingState />
        )}
      </Card>

      <FeedbackPanel
        alertRef={alertRef}
        current={detail.currentFeedback}
        onRecorded={() => setVersion((previous) => previous + 1)}
      />

      {history !== null ? (
        <FeedbackHistoryCard history={history} />
      ) : (
        <Card title="Verdict history">
          {historyResource.status === "error" ? (
            <ErrorState error={historyResource.error} onRetry={historyResource.reload} />
          ) : (
            <LoadingState />
          )}
        </Card>
      )}
    </div>
  );
}
