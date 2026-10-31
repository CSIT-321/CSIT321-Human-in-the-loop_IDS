import type { Schemas } from "../../api/client";
import { formatPercent } from "../../design/format";

export function DetectorProvenance({ detector }: { detector: Schemas["CanonicalAlert"] | null | undefined }) {
  if (!detector) return null;
  return (
    <section aria-label="Detector provenance" className="border-b border-border pb-3">
      <dl className="grid gap-2 text-xs sm:grid-cols-2">
        <div><dt className="text-muted">Detector Source</dt><dd>{detector.detectorSource === "current_flow" ? "Legacy Flow Detector" : detector.detectorName}</dd></div>
        <div><dt className="text-muted">Detector Name/Version</dt><dd>{detector.detectorName} / {detector.detectorVersion ?? "Not provided"}</dd></div>
        <div><dt className="text-muted">Detection Signature or Model</dt><dd className="break-words">{detector.detectionTitle}</dd></div>
        <div><dt className="text-muted">Native Severity</dt><dd>{detector.detectorSeverity}</dd></div>
        <div><dt className="text-muted">Confidence</dt><dd>{detector.confidence == null ? "Not provided" : formatPercent(detector.confidence)}</dd></div>
      </dl>
    </section>
  );
}
