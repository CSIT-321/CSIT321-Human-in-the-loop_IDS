import type { Schemas } from "../../api/client";
import { Card, KeyValues } from "../../components/ui";
import { formatPercent } from "../../design/format";
import { DetectorProvenance } from "./DetectorProvenance";

type Canonical = Schemas["CanonicalAlert"];
type Json = Schemas["JsonValue"];
const object = (value: Json | undefined): Record<string, Json> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, Json> : {};
const display = (value: Json | undefined) => value == null ? "Not provided" : typeof value === "object" ? JSON.stringify(value) : String(value);
const endpoint = (ip: string, port: number | null) => port == null ? ip : `${ip.includes(":") ? `[${ip}]` : ip}:${port}`;

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
      ["Supplied confidence", detector.confidence == null ? "Not provided" : formatPercent(detector.confidence)],
      ...(historical && evidence.mlProbability != null ? [["Historical ML probability", display(evidence.mlProbability)] as const] : []),
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
  return <div className="space-y-4">
    <DetectorProvenance detector={detector} />
    <KeyValues rows={[
      ["Category", detector.detectionCategory ?? "Not provided"],
      ["Source", endpoint(detector.sourceIp, detector.sourcePort)],
      ["Destination", endpoint(detector.destinationIp, detector.destinationPort)],
      ["Protocol", detector.protocol],
      ["Occurred at", detector.occurredAt],
    ]} />
    {!summaryOnly && <>
      {source === "suricata" && <Card title="Suricata Rule Evidence"><KeyValues rows={[
        ["Signature", detector.detectionTitle],
        ["Rule ID", display(detector.structuredEvidence.signatureId)],
        ["Action", display(detector.structuredEvidence.action)],
      ]} /></Card>}
      {legacy && <Card title="Historical Signature Evidence">
        <p className="mb-2 text-xs text-muted">Legacy Flow Detector evidence; separate from current routing and human decisions.</p>
        {Array.isArray(detector.structuredEvidence.signatureRules) && detector.structuredEvidence.signatureRules.length > 0
          ? <ul className="space-y-2 text-sm">{detector.structuredEvidence.signatureRules.map((rule, index) => {
            const fields = object(rule); return <li key={index} className="break-words">{display(fields.name)} <span className="font-mono text-xs text-muted">{display(fields.ruleId ?? fields.rule_id)}</span></li>;
          })}</ul> : <p className="text-sm text-muted">No historical signature matches supplied.</p>}
      </Card>}
      {(source === "xgboost" || legacy) && <ModelEvidence detector={detector} historical={legacy} />}
      {source !== "suricata" && source !== "xgboost" && !legacy && <Card title="Detector Evidence"><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(detector.structuredEvidence, null, 2)}</pre></Card>}
    </>}
  </div>;
}
