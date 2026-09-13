/**
 * The workstation's left column: band tabs, a search box, and the ranked alert list.
 *
 * The API ranks; this list renders rows in the order they arrive. Tabs are queue bands, not severities:
 * in this data severity is almost only Critical or Informational, while the band carries the triage
 * meaning (console-rebuild-proposal.md §1).
 */

import { useEffect, useRef, useState, type FormEvent } from "react";

import type { Schemas } from "../../api/client";
import type { ApiResource } from "../../api/useApi";
import { ErrorState, LoadingState } from "../../components/states";
import { formatNumber, formatScore, humanise } from "../../design/format";

type AlertSummary = Schemas["AlertSummary"];
type QueueClass = AlertSummary["queueClass"];

interface AlertPage {
  readonly items: AlertSummary[];
  readonly page: Schemas["PageInfo"];
}

export interface QueueTab {
  readonly key: string;
  readonly label: string;
  readonly queueClass: QueueClass | null;
  readonly requiresReview: boolean;
}

export const QUEUE_TABS: readonly [QueueTab, ...QueueTab[]] = [
  { key: "all", label: "All", queueClass: null, requiresReview: false },
  { key: "tier2", label: "Tier 2", queueClass: "tier2_candidate", requiresReview: false },
  { key: "review", label: "Needs review", queueClass: null, requiresReview: true },
  { key: "corroborated", label: "Rule + model", queueClass: "corroborated", requiresReview: false },
  { key: "rule", label: "Rule only", queueClass: "signature_override", requiresReview: false },
  { key: "model", label: "Model only", queueClass: "ml_only", requiresReview: false },
  { key: "none", label: "Not flagged", queueClass: "none", requiresReview: false },
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

export function QueuePane({
  queue,
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
  useEffect(() => setDraft(search), [search]);

  return (
    <section aria-label="Alert queue" className="flex min-h-0 flex-col border-r border-border bg-surface">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <h2 className="label-mono">Alert queue</h2>
        {queue.status === "success" && (
          <span className="font-mono text-[11px] tabular-nums text-dim">{formatNumber(queue.data.page.total)} alerts</span>
        )}
      </header>

      <div role="tablist" aria-label="Queue band" className="flex flex-wrap gap-px border-b border-border bg-border">
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

      <div className="min-h-0 flex-1 overflow-y-auto">
        {queue.status === "loading" && (
          <div className="p-3">
            <LoadingState label="Loading queue…" />
          </div>
        )}
        {queue.status === "error" && (
          <div className="p-3">
            <ErrorState error={queue.error} onRetry={queue.reload} />
          </div>
        )}
        {queue.status === "success" &&
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

      {queue.status === "success" && queue.data.page.total > pageSize && (
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
            {formatNumber(offset + 1)}–{formatNumber(offset + queue.data.page.returned)} of {formatNumber(queue.data.page.total)}
          </span>
          <button
            type="button"
            disabled={offset + queue.data.page.returned >= queue.data.page.total}
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
