import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { OperationalEvidence, flowShortName } from "./OperationalEvidence";

// C4 (plan S7-03, S7-05; layout approved 2026-11-08). Field paths measured on the routed demo copy
// (analysis/phase-c/c4_fields.py): AL short name in sourceRecordReference, rule clauses in
// signatureRules[].matched_conditions (snake_case), combined explanation in structuredEvidence.explanation,
// agreement in evidenceClass, legacy confidence in sourceProvenance.legacyFusionConfidence.
const rule = { rule_id: "SIG-FTP-BRUTE-FORCE", name: "FTP Brute Force Flow Pattern", severity: "Medium", attack_category: "Brute Force",
  version: "s4b-1", matched_conditions: [
    { feature: "destinationPort", expected: 21, observed: 21 },
    { feature: "flowPacketsPerSecond", expected: { min: 10 }, observed: 666666.6666666666 },
  ] };
const explanation = "A signature rule and the model agree on Brute Force. The rule's conditions below can be checked against the flow.";

function flowAlert(evidenceClass: string, over: { confidence?: number | null; rules?: unknown[]; fusion?: number } = {}) {
  return {
    sourceKind: "legacy_flow_alert",
    sourceProvenance: { sourceKind: "legacy_flow_alert", datasetId: 1, runId: 1, legacyAlertRef: "10ee4c5f-c25d-4e4d-96ae-f870157700c4",
      detectionScore: 100, legacyFusionConfidence: over.fusion ?? 0.99999261 },
    detectorEvidence: { detectorSource: "current_flow", detectorName: "Signature + XGBoost", detectorVersion: "s4b-1",
      detectionTitle: "Brute Force", detectionCategory: "Brute Force", detectorSeverity: "Medium",
      confidence: over.confidence === undefined ? null : over.confidence, evidenceClass,
      sourceIp: "192.0.2.1", destinationIp: "192.0.2.2", sourcePort: 53000, destinationPort: 21, protocol: "TCP",
      occurredAt: "2017-07-05T10:00:00Z", sourceRecordReference: "AL-01958", provenance: {}, originalDetectorFields: {},
      structuredEvidence: { explanation, signatureRules: over.rules ?? [rule], mlPredictedClass: "Brute Force", detectionScore: 100 } },
  } as unknown as Schemas["OperationalAlertV2"];
}

describe("C4 flow alert evidence", () => {
  it("shows the legacy fusion confidence when the detector confidence is missing (S7-05)", () => {
    render(<OperationalEvidence alert={flowAlert("corroborated")} />);
    const provenance = screen.getByRole("region", { name: "Detector provenance" });
    expect(within(provenance).getByText("100.0%")).toBeVisible();
    expect(within(provenance).queryByText("Not provided")).not.toBeInTheDocument();
  });

  it("prefers the legacy fusion confidence over a supplied detector confidence for a flow alert", () => {
    render(<OperationalEvidence alert={flowAlert("ml_only", { confidence: 0.5, fusion: 0.9989171 })} />);
    expect(within(screen.getByRole("region", { name: "Detector provenance" })).getByText("99.9%")).toBeVisible();
  });

  it("shows each rule clause with the required and the observed value", () => {
    render(<OperationalEvidence alert={flowAlert("corroborated")} />);
    const table = screen.getByRole("table", { name: "Conditions for SIG-FTP-BRUTE-FORCE" });
    expect(within(table).getByText("destinationPort")).toBeVisible();
    expect(within(table).getByText("= 21")).toBeVisible();
    expect(within(table).getByText("≥ 10")).toBeVisible();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("shows the combined explanation", () => {
    render(<OperationalEvidence alert={flowAlert("corroborated")} />);
    expect(screen.getByRole("region", { name: "Combined explanation" })).toHaveTextContent(explanation);
  });

  it.each([
    ["corroborated", "Rule and model agree"],
    ["signature_override", "Rule overrides the model"],
    ["ml_only", "Model only — no rule fired"],
    ["none", "Neither the rule nor the model flagged this flow"],
  ])("states the rule and model agreement for %s", (evidenceClass, text) => {
    render(<OperationalEvidence alert={flowAlert(evidenceClass, { rules: evidenceClass === "corroborated" ? [rule] : [] })} />);
    expect(within(screen.getByRole("region", { name: "Detector provenance" })).getByText(text)).toBeVisible();
  });

  it("shows agreement and explanation on the Overview summary too", () => {
    render(<OperationalEvidence alert={flowAlert("corroborated")} summaryOnly />);
    expect(screen.getByText("Rule and model agree")).toBeVisible();
    expect(screen.getByRole("region", { name: "Combined explanation" })).toBeVisible();
    expect(screen.queryByRole("table", { name: /Conditions for/ })).not.toBeInTheDocument();
  });

  it("gives the AL short name for a flow alert and nothing for other sources", () => {
    expect(flowShortName(flowAlert("corroborated"))).toBe("AL-01958");
    const suricata = { ...flowAlert("corroborated"), sourceKind: "external_detector_alert",
      detectorEvidence: { ...flowAlert("corroborated").detectorEvidence, detectorSource: "suricata", sourceRecordReference: "eve:1" } } as unknown as Schemas["OperationalAlertV2"];
    expect(flowShortName(suricata)).toBeNull();
    const odd = { ...flowAlert("corroborated"), detectorEvidence: { ...flowAlert("corroborated").detectorEvidence, sourceRecordReference: "fixture:1" } } as unknown as Schemas["OperationalAlertV2"];
    expect(flowShortName(odd)).toBeNull();
  });
});
