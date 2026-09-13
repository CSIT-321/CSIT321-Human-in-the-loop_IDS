/**
 * A route that exists and navigates, but whose view a later plan step fills in. Naming the step is
 * the point: the demo walks the shells without pretending an unbuilt screen is finished.
 */

export function StepPlaceholder({ title, step, summary }: { title: string; step: string; summary: string }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-text">{title}</h1>
      <section className="rounded-sm border border-border bg-surface p-5">
        <span className="inline-block rounded-full bg-accent-dim px-3 py-1 text-xs font-medium text-accent">
          Built in {step}
        </span>
        <p className="mt-3 text-sm text-text">{summary}</p>
        <p className="mt-3 text-sm text-muted">
          This view is part of the demo build plan and is not implemented yet.
        </p>
      </section>
    </div>
  );
}
