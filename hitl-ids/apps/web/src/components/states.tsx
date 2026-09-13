/**
 * The three states every API-backed view owes its user (plan step S11).
 *
 * `ApiView` exists so a page cannot accidentally render only the happy path: the loading, error and
 * empty branches are one component, wired to `useApi`'s `ApiResource<T>`, and a page supplies only
 * what success looks like.
 */

import type { ReactNode } from "react";

import type { ApiError } from "../api/client";
import type { ApiResource } from "../api/useApi";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-sm border border-border bg-surface p-5 text-muted"
    >
      <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-accent" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-sm border border-danger/40 bg-danger-dim/40 p-5">
      <h2 className="text-lg font-semibold text-text">Something went wrong</h2>
      <p className="mt-1 text-sm text-muted">{error.message}</p>
      <p className="mt-3">
        <span className="rounded-md bg-raised px-2 py-0.5 font-mono text-xs text-danger">
          {error.code}
          {error.status > 0 ? ` · HTTP ${error.status}` : ""}
        </span>
      </p>
      {onRetry !== undefined && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text hover:bg-surface"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="rounded-sm border border-dashed border-border bg-surface p-10 text-center">
      <h2 className="text-base font-semibold text-muted">{title}</h2>
      {hint !== undefined && <p className="mt-2 text-sm text-muted">{hint}</p>}
    </div>
  );
}

export function ApiView<T>({
  resource,
  children,
  isEmpty,
  empty,
  loadingLabel,
}: {
  resource: ApiResource<T>;
  children: (data: T) => ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loadingLabel?: string;
}) {
  if (resource.status === "loading") return <LoadingState label={loadingLabel} />;
  if (resource.status === "error")
    return <ErrorState error={resource.error} onRetry={resource.reload} />;
  const { data } = resource;
  if (isEmpty !== undefined && isEmpty(data)) {
    return <>{empty ?? <EmptyState title="Nothing to show yet" />}</>;
  }
  return <>{children(data)}</>;
}
