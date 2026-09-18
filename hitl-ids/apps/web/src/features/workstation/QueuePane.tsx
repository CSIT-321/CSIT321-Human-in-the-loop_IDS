/**
 * The workstation's left column: band tabs, a search box, and the ranked alert list.
 *
 * The API ranks; this list renders rows in the order they arrive. Tabs select either queue/workflow
 * state or immutable detector evidence. Neither dimension is a severity filter.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi, type ApiResource } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import { formatNumber, formatScore, humanise } from "../../design/format";
import { categoryLabel } from "../feedback/categories";

type AlertSummary = Schemas["AlertSummary"];
type FamilyRow = Schemas["FamilyRow"];
type QueueClass = AlertSummary["queueClass"];
type EvidenceClass = AlertSummary["evidenceClass"];

interface AlertPage {
  readonly items: AlertSummary[];
  readonly page: Schemas["PageInfo"];
}

interface FamilyPage {
  readonly items: FamilyRow[];
  readonly page: Schemas["PageInfo"];
}

/**
 * How the queue is grouped. `none` is the ranked list an analyst works down; `family` folds it into
 * the groups similar-alert learning actually acts on.
 *
 * The grouping is not a second ranking: families are returned in the order of their best-ranked
 * member, so the same queue order governs both views.
 */
export type QueueGrouping = "none" | "family";

export interface QueueTab {
  readonly key: string;
  readonly label: string;
  readonly queueClass: QueueClass | null;
  readonly evidenceClass: EvidenceClass | null;
  readonly requiresReview: boolean;
}

export const QUEUE_TABS: readonly [QueueTab, ...QueueTab[]] = [
  { key: "all", label: "All", queueClass: null, evidenceClass: null, requiresReview: false },
  { key: "tier2", label: "Tier 2", queueClass: "tier2_candidate", evidenceClass: null, requiresReview: false },
  { key: "review", label: "Needs review", queueClass: null, evidenceClass: null, requiresReview: true },
  { key: "corroborated", label: "Rule + model", queueClass: null, evidenceClass: "corroborated", requiresReview: false },
  { key: "rule", label: "Rule only", queueClass: null, evidenceClass: "signature_override", requiresReview: false },
  { key: "model", label: "Model only", queueClass: null, evidenceClass: "ml_only", requiresReview: false },
  { key: "none", label: "Not flagged", queueClass: null, evidenceClass: "none", requiresReview: false },
];

/** The left edge of a card: the band's colour, so the list reads as bands even when scrolled. */
export const BAND_RULE: Record<QueueClass, string> = {
  tier2_candidate: "border-l-danger",
  corroborated: "border-l-violet",
  signature_override: "border-l-warn",
  ml_only: "border-l-accent",
  none: "border-l-border-strong",
};

const BAND_SHORT: Record<QueueClass, string> = {
  tier2_candidate: "TIER 2",
  corroborated: "RULE+MODEL",
  signature_override: "RULE",
  ml_only: "MODEL",
  none: "NOT FLAGGED",
};

const BAND_TEXT: Record<QueueClass, string> = {
  tier2_candidate: "text-danger",
  corroborated: "text-violet",
  signature_override: "text-warn",
  ml_only: "text-accent",
  none: "text-dim",
};

const SEVERITY_DOT: Record<AlertSummary["severity"], string> = {
  Critical: "bg-severity-critical",
  High: "bg-severity-high",
  Medium: "bg-severity-medium",
  Low: "bg-severity-low",
  Informational: "bg-dim",
};

/** "2018-02-14 12:40:02.383338" -> "2018-02-14 12:40:02". */
export function shortFlowTime(flowTime: string | null | undefined): string {
  return flowTime === null || flowTime === undefined ? "—" : flowTime.slice(0, 19);
}

