/**
 * The analyst's working list (plan step S12).
 *
 * Two rules shape this page:
 *
 * 1. **The API ranks, this page does not.** `sort=queue` is the contract order (band first, then
 *    operational score). Rows are rendered in the order they arrive; a client-side re-sort would
 *    silently disagree with the ranking the evaluation measured.
 * 2. **The view lives in the URL.** Every filter, the sort and the page offset are search params, so a
 *    refresh, a Back, or a pasted link all restore exactly what the analyst was looking at.
 */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import type { paths } from "../../api/schema";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import {
  BandBadge,
  Card,
  EVIDENCE_LABEL,
  EvidenceBadge,
  PageHeader,
  Pill,
  ScorePair,
  SeverityBadge,
} from "../../components/ui";
import { QUEUE_BANDS } from "../../design/bands";
import { formatNumber, formatScore } from "../../design/format";

type AlertSummary = Schemas["AlertSummary"];
type QueueClass = AlertSummary["queueClass"];
type EvidenceClass = AlertSummary["evidenceClass"];
type Severity = AlertSummary["severity"];
type AttackCategory = NonNullable<AlertSummary["attackCategory"]>;
type SortKey = NonNullable<NonNullable<paths["/api/alerts"]["get"]["parameters"]["query"]>["sort"]>;
type Direction = NonNullable<
  NonNullable<paths["/api/alerts"]["get"]["parameters"]["query"]>["direction"]
>;

const PAGE_SIZE = 50;

const QUEUE_KEYS: readonly QueueClass[] = QUEUE_BANDS.map((band) => band.key);
const EVIDENCE_KEYS: readonly EvidenceClass[] = [
  "corroborated",
  "signature_override",
  "ml_only",
  "none",
];
const SEVERITIES: readonly Severity[] = ["Critical", "High", "Medium", "Low", "Informational"];
const ATTACK_CATEGORIES: readonly AttackCategory[] = [
  "Botnet",
  "Brute Force",
  "DDoS",
  "DoS",
  "Infiltration",
  "Port Scan",
  "Web Attack",
];

const SORTS: readonly { readonly value: SortKey; readonly label: string }[] = [
  { value: "queue", label: "Queue order" },
  { value: "combined_score", label: "Operational score" },
  { value: "detection_score", label: "Detection score" },
  { value: "created_at", label: "Newest" },
  { value: "severity", label: "Severity" },
  { value: "evidence", label: "Evidence" },
];

const DIRECTIONS: readonly { readonly value: Direction; readonly label: string }[] = [
  { value: "desc", label: "Descending" },
  { value: "asc", label: "Ascending" },
];

type VerdictCategory = NonNullable<
  NonNullable<paths["/api/alerts"]["get"]["parameters"]["query"]>["verdict"]
>[number];

/**
 * The "Judged" control: what an analyst has said about an alert, in the industry's own words.
 *
 * `unjudged` is not a verdict, it is the absence of one, so it travels as its own query parameter —
 * the API's `verdict` filter asks about the verdict currently *in force*, which by definition no
 * unjudged alert has. The two are complements, and the row's "Verdict recorded" pill reads the same
 * condition, so a filter and its pill can never disagree.
 */
const JUDGED: readonly { readonly value: string; readonly label: string }[] = [
  { value: "any", label: "Any" },
  { value: "confirm_true_positive", label: "True Positive" },
  { value: "mark_false_positive", label: "False Positive" },
  { value: "mark_expected_activity", label: "Benign Positive" },
  { value: "escalate", label: "Escalated to Tier 2" },
  { value: "needs_investigation", label: "Needs investigation" },
  { value: "unjudged", label: "Not yet judged" },
];

/**
 * Detection-score ceilings. "Below 100" is the demo's saturation filter: 975 of the 996 flagged
 * alerts sit at exactly 100.0, where a confirming verdict clamps and nothing visibly moves. The
 * 99.999 bound (not 99.9) catches the alerts at 99.96–99.99 too — only an exact 100.0 is saturated.
 */
const DETECTION_CEILINGS: readonly { readonly value: string; readonly label: string }[] = [
  { value: "99.999", label: "Below 100 — not saturated" },
  { value: "90", label: "Below 90" },
  { value: "50", label: "Below 50" },
];

/** Narrow a raw search param to one of the values the contract accepts. Null means "no filter". */
function oneOf<T extends string>(options: readonly T[], value: string | null): T | null {
  if (value === null) return null;
  for (const option of options) {
    if (option === value) return option;
  }
  return null;
}

/** What the Rule column shows when no rule fired: an ML-only alert says so; an unflagged one is just empty. */
function ruleText(alert: AlertSummary): string {
  const rules = alert.matchedRuleIds ?? [];
  if (rules.length > 0) return rules.join(", ");
  return alert.evidenceClass === "ml_only" ? "no rule matched (model only)" : "—";
}

