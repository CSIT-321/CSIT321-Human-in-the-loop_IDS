import type { Schemas } from "../../api/client";
import { DetectorProvenance } from "./DetectorProvenance";
import { MlPanelCard } from "./MlPanelCard";
import { SignaturePanelCard } from "./SignaturePanelCard";
export function detectorLabel(detector: Schemas["CanonicalAlert"]) {
  return detector.detectorSource === "current_flow" ? "Legacy Flow Detector" : detector.detectorName;
}
export function DetectorEvidence({detector, ml, signature}: {
  detector?: Schemas["CanonicalAlert"] | null; ml?: Schemas["MlPanel"]; signature?: Schemas["SignaturePanel"];
}) {
  const legacy = !detector || detector.detectorSource === "current_flow";
  const evidence = detector?.structuredEvidence;
  const treeShap = evidence?.treeShap;
  const machine = /xgboost|xgb|machine|^ml$/i.test(`${detector?.detectorSource} ${detector?.detectorName}`);
  return <div className="space-y-4">
    <DetectorProvenance detector={detector}/>
    {legacy && <p className="text-sm text-warn">Legacy detector evidence — Signature + XGBoost. Historical compatibility evidence.</p>}
    {machine && <p className="text-sm text-muted">Supported secondary / historical ML detector. Explanation availability follows the supplied evidence.</p>}
    {legacy && signature && <SignaturePanelCard signature={signature}/>}
    {(legacy || machine) && ml && <MlPanelCard ml={ml}/>}
    {(legacy || machine) && detector && <section className="space-y-2"><h3 className="font-semibold">XGBoost / ML evidence</h3><p className="text-sm">Model: {detector.detectorVersion ?? "Not provided"}</p><p className="text-sm">Prediction: {String(evidence?.mlPredictedClass ?? detector.detectionCategory ?? "Not provided")}</p><p className="text-sm">Explanation: {treeShap && typeof treeShap === "object" && !Array.isArray(treeShap) && "status" in treeShap && treeShap.status === "available" ? "TreeSHAP available" : "Availability not provided"}</p>{treeShap != null && <details><summary>Model explanation evidence</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(treeShap,null,2)}</pre></details>}</section>}
    {legacy && detector && <details><summary>Legacy signature evidence</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(evidence?.signatureRules ?? [],null,2)}</pre></details>}
    {detector && <><dl className="grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-muted">Source endpoint</dt><dd>{detector.sourceIp}:{detector.sourcePort ?? "No port"}</dd></div><div><dt className="text-muted">Destination endpoint</dt><dd>{detector.destinationIp}:{detector.destinationPort ?? "No port"}</dd></div><div><dt className="text-muted">Category / Prediction</dt><dd>{detector.detectionCategory ?? "Not provided"}</dd></div><div><dt className="text-muted">Occurred at</dt><dd>{detector.occurredAt}</dd></div></dl>
    <details><summary>Detector evidence snapshot</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(detector.originalDetectorFields,null,2)}</pre></details></>}
  </div>;
}
