/**
 * Every verdict recorded, newest first (plan step S12).
 *
 * This is the audit trail read back as a work list: the API's `FEEDBACK` entries, each naming the
 * alert it belongs to. The alert is linked by the first eight characters of its reference — an audit
 * entry carries the public `alertRef` but not the flow's `sourceRecordId`, and inventing a short name
 * here would be the one thing this page must not do.
 */

import { Link } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, PageHeader } from "../../components/ui";
import { formatDateTime } from "../../design/format";
import { categoryLabel } from "../../features/feedback/categories";

type AuditEntry = Schemas["AuditEntryOut"];

const REF_PREFIX_LENGTH = 8;

function verdictOf(entry: AuditEntry): string {
  const category = entry.details?.["category"];
  return typeof category === "string" ? categoryLabel(category) : "—";
}

function analystOf(entry: AuditEntry): string {
  return entry.actor.displayName ?? entry.actor.role ?? "system";
}

export function InvestigationsPage() {
  const entries = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/audit-log", {
          params: { query: { eventType: ["FEEDBACK"], limit: 100 } },
          signal,
        }),
      ),
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Investigations"
        subtitle="Every verdict recorded, newest first. Open an alert to read its notes and the full adjustment chain."
      />

      <Card>
        <ApiView
          resource={entries}
          isEmpty={(data) => data.items.length === 0}
          empty={<EmptyState title="No verdicts recorded yet" />}
        >
          {(data) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-muted">
                    <th scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                      When
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Analyst
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Alert
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Verdict
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((entry) => (
                    <tr key={entry.eventId} className="border-t border-border">
                      <td className="whitespace-nowrap px-3 py-2 text-muted">
                        {formatDateTime(entry.createdAt)}
                      </td>
                      <td className="px-3 py-2 text-text">{analystOf(entry)}</td>
                      <td className="px-3 py-2">
                        {entry.alertRef === null ? (
                          <span className="text-dim">—</span>
                        ) : (
                          <Link
                            to={`/analyst/alerts/${entry.alertRef}`}
                            className="font-mono text-accent hover:text-text"
                          >
                            {entry.alertRef.slice(0, REF_PREFIX_LENGTH)}
                          </Link>
                        )}
                      </td>
                      <td className="px-3 py-2 text-text">{verdictOf(entry)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ApiView>
      </Card>
    </div>
  );
}
