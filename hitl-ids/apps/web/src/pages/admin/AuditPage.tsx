/**
 * S13 — the whole audit trail, newest first, filtered and exportable.
 *
 * The table is deliberately the plain one: every column is a field of `AuditEntryOut` and the
 * `details` blob is folded into a disclosure rather than into columns, because the API promises no
 * shape per event type. The trail's own guarantee — `UPDATE` and `DELETE` raise at the database
 * (NFR-02/03) — is what the subtitle says, so nobody reads the filter row as an edit row.
 *
 * Filters live in the URL, so a filtered view can be linked, reloaded and handed over. The export
 * re-reads every page the filters match rather than exporting the visible hundred: a CSV that
 * silently stopped at the page boundary would be the kind of half-truth the trail exists to prevent.
 *
 * The filter row is a toolbar rather than a panel — it is the table's controls, not a report — and
 * the event type is a pill, so the trail can be sorted by kind at a glance. The pill's colour is an
 * aid to that scan and never the only carrier: the humanised word inside it says what happened.
 */

import { useState } from "react";
import { useSearchParams } from "react-router";

import { ApiError, CLIENT_ERROR, api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState, ErrorState } from "../../components/states";
import { Card, PageHeader, Pill, type Tone } from "../../components/ui";
import { formatDateTime, formatNumber, humanise } from "../../design/format";
import {
  CSV_HEADER,
  EVENT_TYPES,
  asEventType,
  auditCsv,
  auditQuery,
  dayEnd,
  dayStart,
  shortAlertRef,
  type AuditEntry,
} from "../../features/admin/audit";

const PAGE_SIZE = 100;
/** The API's own maximum page size, used for the export walk so it needs as few requests as possible. */
const EXPORT_PAGE_SIZE = 500;

const CONTROL_CLASS = "rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text";
/** The console's one primary button, as the verdict form's "Record verdict" draws it. */
const PRIMARY_CLASS =
  "rounded-sm bg-primary px-4 py-1.5 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40";
const LABEL_CLASS = "block text-xs text-dim";
const TH_CLASS = "px-2 py-1.5 font-medium";
const TD_CLASS = "px-2 py-1.5 text-text";

/**
 * The trail's kinds, coloured. Anything the contract adds later falls through to `muted`, so an
 * unrecognised event still renders — with its own humanised name, which is the part that matters.
 */
const EVENT_TONE: Partial<Record<AuditEntry["eventType"], Tone>> = {
  FEEDBACK: "accent",
  FEEDBACK_AMEND: "accent",
  GUARDRAIL_INTERVENTION: "warn",
  GUARDRAIL_REJECTION: "danger",
  SIMILAR_ALERT_LEARNING: "violet",
  CONFIG_CHANGE: "stub",
};

function asApiError(cause: unknown): ApiError {
  return cause instanceof ApiError
    ? cause
    : new ApiError(0, { code: CLIENT_ERROR.unexpected, message: String(cause) });
}

/** Every entry the current filters match, walked in full pages of 500. */
async function collectEntries(query: ReturnType<typeof auditQuery>): Promise<readonly AuditEntry[]> {
  const entries: AuditEntry[] = [];
  let offset = 0;
  for (;;) {
    const page = await unwrap(
      api.GET("/api/audit-log", { params: { query: { ...query, limit: EXPORT_PAGE_SIZE, offset } } }),
    );
    entries.push(...page.items);
    if (page.items.length === 0 || entries.length >= page.page.total) return entries;
    offset += page.items.length;
  }
}

function DetailsCell({ entry }: { entry: AuditEntry }) {
  if (entry.details === null) return <span className="text-dim">—</span>;
  return (
    <details>
      <summary className="cursor-pointer text-accent">View</summary>
      <pre className="mt-2 max-w-md overflow-x-auto rounded-sm bg-raised p-2 font-mono text-xs text-muted">
        {JSON.stringify(entry.details, null, 2)}
      </pre>
    </details>
  );
}

