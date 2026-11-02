import type { Schemas } from "../../api/client";

type Work = Schemas["WorkView"];

export function workLabel(work: Work) {
  if (work.status === "in_review") return work.isOwner ? "In Review — You" : `In Review — ${work.ownerName}`;
  if (work.status === "completed") return `Completed — Reviewed by ${work.finishedByName}`;
  if (work.status === "escalated") return `Escalated — ${work.finishedByName}`;
  return work.status === "available" ? "Available" : "No active Tier 1 work";
}

/** Claim submission belongs to the explicit queue selection gesture in the Workstation. */
export function AnalystWorkPanel({ work, starting = false }: { work: Work; starting?: boolean }) {
  const status = starting ? "Starting review…" : work.status === "available" ? "Available for Review" :
    work.status === "in_review" ? "In Review" : workLabel(work);
  return <section aria-label="Human work status" className="min-w-0 space-y-2 rounded-sm border border-border p-3 text-xs">
    <p>Work Status: <strong>{status}</strong></p>
    {!starting && work.status === "in_review" && <>
      <p>Owner: <strong>{work.isOwner ? `${work.ownerName ?? "You"} (You)` : work.ownerName ?? "Unknown"}</strong></p>
      <p>Your Access: <strong>{work.isOwner ? "Owner" : "Viewer"}</strong></p>
    </>}
    <p className="break-words text-muted">{starting ? "Waiting for review ownership…" :
      work.status === "available" && work.canClaim ? "Selecting this alert starts your review." : work.explanation}</p>
    {work.finishedAt && <p>Finished at: {work.finishedAt}</p>}
    {work.verdictOutcome && <p className="capitalize">Verdict: {work.verdictOutcome.replaceAll("_", " ")}</p>}
  </section>;
}
