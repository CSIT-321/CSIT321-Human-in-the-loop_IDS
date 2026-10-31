import type { Schemas } from "../../api/client";
import { formatPercent } from "../../design/format";
import { EvidencePanelCard } from "./EvidencePanelCard";
import { SignaturePanelCard } from "./SignaturePanelCard";
import { MlPanelCard } from "./MlPanelCard";

type Detector = Schemas["CanonicalAlert"];

export function detectorKind(detector: Detector | null | undefined) {
  // Missing provenance is the original, historical flow API. Do not infer fusion for other sources.
  if (!detector || detector.detectorSource === "current_flow") return "legacy";
  if (detector.detectorSource.toLowerCase() === "suricata") return "suricata";
  if (detector.detectorSource.toLowerCase() === "xgboost") return "xgboost";
  return "other";
}

/** Keep the original evidence cards, but only for the detector that actually supplied them. */
export function DetectorEvidence({ detail, layout = "workstation" }: { detail: Schemas["AlertDetail"]; layout?: "workstation" | "detail" }) {
  const kind = detectorKind(detail.detector);
  if (kind === "legacy" && layout === "detail") return <>
    <SignaturePanelCard signature={detail.signature} />
    <MlPanelCard ml={detail.ml} />
    <EvidencePanelCard evidence={detail.evidence} />
  </>;
  if (kind === "legacy") return <>
    <p className="text-xs text-muted">Legacy detector evidence — historical Signature + XGBoost flow results.</p>
    <EvidencePanelCard evidence={detail.evidence} />
    <div className="grid gap-4 2xl:grid-cols-2">
      <SignaturePanelCard signature={detail.signature} />
      <MlPanelCard ml={detail.ml} />
    </div>
  </>;
  if (kind === "xgboost" && detail.ml.predictedClass !== null &&
      ((detail.ml.topSupporting?.length ?? 0) + (detail.ml.topOpposing?.length ?? 0) > 0)) {
    return <MlPanelCard ml={detail.ml} />;
  }
  return null;
}

export function DetectorProvenance({ detector }: { detector: Schemas["CanonicalAlert"] | null | undefined }) {
  if (!detector) return null;
  const kind = detectorKind(detector);
  const prediction = detector.structuredEvidence.mlPredictedClass ?? detector.structuredEvidence.predictedAttackType;
  return (
    <section aria-label="Detector provenance" className="border-b border-border pb-3">
      <dl className="grid gap-2 text-xs sm:grid-cols-2">
        <div><dt className="text-muted">Detector Source</dt><dd>{kind === "legacy" ? "Legacy Flow Detector" : kind === "suricata" ? "Suricata" : kind === "xgboost" ? "XGBoost" : detector.detectorName}</dd></div>
        <div><dt className="text-muted">{kind === "xgboost" ? "Model" : "Detector Name/Version"}</dt><dd>{detector.detectorName} / {detector.detectorVersion ?? "Not provided"}</dd></div>
        <div><dt className="text-muted">Detection</dt><dd className="break-words">{detector.detectionTitle}</dd></div>
        {kind === "xgboost" && <div><dt className="text-muted">Prediction</dt><dd>{typeof prediction === "string" ? prediction : "Not provided"}</dd></div>}
        <div><dt className="text-muted">Native Severity</dt><dd>{detector.detectorSeverity}</dd></div>
        <div><dt className="text-muted">Confidence</dt><dd>{detector.confidence == null ? "Not provided" : formatPercent(detector.confidence)}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-muted">Native Severity and Confidence are detector evidence, separate from Operational Priority and workflow Tier.</p>
    </section>
  );
}