function EntryTable({ entries }: { entries: readonly AuditEntry[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-dim">
            <th scope="col" className={TH_CLASS}>
              When
            </th>
            <th scope="col" className={TH_CLASS}>
              Event
            </th>
            <th scope="col" className={TH_CLASS}>
              Actor
            </th>
            <th scope="col" className={TH_CLASS}>
              Alert
            </th>
            <th scope="col" className={TH_CLASS}>
              Rationale
            </th>
            <th scope="col" className={TH_CLASS}>
              Details
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.eventId} className="border-t border-border align-top">
              <td className={`${TD_CLASS} whitespace-nowrap font-mono text-muted`}>
                {formatDateTime(entry.createdAt)}
              </td>
              <td className={`${TD_CLASS} whitespace-nowrap`}>
                <Pill tone={EVENT_TONE[entry.eventType] ?? "muted"}>{humanise(entry.eventType)}</Pill>
              </td>
              <td className={TD_CLASS}>{entry.actor.displayName ?? entry.actor.role ?? "system"}</td>
              <td className={`${TD_CLASS} font-mono`}>{shortAlertRef(entry.alertRef)}</td>
              <td className={`${TD_CLASS} text-muted`}>{entry.rationale ?? "—"}</td>
              <td className={TD_CLASS}>
                <DetailsCell entry={entry} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const eventType = asEventType(params.get("eventType") ?? "");
  const since = params.get("since") ?? "";
  const until = params.get("until") ?? "";
  const [offset, setOffset] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<ApiError | null>(null);

  const query = auditQuery({ eventType, since: dayStart(since), until: dayEnd(until) }, PAGE_SIZE, offset);
  const audit = useApi(
    (signal) => unwrap(api.GET("/api/audit-log", { params: { query }, signal })),
    [eventType, since, until, offset],
  );

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value === "") next.delete(name);
    else next.set(name, value);
    setOffset(0);
    setExportError(null);
    setParams(next);
  }

  function clearFilters() {
    setOffset(0);
    setExportError(null);
    setParams(new URLSearchParams());
  }

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const csv = auditCsv(await collectEntries(query));
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "audit-log.csv";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setExportError(asApiError(cause));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Audit Trail"
        subtitle="Every run, verdict, guardrail action, family-learning event and configuration change, newest first. The database refuses UPDATE and DELETE on this table."
      />

      <div className="rounded-sm border border-border bg-surface px-4 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label htmlFor="audit-event-type" className={LABEL_CLASS}>
              Event type
            </label>
            <select
              id="audit-event-type"
              value={eventType ?? ""}
              onChange={(event) => setFilter("eventType", event.target.value)}
              className={CONTROL_CLASS}
            >
              <option value="">All events</option>
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanise(type)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-since" className={LABEL_CLASS}>
              From
            </label>
            <input
              id="audit-since"
              type="date"
              value={since}
              onChange={(event) => setFilter("since", event.target.value)}
              className={CONTROL_CLASS}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-until" className={LABEL_CLASS}>
              To
            </label>
            <input
              id="audit-until"
              type="date"
              value={until}
              onChange={(event) => setFilter("until", event.target.value)}
              className={CONTROL_CLASS}
            />
          </div>
          <button type="button" onClick={clearFilters} className={CONTROL_CLASS}>
            Clear filters
          </button>
          <button type="button" onClick={exportCsv} disabled={exporting} className={`${PRIMARY_CLASS} ml-auto`}>
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
        <p className="mt-2 text-xs text-dim">
          The export carries every entry these filters match, as {CSV_HEADER}.
        </p>
      </div>

      {exportError !== null && <ErrorState error={exportError} />}

      <Card title="Entries" subtitle="Newest first, 100 per page.">
        <ApiView
          resource={audit}
          isEmpty={(data) => data.items.length === 0}
          empty={<EmptyState title="No audit entries match these filters" />}
        >
          {(data) => {
            const shownTo = data.page.offset + data.page.returned;
            return (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-[13px] text-muted">
                    Showing {data.page.offset + 1}–{shownTo} of {formatNumber(data.page.total)}
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={data.page.offset === 0}
                      onClick={() => setOffset(Math.max(0, data.page.offset - PAGE_SIZE))}
                      className={`${CONTROL_CLASS} disabled:opacity-50`}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={shownTo >= data.page.total}
                      onClick={() => setOffset(data.page.offset + PAGE_SIZE)}
                      className={`${CONTROL_CLASS} disabled:opacity-50`}
                    >
                      Next
                    </button>
                  </div>
                </div>
                <EntryTable entries={data.items} />
              </div>
            );
          }}
        </ApiView>
      </Card>
    </div>
  );
}
