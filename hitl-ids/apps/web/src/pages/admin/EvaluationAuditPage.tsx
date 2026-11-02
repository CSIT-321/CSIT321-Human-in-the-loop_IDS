import { Link } from "react-router";
import { Card, PageHeader } from "../../components/ui";

export function EvaluationAuditPage() {
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Evaluation & Audit" subtitle="Current product decisions, official frozen evaluation, and retained historical feedback." />
    <div className="grid min-w-0 gap-4 lg:grid-cols-3">
      <Card title="Current Product · HITL Audit"><div className="space-y-3 p-4 text-sm">
        <p>Trace current human and System Policy decisions across work, Verdict, Memory, Review, Tier 2, and response in the active workspace.</p>
        <Link className="text-accent underline" to="/admin/evaluation/audit">Open Current HITL Audit</Link>
      </div></Card>
      <Card title="Final Evaluation V3.1"><div className="space-y-3 p-4 text-sm">
        <p>Browse official frozen results, Memory Impact, and drift evidence. Current product audit events are separate from this evaluation.</p>
        <Link className="text-accent underline" to="/admin/evaluation/final-v3-1">Open Final V3.1 Evaluation</Link>
      </div></Card>
      <Card title="Historical Feedback / Legacy Audit"><div className="space-y-3 p-4 text-sm">
        <p>Retained Signature/XGBoost feedback and legacy event history. This is separate from the current HITL workflow.</p>
        <Link className="text-accent underline" to="/admin/audit">Open Historical Audit</Link>
      </div></Card>
    </div>
  </div>;
}
