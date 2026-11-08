/**
 * The verdict history (plan S12): append-only, oldest first.
 *
 * Feedback does not stack — a new verdict replaces the old one — so the card labels the last event
 * "In effect" and everything before it "Superseded" rather than summing the deltas. Every event keeps
 * its own requested/applied pair, which is how a reader sees a guardrail's effect after the fact.
 */

import type { Schemas } from "../../api/client";
import { EmptyState } from "../../components/states";
import { Card, Pill } from "../../components/ui";
import { formatDateTime, formatDelta } from "../../design/format";
import { categoryMeta } from "../feedback/categories";

type FeedbackHistory = Schemas["FeedbackHistory"];

export function FeedbackHistoryCard({ history }: { history: FeedbackHistory }) {
  const events = history.events ?? [];

  return (
    <Card title="Verdict history">
      {events.length === 0 ? (
        <EmptyState title="No verdicts recorded yet." />
      ) : (
        <ol className="space-y-3">
          {events.map((event, index) => {
            const inEffect = index === events.length - 1;
            return (
              <li key={event.feedbackRef} className="rounded-sm border border-border bg-raised p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-text">{categoryMeta(event.category).label}</span>
                  {inEffect ? <Pill tone="ok">In effect</Pill> : <Pill tone="muted">Superseded</Pill>}
                </div>
                <p className="mt-1 text-xs text-muted">
                  {formatDateTime(event.createdAt)} ·{" "}
                  {event.actor.displayName ?? event.actor.role ?? "unknown"}
                </p>
                {event.note !== null && <p className="mt-2 text-muted">{event.note}</p>}
                <p className="mt-2 font-mono text-xs text-muted">
                  {`requested ${formatDelta(event.adjustment.requestedDelta)} → applied ${formatDelta(event.adjustment.actualDelta)} (${event.adjustment.action})`}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
