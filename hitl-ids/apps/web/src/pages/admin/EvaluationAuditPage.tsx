import { Link } from "react-router";
import { Card, PageHeader } from "../../components/ui";

export function EvaluationAuditPage() {
  return <div className="min-w-0 space-y-5">
    <PageHeader title="Evaluation & Audit" subtitle="Current frozen evaluation evidence and retained audit coverage." />
    <div className="grid min-w-0 gap-4 md:grid-cols-2">
      <Card title="Final Evaluation V3.1"><div className="space-y-3 p-4 text-sm">
        <p>Browse the official frozen results, Memory Impact, and drift evidence. This Admin consolidation was not part of that evaluation.</p>
        <Link className="text-accent underline" to="/admin/evaluation/final-v3-1">Open Final V3.1 Evaluation</Link>
      </div></Card>
      <Card title="Audit Trail"><div className="space-y-3 p-4 text-sm">
        <p>The retained trail includes historical event types. It is not yet a unified audit projection for every current V2/HITL subsystem.</p>
        <Link className="text-accent underline" to="/admin/audit">Open Audit Trail</Link>
      </div></Card>
    </div>
  </div>;
}
