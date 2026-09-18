/**
 * The analyst workstation (console rebuild R3): queue, alert and context in one view.
 *
 * SOC consoles put the queue beside a details pane rather than a page per alert
 * (docs/research/soc-console-research.md). The band tab, search, page offset and selected alert all
 * live in the URL, so a refresh or a pasted link restores the view.
 *
 * Keyboard: `j` / `k` move the selection down / up the list; `/` focuses search.
 */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { api, unwrap } from "../../api/client";
import { useApi } from "../../api/useApi";
import { useLastGood } from "../../features/alert/useLastGood";
import { AlertPane } from "../../features/workstation/AlertPane";
import { ContextRail } from "../../features/workstation/ContextRail";
import { KpiStrip } from "../../features/workstation/KpiStrip";
import { QUEUE_TABS, QueuePane, type QueueGrouping, type QueueTab } from "../../features/workstation/QueuePane";

const PAGE_SIZE = 50;

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)
  );
}

export function WorkstationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = QUEUE_TABS.find((option) => option.key === searchParams.get("tab")) ?? QUEUE_TABS[0];
  const search = searchParams.get("search") ?? "";
  // A family deep-link (`?familyKey=…`) narrows the flat queue to the alerts one verdict moved;
  // `?group=family` folds the whole queue into those groups. They are different questions, so they
  // are different parameters.
  const familyKey = searchParams.get("familyKey");
  const grouping: QueueGrouping = searchParams.get("group") === "family" ? "family" : "none";
  const offsetParam = Number.parseInt(searchParams.get("offset") ?? "0", 10);
  const offset = Number.isFinite(offsetParam) && offsetParam > 0 ? offsetParam : 0;
  const selectedParam = searchParams.get("alert");

  const [queueVersion, setQueueVersion] = useState(0);
  const [alertVersion, setAlertVersion] = useState(0);

  const update = useCallback(
    (changes: Readonly<Record<string, string | null>>) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === "") next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const summary = useApi((signal) => unwrap(api.GET("/api/dashboard/summary", { signal })), [queueVersion]);
  const breakdowns = useApi(
    (signal) => unwrap(api.GET("/api/dashboard/breakdowns", { params: { query: { limit: 5 } }, signal })),
    [queueVersion],
  );
  const queue = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/alerts", {
          params: {
            query: {
              limit: PAGE_SIZE,
              offset,
              sort: "queue",
              direction: "desc",
              queueClass: tab.queueClass === null ? null : [tab.queueClass],
              evidenceClass: tab.evidenceClass === null ? null : [tab.evidenceClass],
              requiresReview: tab.requiresReview ? true : null,
              search: search === "" ? null : search,
              familyKey,
            },
          },
          signal,
        }),
      ),
    [tab.key, search, offset, familyKey, queueVersion],
  );
  // The same filters, grouped by what the system calls similar. Loaded only while that view is on
  // screen: the grouped query scans the whole queue to rank the groups.
  const families = useApi(
    (signal) =>
      grouping === "family"
        ? unwrap(
            api.GET("/api/alerts/families", {
              params: {
                query: {
                  limit: PAGE_SIZE,
                  offset,
                  queueClass: tab.queueClass === null ? null : [tab.queueClass],
                  evidenceClass: tab.evidenceClass === null ? null : [tab.evidenceClass],
                  requiresReview: tab.requiresReview ? true : null,
                  search: search === "" ? null : search,
                },
              },
              signal,
            }),
          )
        : new Promise<never>(() => undefined),
    [grouping, tab.key, search, offset, queueVersion],
  );
  const queueData = useLastGood(queue);
  const items = queueData?.items ?? [];
  const selectedRef = selectedParam !== null && selectedParam !== "" ? selectedParam : (items[0]?.alertRef ?? null);

  const alertRef = selectedRef ?? "";
  const hasSelection = selectedRef !== null;
  const detailResource = useApi(
    (signal) =>
      hasSelection
        ? unwrap(api.GET("/api/alerts/{alertRef}", { params: { path: { alertRef } }, signal }))
        : new Promise<never>(() => undefined),
    [alertRef, alertVersion],
  );
  const adjustmentResource = useApi(
    (signal) =>
      hasSelection
        ? unwrap(api.GET("/api/alerts/{alertRef}/score-adjustment", { params: { path: { alertRef } }, signal }))
        : new Promise<never>(() => undefined),
    [alertRef, alertVersion],
  );
  const historyResource = useApi(
    (signal) =>
      hasSelection
        ? unwrap(api.GET("/api/alerts/{alertRef}/feedback-history", { params: { path: { alertRef } }, signal }))
        : new Promise<never>(() => undefined),
    [alertRef, alertVersion],
  );
  const notes = useApi(
    (signal) =>
      hasSelection
        ? unwrap(api.GET("/api/alerts/{alertRef}/notes", { params: { path: { alertRef } }, signal }))
        : new Promise<never>(() => undefined),
    [alertRef, alertVersion],
  );
  const detail = useLastGood(detailResource);
  const adjustment = useLastGood(adjustmentResource);
  const history = useLastGood(historyResource);
  const shownDetail = detail !== null && detail.alert.alertRef === alertRef ? detail : null;

  const counts: Record<string, number | undefined> = {};
  if (summary.status === "success") {
    counts.all = summary.data.totalAlerts;
    counts.review = summary.data.requiresReview;
    for (const option of QUEUE_TABS) {
      if (option.queueClass !== null) {
        counts[option.key] = (summary.data.byQueueClass ?? []).find((band) => band.queueClass === option.queueClass)?.count ?? 0;
      } else if (option.evidenceClass !== null) {
        counts[option.key] = summary.data.byEvidenceClass?.[option.evidenceClass] ?? 0;
      }
    }
  }

  const select = useCallback((ref: string) => update({ alert: ref }), [update]);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (event.key === "/") {
        event.preventDefault();
        document.getElementById("workstation-search")?.focus();
        return;
      }
      if ((event.key !== "j" && event.key !== "k") || items.length === 0) return;
      const index = items.findIndex((alert) => alert.alertRef === selectedRef);
      const nextIndex = event.key === "j" ? Math.min(items.length - 1, index + 1) : Math.max(0, index - 1);
      const next = items[nextIndex];
      if (next !== undefined) {
        event.preventDefault();
        select(next.alertRef);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, selectedRef, select]);

  const onChanged = () => {
    setAlertVersion((n) => n + 1);
    setQueueVersion((n) => n + 1);
  };

  const refreshing =
    shownDetail !== null &&
    (detailResource.status === "loading" || adjustmentResource.status === "loading" || historyResource.status === "loading");

  return (
    <div className="-mx-6 -my-5 flex h-[calc(100%+2.5rem)] min-h-[36rem] flex-col">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-bg px-4 py-2">
        <h1 className="text-sm font-semibold tracking-tight text-text">Workstation</h1>
        <p className="hidden font-mono text-[11px] text-dim md:block">
          <kbd className="rounded-sm border border-border px-1">j</kbd> <kbd className="rounded-sm border border-border px-1">k</kbd> move ·{" "}
          <kbd className="rounded-sm border border-border px-1">/</kbd> search
        </p>
      </div>
      <KpiStrip summary={summary} breakdowns={breakdowns} />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(18rem,20rem)_minmax(0,1fr)] xl:grid-cols-[21rem_minmax(0,1fr)_20rem]">
        <QueuePane
          queue={queue}
          families={families}
          grouping={grouping}
          onGrouping={(next) => update({ group: next === "family" ? "family" : null, offset: null, familyKey: null })}
          tab={tab}
          onTab={(next: QueueTab) => update({ tab: next.key === "all" ? null : next.key, offset: null, alert: null })}
          counts={counts}
          search={search}
          onSearch={(term) => update({ search: term, offset: null, alert: null })}
          selectedRef={selectedRef}
          onSelect={select}
          onPage={(next) => update({ offset: next === 0 ? null : String(next), alert: null })}
          offset={offset}
          pageSize={PAGE_SIZE}
        />
        {hasSelection ? (
          <AlertPane
            key={alertRef}
            detail={shownDetail}
            detailResource={detailResource}
            adjustment={adjustment}
            adjustmentResource={adjustmentResource}
            history={history}
            historyResource={historyResource}
            notes={notes}
            refreshing={refreshing}
            onChanged={onChanged}
          />
        ) : (
          <section aria-label="Alert detail" className="grid place-items-center p-8 text-sm text-muted">
            {queue.status === "loading" ? "Loading…" : "Select an alert."}
          </section>
        )}
        <ContextRail detail={shownDetail} detailError={detailResource.status === "error"} />
      </div>
    </div>
  );
}
