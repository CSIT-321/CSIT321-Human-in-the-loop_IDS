import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { DetectorEvidence, DetectorProvenance } from "./DetectorProvenance";
import { ALERT_DETAIL } from "../../pages/analyst/__tests__/fixtures";

const detector: Schemas["CanonicalAlert"] = {
  canonicalAlertId: "8f22e741-c776-4999-b347-17a0c42aca6a",
  occurredAt: "2026-09-18T00:00:00Z",
  occurredAtTimezoneOffset: "+00:00",
  detectorSource: "suricata", detectorName: "Suricata", detectorVersion: "7.0.14",
  detectionTitle: "TEST Network signature", detectionCategory: "Policy",
  detectorSeverity: 2, confidence: null, sourceIp: "192.0.2.1",
  destinationIp: "198.51.100.1", sourcePort: null, destinationPort: null, protocol: "TCP",
  evidenceClass: "external_signature", structuredEvidence: {}, provenance: {},
  sourceRecordReference: "fixture:1", originalDetectorFields: {},
};

describe("detector provenance", () => {
  it("shows native severity and missing confidence without inventing zero", () => {
    render(<DetectorProvenance detector={detector} />);
    expect(screen.getByText("Suricata")).toBeVisible();
    expect(screen.getByText("2")).toBeVisible();
    expect(screen.getByText("Not provided")).toBeVisible();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
  it("shows provided model confidence independently of severity", () => {
    render(<DetectorProvenance detector={{ ...detector, detectorSource: "current_flow",
      detectorName: "Signature + XGBoost", detectorSeverity: "Medium", confidence: 0.992 }} />);
    expect(screen.getByText("Legacy Flow Detector")).toBeVisible();
    expect(screen.getByText("Medium")).toBeVisible();
    expect(screen.getByText(/99.2/)).toBeVisible();
  });
  it("never renders legacy fusion or ML panels on Suricata, even with stale flow fields", () => {
    render(<DetectorEvidence detail={{ ...ALERT_DETAIL, detector }} />);
    expect(screen.queryByText(/TreeSHAP|Model prediction|Combined explanation|Signature evidence/i)).toBeNull();
  });
  it("shows the supplied XGBoost model, prediction and confidence", () => {
    render(<DetectorProvenance detector={{ ...detector, detectorSource: "xgboost", detectorName: "XGBoost",
      detectorVersion: "model-v7", confidence: .82, structuredEvidence: { mlPredictedClass: "Port Scan" } }} />);
    expect(screen.getByText("XGBoost")).toBeVisible();
    expect(screen.getByText("XGBoost / model-v7")).toBeVisible();
    expect(screen.getByText("Port Scan")).toBeVisible();
    expect(screen.getByText(/82/)).toBeVisible();
  });
  it("retains historical evidence and only shows TreeSHAP when supplied", () => {
    const result = render(<DetectorEvidence detail={ALERT_DETAIL} />);
    expect(screen.getByText(/Legacy detector evidence/)).toBeVisible();
    expect(screen.getByText(/Contributions are TreeSHAP/)).toBeVisible();
    result.rerender(<DetectorEvidence detail={{ ...ALERT_DETAIL,
      detector: { ...detector, detectorSource: "xgboost" },
      ml: { ...ALERT_DETAIL.ml, topSupporting: [], topOpposing: [] } }} />);
    expect(screen.queryByText(/TreeSHAP|Combined explanation/)).toBeNull();
  });
  it("supports legacy API responses without the additive field", () => {
    render(<DetectorProvenance detector={undefined} />);
    expect(screen.queryByRole("region", { name: "Detector provenance" })).not.toBeInTheDocument();
  });
});
