import type { Schemas } from "../../api/client";
import { Card, KeyValues } from "../../components/ui";
import { formatPercent } from "../../design/format";
import { DetectorProvenance } from "./DetectorProvenance";
import { ConditionTable } from "./SignaturePanelCard";

import { SuricataEvidence } from "./SuricataEvidence";

type Canonical = Schemas["CanonicalAlert"];
type Json = Schemas["JsonValue"];
const object = (value: Json | undefined): Record<string, Json> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, Json> : {};
const display = (value: Json | undefined) => value == null ? "Not provided" : typeof value === "object" ? JSON.stringify(value) : String(value);
const endpoint = (ip: string, port: number | null) => port == null ? ip : `${ip.includes(":") ? `[${ip}]` : ip}:${port}`;

// C4 (S7-03, S7-05). Paths measured on the routed demo copy: analysis/phase-c/c4_fields.py.
const AGREEMENT: Record<string, string> = {
  corroborated: "Rule and model agree",
  signature_override: "Rule overrides the model",
  ml_only: "Model only — no rule fired",
  none: "Neither the rule nor the model flagged this flow",
};
const isFlow = (alert: Schemas["OperationalAlertV2"]) =>
  alert.sourceKind === "legacy_flow_alert" || alert.detectorEvidence.detectorSource === "current_flow";

/** The approved screens' short name (AL-01958) for a flow alert; null for any other source. */
export function flowShortName(alert: Schemas["OperationalAlertV2"]): string | null {
  const ref = alert.detectorEvidence.sourceRecordReference;
  return isFlow(alert) && typeof ref === "string" && /^AL-\d+$/.test(ref) ? ref : null;
}

/** A flow alert's confidence is the legacy fusion confidence; the canonical field is empty for corroborated alerts. */
function flowConfidence(alert: Schemas["OperationalAlertV2"]): number | null | undefined {
  if (!isFlow(alert)) return undefined;
  const fusion = (alert.sourceProvenance as { legacyFusionConfidence?: unknown } | undefined)?.legacyFusionConfidence;
  return typeof fusion === "number" ? fusion : alert.detectorEvidence.confidence;
}

export function operationalDetector(source: string | null | undefined, name: string) {
  return source === "current_flow" ? "Legacy Flow Detector" : name;
}

function ModelEvidence({ detector, historical }: { detector: Canonical; historical: boolean }) {
  const evidence = detector.structuredEvidence;
  const shap = object(evidence.treeShap);
  const supporting = shap.topSupportingFeatures ?? shap.top_supporting_features;
  const opposing = shap.topOpposingFeatures ?? shap.top_opposing_features;
  const features = [...(Array.isArray(supporting) ? supporting : []), ...(Array.isArray(opposing) ? opposing : [])];
  return <Card title={historical ? "Historical XGBoost Evidence" : "Model Evidence"}>
    <KeyValues rows={[
      ["Model/version", detector.detectorVersion ?? display(detector.provenance.modelVersion)],
      ["Prediction", display(evidence.mlPredictedClass ?? evidence.predictedAttackType ?? evidence.prediction)],
      // C4 decision (2026-11-08): a flow alert shows its fusion confidence in the provenance block. Its
      // canonical confidence is empty for corroborated alerts, so the card shows the model's own
      // probability instead of a second, empty "confidence" row.
      ...(historical ? [] : [["Supplied confidence", detector.confidence == null ? "Not provided" : formatPercent(detector.confidence)] as const]),
      ...(historical && typeof evidence.mlProbability === "number" ? [["Model probability", formatPercent(evidence.mlProbability)] as const] : []),
    ]} />
    {evidence.treeShap != null && <section aria-label="TreeSHAP evidence" className="mt-4 space-y-2">
      <h3 className="label-mono">TreeSHAP / Attributions</h3>
      {features.length > 0 ? <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <thead><tr><th className="p-2">Feature</th><th className="p-2">Value</th><th className="p-2">Contribution</th></tr></thead>
        <tbody>{features.map((entry, index) => { const feature = object(entry); return <tr key={index} className="border-t border-border">
          <td className="p-2 font-mono">{display(feature.featureName ?? feature.feature_name)}</td>
          <td className="p-2">{display(feature.featureValue ?? feature.feature_value)}</td>
          <td className="p-2 font-mono">{display(feature.shapContribution ?? feature.shap_contribution)}</td>
        </tr>; })}</tbody>
      </table></div> : <p className="text-xs text-muted">{display(shap.status ?? shap.note)}</p>}
      <details><summary className="cursor-pointer text-xs text-accent">Supplied attribution snapshot</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(evidence.treeShap, null, 2)}</pre></details>
    </section>}
  </Card>;
}

