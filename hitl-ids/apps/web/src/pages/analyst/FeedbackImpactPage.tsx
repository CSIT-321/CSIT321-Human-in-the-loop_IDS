/**
 * What verdicts did to the queue (plan step S12).
 *
 * Three headline counts, then the two things that actually moved rows: similar-alert learning and the
 * guardrails. Both are read from the audit trail rather than recomputed, because the audit trail is
 * the record and the count is a summary of it.
 *
 * The caution paragraph is not boilerplate. The recorded evaluation found that family learning
 * promoted a *benign* alert to rank 1 alongside the confirmed attacks in its family, and a screen that
 * showed only the promotions would hide the one result the evaluator is looking for.
 */

import { Link } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";
import { formatDateTime, formatNumber, humanise } from "../../design/format";

type AuditEntry = Schemas["AuditEntryOut"];
type Details = { [key: string]: unknown };

const REF_PREFIX_LENGTH = 8;

function stringDetail(details: Details | null, key: string): string | null {
  const value = details?.[key];
  return typeof value === "string" ? value : null;
}

function numberDetail(details: Details | null, key: string): number | null {
  const value = details?.[key];
  return typeof value === "number" ? value : null;
}

/** A guardrail entry carries `{ outcome: { interventions: [{ explanation }] } }`. */
function interventionExplanations(details: Details | null): readonly string[] {
  const outcome = details?.["outcome"];
  if (typeof outcome !== "object" || outcome === null) return [];
  const interventions: unknown = "interventions" in outcome ? outcome.interventions : undefined;
  if (!Array.isArray(interventions)) return [];
  const items: readonly unknown[] = interventions;
  return items.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const explanation: unknown = "explanation" in item ? item.explanation : undefined;
    return typeof explanation === "string" ? [explanation] : [];
  });
}

function AlertLink({ alertRef }: { alertRef: string | null }) {
  if (alertRef === null) return <span className="text-dim">—</span>;
  return (
    <Link to={`/analyst/alerts/${alertRef}`} className="font-mono text-accent hover:text-text">
      {alertRef.slice(0, REF_PREFIX_LENGTH)}
    </Link>
  );
}

function When({ iso }: { iso: string }) {
  return <td className="whitespace-nowrap px-3 py-2 text-muted">{formatDateTime(iso)}</td>;
}

function Headings({ labels }: { labels: readonly string[] }) {
  return (
    <thead>
      <tr className="text-muted">
        {labels.map((label) => (
          <th key={label} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
            {label}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-sm border border-border bg-surface p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-text tabular-nums">{formatNumber(value)}</p>
    </div>
  );
}

function LearningTable({ entries }: { entries: readonly AuditEntry[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <Headings labels={["When", "Family", "Members moved", "Alert"]} />
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.eventId} className="border-t border-border">
              <When iso={entry.createdAt} />
              <td className="px-3 py-2 font-mono text-xs text-text">
                {stringDetail(entry.details, "family_key") ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono tabular-nums text-text">
                {numberDetail(entry.details, "members_moved") ?? "—"}
              </td>
              <td className="px-3 py-2">
                <AlertLink alertRef={entry.alertRef} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GuardrailTable({ entries }: { entries: readonly AuditEntry[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <Headings labels={["When", "Event", "Alert", "What happened"]} />
        <tbody>
          {entries.map((entry) => {
            const explanations = interventionExplanations(entry.details);
            return (
              <tr key={entry.eventId} className="border-t border-border align-top">
                <When iso={entry.createdAt} />
                <td className="whitespace-nowrap px-3 py-2 text-text">{humanise(entry.eventType)}</td>
                <td className="px-3 py-2">
                  <AlertLink alertRef={entry.alertRef} />
                </td>
                <td className="px-3 py-2 text-muted">
                  {explanations.length === 0 ? (
                    "—"
                  ) : (
                    <ul className="space-y-1">
                      {explanations.map((explanation, index) => (
                        <li key={`${entry.eventId}-${index}`}>{explanation}</li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function FeedbackImpactPage() {
  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), []);
  const learning = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/audit-log", {
          params: { query: { eventType: ["SIMILAR_ALERT_LEARNING"], limit: 50 } },
          signal,
        }),
      ),
    [],
  );
  const guardrails = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/audit-log", {
          params: {
            query: { eventType: ["GUARDRAIL_INTERVENTION", "GUARDRAIL_REJECTION"], limit: 50 },
          },
          signal,
        }),
      ),
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Feedback Impact"
        subtitle="What analyst verdicts changed in the queue, and what the guardrails stopped."
      />

      <ApiView resource={summary}>
        {(data) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Kpi label="Verdicts recorded" value={data.feedbackEvents} />
            <Kpi label="Alerts moved by feedback" value={data.alertsMovedByFeedback} />
            <Kpi label="Guardrail interventions" value={data.guardrailInterventions} />
          </div>
        )}
      </ApiView>

      <Card
        title="Similar-alert learning"
        subtitle="A verdict teaches the alerts that share its family, once enough of them agree."
      >
        <ApiView
          resource={learning}
          isEmpty={(data) => data.items.length === 0}
          empty={<EmptyState title="No family has learned from verdicts yet." />}
        >
          {(data) => <LearningTable entries={data.items} />}
        </ApiView>
      </Card>

      <Card title="Guardrail actions" subtitle="Where a guardrail bounded or refused a score change.">
        <ApiView
          resource={guardrails}
          isEmpty={(data) => data.items.length === 0}
          empty={<EmptyState title="No guardrail has acted yet." />}
        >
          {(data) => <GuardrailTable entries={data.items} />}
        </ApiView>
      </Card>

      <p className="text-sm text-muted">
        Families are a coarse key. In the recorded evaluation, learning promoted a benign alert to rank
        1 along with the confirmed attacks in its family — the evaluator view shows the measurement.
      </p>
    </div>
  );
}
