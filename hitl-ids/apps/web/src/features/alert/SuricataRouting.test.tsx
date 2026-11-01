import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Schemas } from "../../api/client";
import { jsonResponse, renderApp, stubFetch } from "../../test/renderApp";
import { OperationalEvidence } from "./OperationalEvidence";

const ref = "00000000-0000-4000-8000-000000000001";
const caseRef = "00000000-0000-4000-8000-000000000002";
const record = { sourceRecordRef: "eve:first", sensorId: "sensor-a", timestamp: "2026-10-31T12:00:00+0800", flowId: "18446744073709551615", txId: "0" };
const bundle = { sensorId: "sensor-a", flowId: record.flowId, correlationBasis: "sensor_flow_id", nativeSeverity: 1,
  evidenceTypes: ["alert", "flow", "ssh"], transactionRecords: { "0": [record.sourceRecordRef] },
  relatedSignatures: [
    { sourceRecordRef: "eve:a", timestamp: record.timestamp, signatureId: 1, signature: "Possible SSH Scan", nativeCategory: "Attempted information leak", nativeSeverity: 3, action: "allowed" },
    { sourceRecordRef: "eve:b", timestamp: record.timestamp, signatureId: 2, signature: "Possible SSH Brute Force", nativeCategory: "Attempted administrator privilege gain", nativeSeverity: 1, action: "allowed" },
  ], records: [
    { ...record, eventType: "ssh", raw: { ssh: { client: { software_version: "OpenSSH_9.6" } } } },
    { ...record, sourceRecordRef: "eve:flow", eventType: "flow", raw: { flow: { pkts_toserver: 20 } } },
  ] };
const alert = { detectorEvidence: { detectorSource: "suricata", detectorName: "Suricata", detectionTitle: "Possible SSH Brute Force",
  detectionCategory: "Attempted administrator privilege gain", detectorSeverity: 1, confidence: null, detectorVersion: null,
  sourceIp: "192.0.2.1", destinationIp: "192.0.2.2", sourcePort: 53000, destinationPort: 22, protocol: "TCP", occurredAt: record.timestamp,
  provenance: {}, structuredEvidence: { suricataBundle: bundle }, originalDetectorFields: { events: [] } } } as unknown as Schemas["OperationalAlertV2"];
const view = { operationalAlertRef: ref, title: "Possible SSH Brute Force", detectorName: "Suricata", detectorSource: "suricata", stateVersion: "a".repeat(64),
  state: { handlingRoute: "tier2_case", workflowStage: "investigation", decisionSource: "system_policy", priorityBand: "P1", operationalPriority: 85, reviewRequired: true },
  reviewReasons: ["Classification cannot be resolved safely"], allowedActions: [], caseRef,
  classification: { attackCategory: "unknown_needs_expert", status: "conflict", source: "deterministic_suricata_mapping", policyVersion: "suricata-classification-v1", reasons: ["Conflicting supported attack classes"] },
  systemRouting: { routeClass: "EXPERT_REVIEW_REQUIRED", route: "tier2_case", decisionSource: "system_policy", policyVersion: "system-routing-v1", reasons: ["Attack classification cannot be resolved safely. This is not a maliciousness verdict."] },
  latestDecision: { action: "system_route", decisionSource: "system_policy", actorId: null, reason: "Classification needs expert review", createdAt: record.timestamp } };

describe("correlated Suricata and system routing", () => {
  it("shows every signature, native category/severity, supplied evidence and safe correlation IDs", () => {
    render(<OperationalEvidence alert={alert} />);
    const table = screen.getByRole("table", { name: "Related Suricata signatures" });
    expect(within(table).getByText("Possible SSH Scan")).toBeVisible();
    expect(within(table).getByText("Possible SSH Brute Force")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Flow / Session Evidence" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Application Evidence" })).toBeVisible();
    expect(screen.getByText(/OpenSSH_9.6/)).toBeVisible();
    expect(screen.getByText(record.flowId)).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Anomaly Evidence" })).toBeNull();
    expect(screen.getByText("Unavailable — no validated feature bridge")).toBeVisible();
    expect(screen.queryByText(/\d+%/)).toBeNull();
  });

  it("opens automatic Tier 2 without human approval or writes and attributes its history to system policy", async () => {
    const empty = { items: [], page: { total: 0, offset: 0, limit: 50, returned: 0 } };
    const requests = stubFetch(req => {
      const path = new URL(req.url).pathname;
      if (path.endsWith("/evidence")) return jsonResponse(alert);
      if (path.endsWith("/triage-state")) return jsonResponse(view);
      if (path === "/api/v2/alerts") return jsonResponse({ ...empty, items: [view] });
      if (path.endsWith("/selective-review")) return jsonResponse({ disposition: "must_review", policyEvaluation: {} });
      return jsonResponse(empty);
    });
    renderApp("/analyst/operations?alertRef=" + ref, { session: { username: "g.ang", displayName: "Analyst", role: "security_analyst", token: "test" } });
    expect(await screen.findByRole("heading", { name: "System Routing" })).toBeVisible();
    expect(await screen.findByText("Unknown / Needs Expert")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Tier 2 Case" })).toHaveAttribute("href", "/analyst/tier2-cases/" + caseRef);
    expect(screen.queryByRole("button", { name: "Approve Tier 2" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Escalate to Tier 2" })).toBeNull();
    expect(screen.queryByText(/Human routing decision|Tier 2 Recommended/)).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "History & Notes" }));
    expect(screen.getByRole("region", { name: "Operational decision history" })).toHaveTextContent("System Policy");
    expect(screen.getByRole("region", { name: "Operational decision history" })).not.toHaveTextContent("Actor #");
    expect(requests.every(req => req.method === "GET")).toBe(true);
  });
});
