import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";

type TourStep = { title: string; description: string; path: string; target: string; tab?: string };

const operations = "/analyst/operations";
const steps: readonly TourStep[] = [
  { title: "Your Analyst Workstation", description: "This shared starting point shows active work, review needs, and Tier 2 cases. The tour only navigates and explains; it never records a decision.", path: operations, target: ".ops-kpis" },
  { title: "Find the next alert", description: "Use queue views, attack type, and search to narrow the workload. Operational Priority orders the alerts. Only an intentional selection of an eligible row requests ownership.", path: operations, target: '[aria-label="Operational alert queue"]' },
  { title: "Claim shared work", description: "Intentionally selecting an eligible Available Tier 1 row starts 750 ms Auto-Claim arbitration. One claimant becomes Owner; concurrent claimants get Claim Conflict with no owner. An already-owned alert opens as Viewer. Page load, direct URL, SSE arrival, background refresh, and automatic rendering never claim.", path: operations, target: '[aria-label="Operational alert workspace"]' },
  { title: "Overview and routing", description: "Read the route, Operational Priority, review requirement, and detector provenance. Unknown / Needs Expert creates a formal Tier 2 Case automatically; a Tier 1 Owner can also escalate directly to a Case.", path: operations, tab: "Overview", target: '#ops-tab-Overview' },
  { title: "Evidence", description: "Inspect immutable Suricata detector evidence, the primary and related signatures, native severity, and source/destination before a human judgment.", path: operations, tab: "Evidence", target: '#ops-tab-Evidence' },
  { title: "Context and review", description: "Check trusted context provenance and the Selective Review reasons. Policy evaluation and the explicit Require Human Review override are separate from the human Verdict.", path: operations, tab: "Context & Review", target: '[id="ops-tab-Context & Review"]' },
  { title: "Analyst Verdict", description: "Only the current Tier 1 Owner can record the first Verdict; a Viewer cannot use owner-scoped actions. Choose Confirmed Malicious, Suspicious, Expected Activity, or False Positive with a reason. This human conclusion does not overwrite System Attack Classification and automatically creates Exact Human Learning evidence.", path: operations, tab: "Analyst Verdict", target: '[id="ops-tab-Analyst Verdict"]' },
  { title: "Triage Memory for this alert", description: "A canonical Verdict creates Exact evidence automatically. Support, agreement, and conflict policy determine reusable Triage Memory. Active Memory guides analysis; it does not automatically suppress review or retrain a model online.", path: operations, tab: "Triage Memory", target: '[id="ops-tab-Triage Memory"]' },
  { title: "History and notes", description: "Read and add investigation notes, and review earlier human Verdicts and routing decisions. Only the analyst who owns the alert can add a note; notes cannot be edited or deleted. For Tier 2 work, the formal Case also holds its own notes and timeline.", path: operations, tab: "History & Notes", target: '[id="ops-tab-History & Notes"]' },
  { title: "Technical snapshots", description: "Read the current operational state and immutable canonical detector snapshot when tracing a decision. These snapshots are read-only.", path: operations, tab: "Technical", target: '#ops-tab-Technical' },
  { title: "Tier 2 Cases", description: "Unknown / Needs Expert automatically enters Expert Review Required and creates a formal Case. Tier 1 Owner manual escalation also creates the Case atomically; there is no current Candidate approval stage.", path: "/analyst/tier2-cases", target: 'a[href="/analyst/tier2-cases"]' },
  { title: "Tier 2 investigation and closure", description: "A Case shows the same immutable Primary Alert Evidence as Tier 1 plus Investigation Assistance, trusted context, and advisory related alerts. Record an Investigation Conclusion and Human Final Attack Classification, review automatic Expert Learning, decide on response, then resolve the Case. Approval means Approved — Not Executed.", path: "/analyst/tier2-cases", target: 'a[href="/analyst/tier2-cases"]' },
  { title: "Triage Memory library", description: "Inspect Exact or Narrow lessons, support, conflicts, validity, activation, evidence, and audit history. Memory is guidance under current safety policy.", path: "/analyst/triage-memory", target: 'a[href="/analyst/triage-memory"]' },
  { title: "Selective Review queue", description: "Active Memory alone is insufficient. Current trusted context, Memory, safety gates, and policy evaluation may yield No Immediate Review. That is neither a human Verdict nor an alert closure.", path: "/analyst/selective-review", target: 'a[href="/analyst/selective-review"]' },
  { title: "Incoming Alerts", description: "Inspect external Suricata evidence and eligibility before operational admission. Admission is separate from an Analyst Verdict or Tier 2 Investigation Conclusion.", path: "/analyst/external-admission", target: 'a[href="/analyst/external-admission"]' },
  { title: "Ready to work", description: "Start with an Available alert, inspect its evidence and context, then intentionally select it if you are ready to own Tier 1 review. You can reopen this read-only tour from the top bar.", path: operations, target: ".ops-kpis" },
];

