import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { DetectorProvenance } from "./DetectorProvenance";

const detector: Schemas["CanonicalAlert"] = {
  canonicalAlertId: "8f22e741-c776-4999-b347-17a0c42aca6a",
  occurredAt: "2026-09-18T00:00:00Z",
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
    expect(screen.getByText("Current Flow Detector")).toBeVisible();
    expect(screen.getByText("Medium")).toBeVisible();
    expect(screen.getByText(/99.2/)).toBeVisible();
  });
  it("supports legacy API responses without the additive field", () => {
    render(<DetectorProvenance detector={undefined} />);
    expect(screen.queryByRole("region", { name: "Detector provenance" })).not.toBeInTheDocument();
  });
});
