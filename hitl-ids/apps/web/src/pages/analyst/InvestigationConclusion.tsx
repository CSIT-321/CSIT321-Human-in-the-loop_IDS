import type { Schemas } from "../../api/client";

export type FinalCategory = NonNullable<Schemas["InvestigationConclusionRequest"]["finalAttackCategory"]>;
export const finalCategories: Record<FinalCategory, string> = {
  brute_force: "Brute Force", botnet_c2: "Botnet / C2", dos: "DoS", ddos: "DDoS",
  web_attack: "Web Attack", infiltration: "Infiltration", reconnaissance_port_scan: "Reconnaissance / Port Scan",
  malware_exploit: "Malware / Exploit", other_known_attack: "Other Known Attack",
};
export const systemCategoryLabel = (classification?: Schemas["AttackClassification"] | null) =>
  !classification ? "Not recorded" : classification.attackCategory === "unknown_needs_expert" ? "Unknown / Needs Expert" :
    classification.attackCategory ? finalCategories[classification.attackCategory] : "Informational / Policy Signal";

export function ConclusionDetails({ conclusion }: { conclusion: Schemas["InvestigationConclusion"] }) {
  return <div className="min-w-0 space-y-1 text-sm [overflow-wrap:anywhere]">
    <p>Human Investigation Finding: {conclusion.finding.replaceAll("_", " ")}</p>
    <p>Human Final Attack Classification: {conclusion.finalAttackCategory ? finalCategories[conclusion.finalAttackCategory] :
      conclusion.recordKind === "legacy_finding" ? "Not recorded (historical Finding)" :
        conclusion.finding === "expected_activity" ? "Not applicable" : "Unresolved"}</p>
    <p className="text-xs text-muted">Actor #{conclusion.actorId} · {conclusion.createdAt} · Case revision {conclusion.caseRevision} · Event #{conclusion.eventId}</p>
    {conclusion.supersedesEventId && <p className="text-xs text-muted">Supersedes event #{conclusion.supersedesEventId}; history is preserved.</p>}
    <p className="whitespace-pre-wrap">{conclusion.reason}</p>
  </div>;
}