export function AnalystTour({ stepIndex, onStep, onClose }: {
  stepIndex: number | null;
  onStep: (step: number) => void;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const startingPath = useRef<string | null>(null);
  const previousStep = useRef<number | null>(null);
  const nextButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (stepIndex === null) {
      window.dispatchEvent(new CustomEvent("analyst-tour-tab", { detail: null }));
      if (previousStep.current !== null && startingPath.current && location.pathname + location.search !== startingPath.current) {
        void navigate(startingPath.current, { replace: true });
      }
      startingPath.current = null;
      previousStep.current = null;
      return;
    }
    if (previousStep.current === null) startingPath.current = location.pathname + location.search;
    previousStep.current = stepIndex;
    const step = steps[stepIndex];
    if (!step) return;
    if (step.path === operations) {
      if (location.pathname !== operations) void navigate(operations, { replace: true });
      else window.dispatchEvent(new CustomEvent("analyst-tour-tab", { detail: step.tab ?? null }));
      return;
    }
    window.dispatchEvent(new CustomEvent("analyst-tour-tab", { detail: null }));
    if (location.pathname !== step.path) void navigate(step.path, { replace: true });
  }, [stepIndex, location.pathname, navigate]);

  useEffect(() => {
    if (stepIndex === null) return;
    const step = steps[stepIndex];
    if (!step) return;
    let highlighted: Element | null = null;
    const update = () => {
      const target = document.querySelector(step.target) ?? document.querySelector('[data-tour="analyst-main"]');
      if (target === highlighted) return;
      highlighted?.classList.remove("analyst-tour-highlight");
      highlighted = target;
      target?.classList.add("analyst-tour-highlight");
      if (target instanceof HTMLElement && typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); highlighted?.classList.remove("analyst-tour-highlight"); };
  }, [stepIndex, location.pathname, location.search]);

  useEffect(() => {
    if (stepIndex === null) return;
    nextButton.current?.focus();
    const dismiss = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", dismiss);
    return () => window.removeEventListener("keydown", dismiss);
  }, [stepIndex, onClose]);

  const step = stepIndex === null ? null : steps[stepIndex];
  if (!step || stepIndex === null) return null;
  const last = stepIndex === steps.length - 1;
  return <aside role="region" aria-label="Analyst feature tour" className="analyst-tour-card fixed bottom-4 right-4 z-50 max-h-[min(80vh,34rem)] w-[min(24rem,calc(100vw-2rem))] overflow-y-auto rounded-md border border-primary bg-surface p-4 text-sm text-text shadow-2xl">
    <div className="flex items-start justify-between gap-3">
      <div><p className="label-mono">Analyst guide · {stepIndex + 1} / {steps.length}</p><h2 className="mt-1 text-base font-semibold">{step.title}</h2></div>
      <button type="button" onClick={onClose} aria-label="Close analyst tour" className="rounded border border-border px-2 py-1 hover:bg-raised">×</button>
    </div>
    <p className="mt-3 leading-relaxed text-muted">{step.description}</p>
    <div className="mt-4 flex items-center justify-between gap-2">
      <button type="button" onClick={onClose} className="text-xs text-muted underline">Skip tour</button>
      <div className="flex gap-2">
        <button type="button" disabled={stepIndex === 0} onClick={() => onStep(stepIndex - 1)} className="rounded border border-border px-3 py-1.5 disabled:opacity-40">Back</button>
        <button ref={nextButton} type="button" onClick={() => last ? onClose() : onStep(stepIndex + 1)} className="rounded bg-primary px-3 py-1.5 font-semibold text-bg">{last ? "Finish" : "Next"}</button>
      </div>
    </div>
  </aside>;
}