function AlertCard({ alert, selected, onSelect }: { alert: AlertSummary; selected: boolean; onSelect: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  return (
    <li>
      <button
        ref={ref}
        type="button"
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
        className={`block w-full border-b border-l-2 border-b-border px-3 py-2.5 text-left transition-colors ${
          BAND_RULE[alert.queueClass]
        } ${selected ? "bg-raised" : "hover:bg-raised/50"}`}
      >
        <span className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5">
            <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[alert.severity]}`} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">
              {alert.severity === "Informational" ? "Info" : alert.severity}
            </span>
            <span className={`font-mono text-[10px] font-semibold tracking-wider ${BAND_TEXT[alert.queueClass]}`}>
              {BAND_SHORT[alert.queueClass]}
            </span>
          </span>
          <span className="font-mono text-[13px] font-semibold tabular-nums text-text">{formatScore(alert.combinedScore)}</span>
        </span>
        <span className="mt-1 flex items-baseline justify-between gap-2">
          <span className="truncate text-[13px] font-medium text-text">{alert.attackCategory ?? "No detection"}</span>
          <span className="shrink-0 font-mono text-[11px] text-accent">{alert.sourceRecordId}</span>
        </span>
        <span className="mt-1 block truncate font-mono text-[11px] text-muted">
          <span className="text-accent/90">{alert.srcIp}</span>
          {" → "}
          <span className="text-accent/90">{alert.dstIp}</span>
          <span className="text-severity-medium">:{alert.dstPort}</span>
          <span className="text-dim">/{alert.protocol}</span>
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-dim">
          <span>{shortFlowTime(alert.flowTime)}</span>
          {alert.status !== "new" && <span className="text-muted">· {humanise(alert.status)}</span>}
          {alert.hasFeedback && <span className="text-ok">· verdict</span>}
          {alert.owner !== null && alert.owner !== undefined && (
            <span className="text-muted">· {alert.owner.displayName ?? "owned"}</span>
          )}
          {alert.familySize > 1 && <span>· family {formatNumber(alert.familySize)}</span>}
        </span>
      </button>
    </li>
  );
}

/**
 * One family in the grouped queue: what it is, what it has learned, and its members on demand.
 *
 * The learning line is the reason this view exists. `applied` is what every unjudged member of the
 * family currently carries — the alerts no analyst has touched — so a family whose gate is open is
 * a family that has re-ranked alerts on its own. Closed and zero is the normal state and is shown
 * as plainly as an open one: the gate refusing to act on one verdict is the safety claim working.
 */
function FamilyGroup({
  row,
  expanded,
  onToggle,
  selectedRef,
  onSelect,
}: {
  row: FamilyRow;
  expanded: boolean;
  onToggle: () => void;
  selectedRef: string | null;
  onSelect: (alertRef: string) => void;
}) {
  const applied = row.appliedAdjustment !== 0 || row.appliedOffset !== 0;
  return (
    <li className={`border-b border-border border-l-2 ${BAND_RULE[row.bestQueueClass]}`}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-raised"
      >
        <span aria-hidden className="mt-0.5 font-mono text-[10px] text-dim">
          {expanded ? "▾" : "▸"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] text-text">{row.familyLabel}</span>
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-dim">
            <span className="tabular-nums">#{formatNumber(row.bestRank)}</span>
            <span>· {formatNumber(row.members)} alerts</span>
            <span>· {formatNumber(row.judged)} judged</span>
            <span className={row.gateOpen ? "text-ok" : "text-muted"}>
              · gate {row.gateOpen ? "open" : "closed"}
            </span>
            {applied && (
              <span className="text-warn">
                · applied {row.appliedAdjustment > 0 ? "+" : ""}
                {row.appliedAdjustment}
              </span>
            )}
          </span>
          {row.gateOpen && row.dominantCategory !== null && (
            <span className="mt-0.5 block text-[11px] text-muted">
              {categoryLabel(row.dominantCategory)}
              {row.agreementRatio !== null && ` · ${Math.round(row.agreementRatio * 100)}% agree`}
              {` · ${formatNumber(row.members - row.judged)} unjudged alerts carry this`}
            </span>
          )}
        </span>
      </button>
      {expanded && <FamilyMembers familyKey={row.familyKey} selectedRef={selectedRef} onSelect={onSelect} />}
    </li>
  );
}

/**
 * A family's alerts, fetched only when the group is opened.
 *
 * Read back through the ordinary queue endpoint with `familyKey`, so these rows are the same rows,
 * in the same contract order, as the ungrouped list — a grouped view rendering from a second source
 * could disagree with the queue it claims to summarise.
 */
function FamilyMembers({
  familyKey,
  selectedRef,
  onSelect,
}: {
  familyKey: string;
  selectedRef: string | null;
  onSelect: (alertRef: string) => void;
}) {
  const members = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/alerts", {
          params: { query: { limit: MEMBER_PREVIEW, offset: 0, sort: "queue", direction: "desc", familyKey } },
          signal,
        }),
      ),
    [familyKey],
  );
  if (members.status === "loading") {
    return (
      <div className="px-3 pb-2">
        <LoadingState label="Loading family…" />
      </div>
    );
  }
  if (members.status === "error") {
    return (
      <div className="px-3 pb-2">
        <ErrorState error={members.error} onRetry={members.reload} />
      </div>
    );
  }
  const hidden = members.data.page.total - members.data.items.length;
  return (
    <div className="border-t border-border bg-bg">
      <ol aria-label="Family members">
        {members.data.items.map((alert) => (
          <AlertCard
            key={alert.alertRef}
            alert={alert}
            selected={alert.alertRef === selectedRef}
            onSelect={() => onSelect(alert.alertRef)}
          />
        ))}
      </ol>
      {hidden > 0 && (
        <p className="px-3 py-1.5 font-mono text-[10px] text-dim">
          + {formatNumber(hidden)} more in this family
        </p>
      )}
    </div>
  );
}

//: How many of a family's alerts the expanded group shows. A family runs to 199 members on this
//: sample, and the point of the group is the summary, not a second full queue.
const MEMBER_PREVIEW = 8;

export function QueuePane({
  queue,
  families,
  grouping,
  onGrouping,
  tab,
  onTab,
  counts,
  search,
  onSearch,
  selectedRef,
  onSelect,
  onPage,
  offset,
  pageSize,
}: {
  queue: ApiResource<AlertPage>;
  families: ApiResource<FamilyPage>;
  grouping: QueueGrouping;
  onGrouping: (grouping: QueueGrouping) => void;
  tab: QueueTab;
  onTab: (tab: QueueTab) => void;
  counts: Readonly<Record<string, number | undefined>>;
  search: string;
  onSearch: (term: string) => void;
  selectedRef: string | null;
  onSelect: (alertRef: string) => void;
  onPage: (offset: number) => void;
  offset: number;
  pageSize: number;
}) {
  const [draft, setDraft] = useState(search);
  const [openFamily, setOpenFamily] = useState<string | null>(null);
  useEffect(() => setDraft(search), [search]);

  const grouped = grouping === "family";
  const page = grouped ? (families.status === "success" ? families.data.page : null) : queue.status === "success" ? queue.data.page : null;

  return (
    <section aria-label="Alert queue" className="flex min-h-0 flex-col border-r border-border bg-surface">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <h2 className="label-mono">Alert queue</h2>
        {page !== null && (
          <span className="font-mono text-[11px] tabular-nums text-dim">
            {formatNumber(page.total)} {grouped ? "families" : "alerts"}
          </span>
        )}
      </header>

      <div role="tablist" aria-label="Alert filter" className="flex flex-wrap gap-px border-b border-border bg-border">
        {QUEUE_TABS.map((option) => {
          const active = option.key === tab.key;
          const count = counts[option.key];
          return (
            <button
              key={option.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onTab(option)}
              className={`flex-1 whitespace-nowrap px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider ${
                active ? "bg-raised text-text shadow-[inset_0_-2px_0_var(--color-primary)]" : "bg-surface text-muted hover:text-text"
              }`}
            >
              {option.label}
              {count !== undefined && <span className="ml-1 text-dim">{formatNumber(count)}</span>}
            </button>
          );
        })}
      </div>

      <form
        role="search"
        className="border-b border-border p-2"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          onSearch(draft.trim());
        }}
      >
        <label htmlFor="workstation-search" className="sr-only">
          Search alerts
        </label>
        <input
          id="workstation-search"
          type="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="AL-00478, an IP or a rule id — Enter"
          className="w-full rounded-sm border border-border bg-bg px-2.5 py-1.5 font-mono text-xs text-text placeholder:text-dim focus:border-primary"
        />
      </form>

      {/* Grouping, not sorting. "Family" folds the queue into the groups similar-alert learning
          acts on, which is the only way to see that a verdict moved alerts nobody judged. */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
        <span id="queue-grouping" className="font-mono text-[10px] uppercase tracking-wider text-dim">
          Group by
        </span>
        <div role="group" aria-labelledby="queue-grouping" className="flex gap-px rounded-sm bg-border">
          {(["none", "family"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={grouping === option}
              onClick={() => {
                setOpenFamily(null);
                onGrouping(option);
              }}
              className={`px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                grouping === option ? "bg-raised text-text" : "bg-surface text-muted hover:text-text"
              }`}
            >
              {option === "none" ? "None" : "Family"}
            </button>
          ))}
        </div>
        {grouped && <span className="ml-auto font-mono text-[10px] text-dim">similar alerts</span>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {(grouped ? families : queue).status === "loading" && (
          <div className="p-3">
            <LoadingState label={grouped ? "Loading families…" : "Loading queue…"} />
          </div>
        )}
        {grouped && families.status === "error" && (
          <div className="p-3">
            <ErrorState error={families.error} onRetry={families.reload} />
          </div>
        )}
        {!grouped && queue.status === "error" && (
          <div className="p-3">
            <ErrorState error={queue.error} onRetry={queue.reload} />
          </div>
        )}
        {grouped && families.status === "success" &&
          (families.data.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted">No families match.</p>
          ) : (
            <ol aria-label="Alert families">
              {families.data.items.map((row) => (
                <FamilyGroup
                  key={row.familyKey}
                  row={row}
                  expanded={openFamily === row.familyKey}
                  onToggle={() => setOpenFamily(openFamily === row.familyKey ? null : row.familyKey)}
                  selectedRef={selectedRef}
                  onSelect={onSelect}
                />
              ))}
            </ol>
          ))}
        {!grouped && queue.status === "success" &&
          (queue.data.items.length === 0 ? (
            <p className="p-6 text-center text-sm text-muted">No alerts match.</p>
          ) : (
            <ol aria-label="Alerts">
              {queue.data.items.map((alert) => (
                <AlertCard
                  key={alert.alertRef}
                  alert={alert}
                  selected={alert.alertRef === selectedRef}
                  onSelect={() => onSelect(alert.alertRef)}
                />
              ))}
            </ol>
          ))}
      </div>

      {page !== null && page.total > pageSize && (
        <footer className="flex items-center justify-between border-t border-border px-3 py-1.5 font-mono text-[11px] text-muted">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => onPage(Math.max(0, offset - pageSize))}
            className="px-1 hover:text-text disabled:opacity-30"
          >
            ← Prev
          </button>
          <span className="tabular-nums">
            {formatNumber(offset + 1)}–{formatNumber(offset + page.returned)} of {formatNumber(page.total)}
          </span>
          <button
            type="button"
            disabled={offset + page.returned >= page.total}
            onClick={() => onPage(offset + pageSize)}
            className="px-1 hover:text-text disabled:opacity-30"
          >
            Next →
          </button>
        </footer>
      )}
    </section>
  );
}