function FilterField({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-xs text-muted">
        {label}
      </label>
      {children}
    </div>
  );
}

const CONTROL =
  "rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text placeholder:text-dim";

export function QueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const searchTerm = searchParams.get("search") ?? "";
  const queueClass = oneOf(QUEUE_KEYS, searchParams.get("queueClass"));
  const evidenceClass = oneOf(EVIDENCE_KEYS, searchParams.get("evidenceClass"));
  const severity = oneOf(SEVERITIES, searchParams.get("severity"));
  const attackCategory = oneOf(ATTACK_CATEGORIES, searchParams.get("attackCategory"));
  const requiresReview = searchParams.get("requiresReview") === "true";
  const detectionMax = oneOf(DETECTION_CEILINGS.map((option) => option.value), searchParams.get("detectionMax"));
  const sort = oneOf(SORTS.map((option) => option.value), searchParams.get("sort")) ?? "queue";
  const direction = oneOf(DIRECTIONS.map((option) => option.value), searchParams.get("direction")) ?? "desc";
  const judged = oneOf(JUDGED.map((option) => option.value), searchParams.get("judged"));
  const judgedVerdict: VerdictCategory | null =
    judged === null || judged === "any" || judged === "unjudged"
      ? null
      : (judged as VerdictCategory);
  const offsetParam = Number.parseInt(searchParams.get("offset") ?? "0", 10);
  const offset = Number.isFinite(offsetParam) && offsetParam > 0 ? offsetParam : 0;

  const [draft, setDraft] = useState(searchTerm);
  useEffect(() => setDraft(searchTerm), [searchTerm]);

  function apply(changes: Readonly<Record<string, string | null>>, resetPage: boolean): void {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      if (resetPage) next.delete("offset");
      return next;
    });
  }

  function clearFilters(): void {
    setDraft("");
    setSearchParams(new URLSearchParams());
  }

  const alerts = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/alerts", {
          params: {
            query: {
              limit: PAGE_SIZE,
              offset,
              sort,
              direction,
              queueClass: queueClass === null ? null : [queueClass],
              evidenceClass: evidenceClass === null ? null : [evidenceClass],
              severity: severity === null ? null : [severity],
              attackCategory: attackCategory === null ? null : [attackCategory],
              requiresReview: requiresReview ? true : null,
              detectionMaxScore: detectionMax === null ? null : Number(detectionMax),
              verdict: judgedVerdict === null ? null : [judgedVerdict],
              unjudged: judged === "unjudged" ? true : null,
              search: searchTerm === "" ? null : searchTerm,
            },
          },
          signal,
        }),
      ),
    [searchTerm, queueClass, evidenceClass, severity, attackCategory, requiresReview, detectionMax, sort, direction, judged, judgedVerdict, offset],
  );

  const clearButton = (
    <button
      type="button"
      onClick={clearFilters}
      className="rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text hover:bg-surface"
    >
      Clear filters
    </button>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alert Queue"
        subtitle="Ranked by queue band, then operational score. The detection score never changes; the operational score is what analyst feedback moves."
      />

      <Card>
        <form
          role="search"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            apply({ search: draft.trim() === "" ? null : draft.trim() }, true);
          }}
          className="space-y-4"
        >
          <div className="flex flex-wrap items-end gap-3">
            <FilterField label="Search" htmlFor="queue-search">
              <input
                id="queue-search"
                type="search"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="AL-00478, an IP address or a rule id"
                className={`${CONTROL} w-72`}
              />
            </FilterField>
            <button
              type="submit"
              className="rounded-sm bg-primary px-4 py-1.5 text-sm font-semibold text-on-primary hover:bg-primary-hover"
            >
              Search
            </button>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <FilterField label="Band" htmlFor="queue-band">
              <select
                id="queue-band"
                value={queueClass ?? ""}
                onChange={(event) => apply({ queueClass: event.target.value }, true)}
                className={CONTROL}
              >
                <option value="">All bands</option>
                {QUEUE_BANDS.map((band) => (
                  <option key={band.key} value={band.key}>
                    {band.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Evidence" htmlFor="queue-evidence">
              <select
                id="queue-evidence"
                value={evidenceClass ?? ""}
                onChange={(event) => apply({ evidenceClass: event.target.value }, true)}
                className={CONTROL}
              >
                <option value="">All evidence</option>
                {EVIDENCE_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {EVIDENCE_LABEL[key]}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Severity" htmlFor="queue-severity">
              <select
                id="queue-severity"
                value={severity ?? ""}
                onChange={(event) => apply({ severity: event.target.value }, true)}
                className={CONTROL}
              >
                <option value="">All</option>
                {SEVERITIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Attack class" htmlFor="queue-attack-category">
              <select
                id="queue-attack-category"
                value={attackCategory ?? ""}
                onChange={(event) => apply({ attackCategory: event.target.value }, true)}
                className={CONTROL}
              >
                <option value="">All</option>
                {ATTACK_CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Detection score" htmlFor="queue-detection-max">
              <select
                id="queue-detection-max"
                value={detectionMax ?? ""}
                onChange={(event) => apply({ detectionMax: event.target.value === "" ? null : event.target.value }, true)}
                className={CONTROL}
              >
                <option value="">Any</option>
                {DETECTION_CEILINGS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <div className="flex items-center gap-2 pb-1.5">
              <input
                id="queue-requires-review"
                type="checkbox"
                checked={requiresReview}
                onChange={(event) => apply({ requiresReview: event.target.checked ? "true" : null }, true)}
                className="h-4 w-4 rounded border-border bg-raised"
              />
              <label htmlFor="queue-requires-review" className="text-sm text-text">
                Needs review only
              </label>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <FilterField label="Sort" htmlFor="queue-sort">
              <select
                id="queue-sort"
                value={sort}
                onChange={(event) =>
                  apply(
                    event.target.value === "queue"
                      ? { sort: null, direction: null } // the contract order carries no direction
                      : { sort: event.target.value },
                    true,
                  )
                }
                className={CONTROL}
              >
                {SORTS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Direction" htmlFor="queue-direction">
              <select
                id="queue-direction"
                value={direction}
                onChange={(event) =>
                  apply({ direction: event.target.value === "desc" ? null : event.target.value }, true)
                }
                disabled={sort === "queue"}
                title={sort === "queue"
                  ? "The queue order is the contract order — band first, then operational score — and has no direction. Choose an inspection sort (e.g. Detection score) to flip it."
                  : undefined}
                className={CONTROL}
              >
                {DIRECTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <FilterField label="Judged" htmlFor="queue-judged">
              <select
                id="queue-judged"
                value={judged ?? "any"}
                onChange={(event) =>
                  apply({ judged: event.target.value === "any" ? null : event.target.value }, true)
                }
                title="What the analyst said. 'Not yet judged' is the absence of a verdict, so it is its own filter."
                className={CONTROL}
              >
                {JUDGED.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>

            <div className="pb-1">{clearButton}</div>
          </div>
        </form>
      </Card>

      <ApiView
        resource={alerts}
        isEmpty={(data) => data.items.length === 0}
        empty={<EmptyState title="No alerts match these filters" hint={clearButton} />}
      >
        {(data) => {
          const first = data.page.total === 0 ? 0 : data.page.offset + 1;
          const last = data.page.total === 0 ? 0 : data.page.offset + data.page.returned;

          return (
            <div className="space-y-4">
              <Card className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-muted">
                      {["Rank", "Alert", "Band", "Evidence", "Severity", "Detection", "Operational", "Class", "Flow", "Rule"].map(
                        (heading) => (
                          <th key={heading} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                            {heading}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((alert, index) => (
                      <tr key={alert.alertRef} className="border-t border-border align-top">
                        <td className="px-3 py-2 font-mono tabular-nums text-muted">
                          {formatNumber(data.page.offset + index + 1)}
                        </td>
                        <td className="px-3 py-2">
                          <span className="flex flex-wrap items-center gap-2">
                            <Link
                              to={`/analyst/alerts/${alert.alertRef}`}
                              className="font-mono text-accent hover:text-text"
                            >
                              {alert.sourceRecordId}
                            </Link>
                            {alert.hasFeedback && <Pill tone="ok">Verdict recorded</Pill>}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <BandBadge queueClass={alert.queueClass} />
                        </td>
                        <td className="px-3 py-2">
                          <EvidenceBadge evidenceClass={alert.evidenceClass} />
                        </td>
                        <td className="px-3 py-2">
                          <SeverityBadge severity={alert.severity} />
                        </td>
                        <td className="px-3 py-2 font-mono tabular-nums text-text">
                          {formatScore(alert.detectionScore)}
                        </td>
                        <td className="px-3 py-2">
                          <ScorePair detection={alert.detectionScore} combined={alert.combinedScore} />
                        </td>
                        <td className="px-3 py-2 text-text">{alert.attackCategory ?? "—"}</td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                          {`${alert.srcIp} → ${alert.dstIp}:${alert.dstPort}/${alert.protocol}`}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted">{ruleText(alert)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted">
                  {`Showing ${formatNumber(first)}–${formatNumber(last)} of ${formatNumber(data.page.total)}`}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={data.page.offset === 0}
                    onClick={() => apply({ offset: offset - PAGE_SIZE > 0 ? String(offset - PAGE_SIZE) : null }, false)}
                    className="rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={data.page.offset + data.page.returned >= data.page.total}
                    onClick={() => apply({ offset: String(offset + PAGE_SIZE) }, false)}
                    className="rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          );
        }}
      </ApiView>
    </div>
  );
}
