import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { DetectorEvidence } from "./DetectorEvidence";
import { DetectorProvenance } from "./DetectorProvenance";

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
  it("supports legacy API responses without the additive field", () => {
    render(<DetectorProvenance detector={undefined} />);
    expect(screen.queryByRole("region", { name: "Detector provenance" })).not.toBeInTheDocument();
  });
});

it("shows Suricata evidence without legacy Signature or ML panels", () => {
  render(<DetectorEvidence detector={detector}/>);
  expect(screen.getByText("Suricata")).toBeVisible();
  expect(screen.queryByText("XGBoost / ML evidence")).not.toBeInTheDocument();
  expect(screen.queryByText("Legacy signature evidence")).not.toBeInTheDocument();
});
it("shows XGBoost confidence, model and available TreeSHAP as secondary evidence", () => {
  render(<DetectorEvidence detector={{...detector,detectorSource:"xgboost",detectorName:"XGBoost",detectorVersion:"xgb-8class-20260911",confidence:1,detectionCategory:"Infiltration",structuredEvidence:{mlPredictedClass:"Infiltration",treeShap:{status:"available"}}}}/>);
  expect(screen.getByText(/Supported secondary/)).toBeVisible();
  expect(screen.getByText("100.0%")).toBeVisible();
  expect(screen.getByText("Explanation: TreeSHAP available")).toBeVisible();
  expect(screen.queryByText("Legacy signature evidence")).not.toBeInTheDocument();
});
it("retains fused signature and ML evidence under an explicit legacy boundary", () => {
  render(<DetectorEvidence detector={{...detector,detectorSource:"current_flow",detectorName:"Signature + XGBoost",structuredEvidence:{signatureRules:[{name:"Historical rule"}],mlPredictedClass:"Infiltration"}}}/>);
  expect(screen.getByText("Legacy Flow Detector")).toBeVisible();
  expect(screen.getByText("Legacy signature evidence")).toBeVisible();
  expect(screen.getByText("XGBoost / ML evidence")).toBeVisible();
});