/** Only immutable operational/canonical evidence; no legacy queue or feedback request. */
export function OperationalEvidence({ alert, summaryOnly = false }: { alert: Schemas["OperationalAlertV2"]; summaryOnly?: boolean }) {
  const detector = alert.detectorEvidence;
  const source = detector.detectorSource.toLowerCase();
  const legacy = source === "current_flow";
  const explanation = detector.structuredEvidence.explanation;
  return <div className="space-y-4">
    <DetectorProvenance detector={detector} confidence={flowConfidence(alert)}
      agreement={legacy ? AGREEMENT[detector.evidenceClass] ?? null : null} />
    <KeyValues rows={[
      ["Native Category", detector.detectionCategory ?? "Not provided"],
      ["Source", endpoint(detector.sourceIp, detector.sourcePort)],
      ["Destination", endpoint(detector.destinationIp, detector.destinationPort)],
      ["Protocol", detector.protocol],
      ["Occurred at", detector.occurredAt],
    ]} />
    {legacy && typeof explanation === "string" && explanation !== "" &&
      <section aria-label="Combined explanation" className="text-sm">
        <h3 className="label-mono mb-1">Combined explanation</h3><p className="break-words">{explanation}</p>
      </section>}
    {source === "suricata" && detector.structuredEvidence.suricataBundle != null && <SuricataEvidence detector={detector} summaryOnly={summaryOnly} />}
    {!summaryOnly && <>
      {source === "suricata" && detector.structuredEvidence.suricataBundle == null && <Card title="Suricata Rule Evidence"><KeyValues rows={[
        ["Signature", detector.detectionTitle],
        ["Rule ID", display(detector.structuredEvidence.signatureId)],
        ["Action", display(detector.structuredEvidence.action)],
      ]} /></Card>}
      {legacy && <Card title="Historical Signature Evidence">
        <p className="mb-2 text-xs text-muted">Legacy Flow Detector evidence; separate from current routing and human decisions.</p>
        {Array.isArray(detector.structuredEvidence.signatureRules) && detector.structuredEvidence.signatureRules.length > 0
          ? <ul className="space-y-2 text-sm">{detector.structuredEvidence.signatureRules.map((rule, index) => {
            const fields = object(rule); const id = display(fields.ruleId ?? fields.rule_id);
            const conditions = fields.matched_conditions ?? fields.matchedConditions;
            return <li key={index} className="break-words">{display(fields.name)} <span className="font-mono text-xs text-muted">{id}</span>
              <ConditionTable label={`Conditions for ${id}`}
                conditions={Array.isArray(conditions) ? conditions.map(c => object(c)) : []} />
            </li>;
          })}</ul> : <p className="text-sm text-muted">No historical signature matches supplied.</p>}
      </Card>}
      {(source === "xgboost" || legacy) && <ModelEvidence detector={detector} historical={legacy} />}
      {source !== "suricata" && source !== "xgboost" && !legacy && <Card title="Detector Evidence"><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(detector.structuredEvidence, null, 2)}</pre></Card>}
    </>}
  </div>;
}
