import { useRef, useState } from "react";
import { api, unwrap, type Schemas } from "../../api/client";

type View = Schemas["RoutingView"];
type Decision = "approve_tier2" | "reject_tier2";

const button = "rounded-sm border border-border px-3 py-2 text-sm hover:bg-raised disabled:opacity-50";

/** C3 "Why Tier 2" panel (decision Q4: Overview tab, above the verdict form; user choice 2026-11-08 option A).
 *  Shown only while the server says the recommendation is open. Both decisions reuse existing server paths:
 *  Escalate = atomic tier2/escalate-case with approve_tier2 (C1 records the +15); Keep in Tier 1 = tier2/reject.
 *  The server's allowedActions decide which button works, so the screen never offers what the server refuses. */
export function Tier2RecommendationPanel({ view, onChanged }: { view: View; onChanged: (view: View) => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<{ action: Decision; body: Schemas["RoutingRequest"] } | null>(null);
  if (!view.tier2RecommendationOpen) return null;

  const can = (action: Decision) => view.allowedActions.includes(action);
  const text = reason.trim();

  async function decide(action: Decision) {
    if (busy || !text || !can(action)) return;
    const previous = pending.current;
    if (!previous || previous.action !== action || previous.body.reason !== text) {
      pending.current = { action, body: { requestId: crypto.randomUUID(), expectedStateVersion: view.stateVersion, reason: text } };
    }
    setBusy(true); setError("");
    try {
      const params = { path: { alertRef: view.operationalAlertRef } };
      if (action === "approve_tier2") {
        const result = await unwrap(api.POST("/api/v2/alerts/{alertRef}/tier2/escalate-case", { params, body: { ...pending.current!.body, action } }));
        onChanged({ ...result.view, caseRef: result.case.caseRef });
      } else {
        const result = await unwrap(api.POST("/api/v2/alerts/{alertRef}/tier2/reject", { params, body: pending.current!.body }));
        onChanged(result.view);
      }
      pending.current = null; setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The decision could not be confirmed.");
    } finally { setBusy(false); }
  }

  function toVerdict() {
    const target = document.getElementById("analyst-verdict-outcome");
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    target?.focus();
  }

  return <section aria-label="Why Tier 2 is recommended" className="space-y-3 rounded-sm border border-warn/50 bg-warn-dim p-4">
    <h3 className="label-mono">Why Tier 2 is recommended</h3>
    <ul className="space-y-1 text-sm">{view.state.tier2RecommendationReasons.map(item => <li key={item} className="break-words">{item}</li>)}</ul>
    <label htmlFor="tier2-recommendation-reason" className="block text-sm">Reason (required for Escalate and Keep in Tier 1)</label>
    <textarea id="tier2-recommendation-reason" rows={2} maxLength={2000} value={reason} disabled={busy}
      placeholder="A short reason is enough, for example: Time constraints."
      onChange={event => setReason(event.target.value)} className="w-full min-w-0 rounded-sm border border-border bg-surface p-2 text-sm" />
    <div className="flex flex-wrap gap-2">
      <button className={button} disabled={busy || !text || !can("approve_tier2")} onClick={() => void decide("approve_tier2")}>Escalate to Tier 2</button>
      <button className={button} disabled={busy || !text || !can("reject_tier2")} onClick={() => void decide("reject_tier2")}>Keep in Tier 1</button>
      <button className={button} type="button" onClick={toVerdict}>Record verdict ↓</button>
    </div>
    {!can("approve_tier2") && !can("reject_tier2") && <p className="text-xs text-muted">Start review to decide.</p>}
    <p className="text-xs text-muted">Escalate opens a Tier 2 case and records the approved "escalate" (+15). Keep in Tier 1 closes the recommendation and keeps the alert on your queue.</p>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </section>;
}
