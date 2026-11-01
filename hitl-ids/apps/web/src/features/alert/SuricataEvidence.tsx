import type { Schemas } from "../../api/client";
import { Card, KeyValues } from "../../components/ui";

type Json = Schemas["JsonValue"];
export const asObject = (value: Json | undefined): Record<string, Json> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, Json> : {};
const rows = (value: Json | undefined) => Array.isArray(value) ? value.map(asObject) : [];
const text = (value: Json | undefined) => value == null ? "Not provided" : typeof value === "object" ? JSON.stringify(value) : String(value);

function RecordGroup({ title, records }: { title: string; records: Record<string, Json>[] }) {
  if (!records.length) return null;
  return <Card title={title}><div className="space-y-3">{records.map(record => <div key={text(record.sourceRecordRef)} className="space-y-2">
    <p className="text-xs font-semibold uppercase">{text(record.eventType)} <span className="font-normal normal-case text-muted">· {text(record.timestamp)}{record.txId != null ? ` · Transaction ${text(record.txId)}` : ""}</span></p>
    <KeyValues rows={Object.entries(asObject(asObject(record.raw)[text(record.eventType)])).map(([key, value]) => [key.replaceAll("_", " "), <span className="break-all" key={key}>{text(value)}</span>] as const)} />
  </div>)}</div></Card>;
}

export function SuricataEvidence({ detector, summaryOnly }: { detector: Schemas["CanonicalAlert"]; summaryOnly: boolean }) {
  const bundle = asObject(detector.structuredEvidence.suricataBundle);
  const signatures = rows(bundle.relatedSignatures);
  const records = rows(bundle.records);
  return <>
    <Card title="Suricata Detection Summary"><KeyValues rows={[
      ["Primary signature", detector.detectionTitle],
      ["Related Signatures", String(signatures.length)],
      ["Evidence Types", Array.isArray(bundle.evidenceTypes) ? bundle.evidenceTypes.map(text).join(" · ") : "Not provided"],
      ["Native Severity", `${text(bundle.nativeSeverity)} (highest-priority matching rule)`],
      ["Suricata confidence", "Not provided"],
      ["XGBoost supporting evidence", "Unavailable — no validated feature bridge"],
    ]} /></Card>
    {!summaryOnly && <>
      <Card title="Related Signatures"><div className="overflow-x-auto"><table aria-label="Related Suricata signatures" className="w-full text-left text-xs">
        <thead><tr>{["Timestamp", "Signature ID", "Signature", "Native Category", "Native Severity", "Action"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead>
        <tbody>{signatures.map(signature => <tr key={text(signature.sourceRecordRef)} className="border-t border-border">{["timestamp", "signatureId", "signature", "nativeCategory", "nativeSeverity", "action"].map(key => <td className="p-2" key={key}>{text(signature[key])}</td>)}</tr>)}</tbody>
      </table></div></Card>
      <RecordGroup title="Flow / Session Evidence" records={records.filter(record => record.eventType === "flow")} />
      <RecordGroup title="Application Evidence" records={records.filter(record => ["http", "dns", "tls", "ssh", "fileinfo"].includes(text(record.eventType)))} />
      <RecordGroup title="Anomaly Evidence" records={records.filter(record => record.eventType === "anomaly")} />
      <Card title="Correlation Details"><KeyValues rows={[
        ["Sensor", text(bundle.sensorId)], ["Capture scope", bundle.captureScope == null ? "Historical unscoped evidence" : text(bundle.captureScope)], ["flow_id", text(bundle.flowId)],
        ["Correlation", text(bundle.correlationBasis).replaceAll("_", " ")],
        ["Transaction IDs", Object.keys(asObject(bundle.transactionRecords)).join(", ") || "Not provided"],
      ]} /><p className="mt-3 text-xs text-muted">Same-flow signatures are supporting evidence within one detection. They do not count as independent campaign alerts.</p></Card>
      <details className="text-xs"><summary className="cursor-pointer text-accent">Raw / Technical Evidence</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(detector.originalDetectorFields, null, 2)}</pre></details>
    </>}
  </>;
}
