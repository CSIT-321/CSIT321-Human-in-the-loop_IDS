import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderApp, stubFetch, jsonResponse } from "../../test/renderApp";

const ref = "fe130e6f-af86-4fc6-89f2-bc76b6cad68b";
const session = { username: "g.ang", displayName: "Analyst", role: "security_analyst" as const, token: "test" };
const record = {
  caseRef: ref, primaryOperationalAlertRef: ref, title: "Connection investigation", ownerActorId: 1,
  createdByActorId: 1, createdAt: "2026-10-31T00:00:00Z", updatedAt: "2026-10-31T00:00:00Z", status: "open", revision: 1,
  snapshot: {
    detector: { detectorName: "Suricata", detectorSource: "suricata", nativeSeverity: 2, detectorConfidence: null,
      detectionTitle: "Suspicious connection", detectionCategory: "Potentially Bad Traffic",
      sourceIp: "192.0.2.1", destinationIp: "198.51.100.2", sourcePort: null, destinationPort: 443,
      detectorEvidence: { confidence: null } },
    triage: { priorityBand: "P2", operationalPriority: 65, triagePolicyVersion: "operational-triage-v1",
      tier2RecommendationReasons: ["Unresolved by Tier 1"] },
    routingDecision: { eventType: "V2_MANUAL_ESCALATION", actorId: 1 },
    escalationReason: "Needs deeper review", tier1HandoffSummary: "Investigate source host", creationReason: "Open case",
  },
};
const relatedRef = "ea130e6f-af86-4fc6-89f2-bc76b6cad68b";
const assistance = {
  caseRef: ref, assistancePolicyVersion: "tier2-assistance-v1", correlationWindowHours: 24, maximumRelated: 20,
  brief: {
    atCaseCreation: record.snapshot, classificationAtAdmission: { status: "unmapped", attackCategory: "unknown_needs_expert", conflictingCategories: [], matches: [], reasons: ["Unmapped signature"], policyVersion: "suricata-classification-v3", source: "deterministic_suricata_mapping" },
    systemRoutingAtAdmission: { routeClass: "EXPERT_REVIEW_REQUIRED", reasons: ["Unknown requires expert review"] },
    suricataEvidenceAtCreation: null, currentCaseStatus: "open", currentCaseRevision: 1,
    currentTier1Verdict: null, tier1VerdictExplanation: "Not recorded / not required for automatic Tier 2 routing.",
    currentTrustedContext: { fields: [], evaluatedAt: "2026-11-01T00:00:00Z", resolverVersion: "context-resolver-v1" },
    uncertainties: ["Unknown / Needs Expert. Maliciousness is not established.", "Optional evidence not recorded: http, dns, tls, ssh."],
  },
  relatedAlerts: [{operationalAlertRef: relatedRef, title: "Potential related authentication", sourceIp: "192.0.2.1", destinationIp: "198.51.100.2", occurredAt: "2026-10-31T00:01:00Z", attackCategory: "brute_force", priorityBand: "P2", operationalPriority: 65, handlingRoute: "tier1_review", relationshipReasons: ["Same source IP", "Within ±24 hours of primary alert"]}],
  suggestedSteps: ["Inspect primary signatures; assistance does not execute actions."],
};
const empty = { items: [], page: { total: 0, returned: 0, offset: 0, limit: 50 } };

describe("Tier 2 cases", () => {
  it("keeps resolved Case history visible and hides all investigation, linking, response and learning write controls", async () => {
    const closed={...record,status:"resolved",revision:4,resolution:{eventId:10,caseRef:ref,actorId:1,actorName:"Analyst",reason:"Investigation completed",createdAt:"2026-11-02T00:00:00Z",previousStatus:"investigating",newStatus:"resolved",caseRevision:4,requestId:ref,
      conclusion:{eventId:9,finding:"expected_activity",finalAttackCategory:null},responses:[]}};
    const event={id:10,eventType:"V2_TIER2_CASE_RESOLVED",decisionSource:"analyst",actorId:1,createdAt:closed.resolution.createdAt,reason:closed.resolution.reason,resolution:closed.resolution};
    stubFetch(r=>jsonResponse(r.url.includes("/assistance")?assistance:r.url.includes("/responses")?{...empty,caseRevision:4}:r.url.includes("/events")?{...empty,items:[event]}:closed));
    renderApp("/analyst/tier2-cases/"+ref,{session});
    expect(await screen.findByText("Resolved")).toBeVisible();
    expect(await screen.findByRole("heading",{name:"Investigation Brief"})).toBeVisible();
    for(const tab of ["Investigation Notes","Investigation Conclusion","Linked Alerts","Audit Timeline"]){
      await userEvent.click(screen.getByRole("tab",{name:tab}));
      expect(screen.queryByLabelText("Investigation note")).not.toBeInTheDocument();
      expect(screen.queryByRole("button",{name:"Record Investigation Conclusion"})).not.toBeInTheDocument();
      expect(screen.queryByRole("button",{name:"Link alert"})).not.toBeInTheDocument();
      expect(screen.queryByRole("button",{name:"Start investigation"})).not.toBeInTheDocument();
    }
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Case Resolved");
    expect(screen.queryByRole("button",{name:"Review link to Case"})).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Proposal reason")).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Use Expert Conclusion as Triage Memory Evidence"})).not.toBeInTheDocument();
  });
  it("lists formal cases only and handles an empty list", async () => {
    const seen = stubFetch(() => jsonResponse(empty));
    renderApp("/analyst/tier2-cases", { session });
    expect(await screen.findByText("No Tier 2 cases.")).toBeInTheDocument();
    expect(seen.some(request => new URL(request.url).pathname === "/api/v2/alerts")).toBe(false);
  });

  it("preserves handoff and separates severity from priority and response", async () => {
    stubFetch(request => jsonResponse(request.url.includes("/assistance") ? assistance : request.url.includes("/responses") ? { ...empty,caseRevision:1 } : request.url.includes("/events") ? empty : record));
    renderApp("/analyst/tier2-cases/" + ref, { session });
    expect(await screen.findByText("Investigate source host")).toBeInTheDocument();
    expect(screen.getByText("Native Severity: 2")).toBeInTheDocument();
    expect(screen.getByText("P2 / 65")).toBeInTheDocument();
    expect(screen.getByText("Confidence: Not provided")).toBeInTheDocument();
    expect(await screen.findByText("No response recommendations.")).toBeInTheDocument();
    expect(screen.getByText("APPROVAL DOES NOT EXECUTE THE ACTION.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add investigation note" })).toBeDisabled();
  });

  it("evaluator can inspect but cannot append investigation records", async () => {
    stubFetch(request => jsonResponse(request.url.includes("/assistance") ? assistance : request.url.includes("/responses") ? { ...empty,caseRevision:1 } : request.url.includes("/events") ? empty : record));
    renderApp("/evaluator/tier2-cases/" + ref, { session: { ...session, role: "evaluator" } });
    await screen.findByText("Investigate source host");
    await screen.findByRole("heading", { name: "Investigation Brief" });
    expect(screen.queryByRole("button", { name: "Review link to Case" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Investigation note")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Investigation Conclusion" }));
    expect(screen.queryByRole("button", { name: "Record Investigation Conclusion" })).not.toBeInTheDocument();
  });

  it("records notes with a revision and retains retry identity on conflicts", async () => {
    const bodies: unknown[] = [];
    stubFetch(async request => {
      if (request.method === "POST") {
        bodies.push(await request.json());
        return jsonResponse({ error: { code: "CASE_CONFLICT", message: "Case changed; refresh" } }, 409);
      }
      return jsonResponse(request.url.includes("/assistance") ? assistance : request.url.includes("/responses") ? { ...empty,caseRevision:1 } : request.url.includes("/events") ? empty : record);
    });
    renderApp("/analyst/tier2-cases/" + ref, { session });
    await userEvent.type(await screen.findByLabelText("Investigation note"), "Affected account identified");
    await userEvent.click(screen.getByRole("button", { name: "Add investigation note" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Case changed");
    await userEvent.click(screen.getByRole("button", { name: "Add investigation note" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(bodies[0]).toMatchObject({ expectedRevision: 1, reason: "Affected account identified" });
  });

  it("shows advisory brief and preselects a link without writing until explicit confirmation", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    const bodies: Record<string, unknown>[] = [];
    let revision = 1;
    const seen = stubFetch(async request => {
      if (request.method === "POST") {
        bodies.push(await request.json() as Record<string, unknown>); revision = 2;
        return jsonResponse({ case: { ...record, revision }, eventId: 8, replayed: false });
      }
      if (request.url.includes("/assistance")) return jsonResponse({ ...assistance, relatedAlerts: revision === 1 ? assistance.relatedAlerts : [] });
      return jsonResponse(request.url.includes("/responses") ? { ...empty, caseRevision: revision } : request.url.includes("/events") ? empty : record);
    });
    renderApp("/analyst/tier2-cases/" + ref, { session });
    expect(await screen.findByRole("heading", { name: "Investigation Brief" })).toBeVisible();
    expect(screen.getByText("At Case Creation")).toBeVisible();
    expect(screen.getByText("Not recorded / not required for automatic Tier 2 routing.")).toBeVisible();
    expect(screen.getByText("Optional evidence not recorded: http, dns, tls, ssh.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Potential related authentication" })).toHaveAttribute("href", "/analyst/v2-triage?alertRef=" + relatedRef);
    expect(screen.getByText("Same source IP")).toBeVisible();
    expect(screen.getByText("Inspect primary signatures; assistance does not execute actions.")).toBeVisible();
    expect(bodies).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Review link to Case" }));
    expect(screen.getByLabelText("Operational alert UUID")).toHaveValue(relatedRef);
    expect(screen.getByRole("button", { name: "Link alert" })).toBeDisabled();
    expect(bodies).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Decision reason"), "Reviewed source relationship");
    await userEvent.click(screen.getByRole("button", { name: "Link alert" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ operationalAlertRef: relatedRef, expectedRevision: 1, reason: "Reviewed source relationship" });
    expect(typeof bodies[0]?.requestId).toBe("string");
    expect(await screen.findByText("No eligible related alerts in this window.")).toBeVisible();
    expect(seen.filter(request => request.method === "POST").every(request => request.url.endsWith("/alerts"))).toBe(true);
  });

  it("renders API failures without an empty-success screen", async () => {
    stubFetch(() => jsonResponse({ error: { code: "OFFLINE", message: "Database unavailable" } }, 503));
    renderApp("/analyst/tier2-cases", { session });
    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
    expect(screen.queryByText("No Tier 2 cases.")).not.toBeInTheDocument();
  });

  it("requires an explicit human category, preserves system classification and displays conclusion history", async () => {
    const bodies: Record<string, unknown>[] = [];
    let saved = false;
    const conclusion = { eventId: 9, caseRef: ref, finding: "confirmed_malicious", finalAttackCategory: "infiltration", actorId: 1,
      reason: "Expert corroborated infiltration", createdAt: "2026-11-02T00:00:00Z", caseRevision: 2,
      requestId: ref, systemClassification: assistance.brief.classificationAtAdmission, supersedesEventId: null, recordKind: "investigation_conclusion" };
    const event = { id: 9, eventType: "V2_TIER2_INVESTIGATION_CONCLUSION_RECORDED", decisionSource: "analyst", actorId: 1,
      createdAt: conclusion.createdAt, reason: conclusion.reason, finding: conclusion.finding, conclusion };
    const seen = stubFetch(async request => {
      if (request.method === "POST") { bodies.push(await request.json() as Record<string, unknown>); saved = true;
        return jsonResponse({ case: { ...record, revision: 2, systemAttackClassification: conclusion.systemClassification, latestConclusion: conclusion }, eventId: 9, replayed: false }); }
      return jsonResponse(request.url.includes("/assistance") ? assistance : request.url.includes("/responses") ? { ...empty, caseRevision: saved ? 2 : 1 } :
        request.url.includes("/events") ? saved ? { ...empty, items: [event] } : empty : { ...record, systemAttackClassification: conclusion.systemClassification });
    });
    renderApp("/analyst/tier2-cases/" + ref, { session });
    await userEvent.click(await screen.findByRole("tab", { name: "Investigation Conclusion" }));
    await userEvent.selectOptions(screen.getByLabelText("Human Investigation Finding"), "confirmed_malicious");
    const category = screen.getByLabelText("Human Final Attack Classification");
    expect(category).toHaveValue(""); expect(category).toBeRequired();
    expect(within(category).queryByRole("option", { name: "Unknown / Needs Expert" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Investigation Reason"), conclusion.reason);
    expect(screen.getByRole("button", { name: "Record Investigation Conclusion" })).toBeDisabled();
    await userEvent.selectOptions(category, "infiltration");
    await userEvent.click(screen.getByRole("button", { name: "Record Investigation Conclusion" }));
    const latest = await screen.findByRole("region", { name: "Latest Human Investigation Conclusion" });
    expect(latest).toHaveTextContent("Human Final Attack Classification: Infiltration");
    expect(screen.getByRole("region", { name: "Case summary" })).toHaveTextContent("System Attack Classification: Unknown / Needs Expert");
    expect(bodies[0]).toMatchObject({ expectedRevision: 1, finding: "confirmed_malicious", finalAttackCategory: "infiltration", reason: conclusion.reason });
    expect(await screen.findByRole("tabpanel")).toHaveTextContent("Human Final Attack Classification: Infiltration");
    expect(seen.filter(r => r.method === "POST").map(r => new URL(r.url).pathname)).toEqual([`/api/v2/tier2/cases/${ref}/conclusions`]);
    expect(seen.filter(r => r.url.includes("/responses")).length).toBeGreaterThan(1);
  });

  it("clears category for Expected Activity and preserves retry identity until the conclusion changes", async () => {
    const bodies: Record<string, unknown>[] = [];
    stubFetch(async request => {
      if (request.method === "POST") { bodies.push(await request.json() as Record<string, unknown>); return jsonResponse({ error: { code: "CASE_CONFLICT", message: "Refresh conclusion" } }, 409); }
      return jsonResponse(request.url.includes("/assistance") ? assistance : request.url.includes("/responses") ? { ...empty,caseRevision:1 } : request.url.includes("/events") ? empty : record);
    });
    renderApp("/analyst/tier2-cases/" + ref, { session });
    await userEvent.click(await screen.findByRole("tab", { name: "Investigation Conclusion" }));
    await userEvent.selectOptions(screen.getByLabelText("Human Final Attack Classification"), "web_attack");
    await userEvent.selectOptions(screen.getByLabelText("Human Investigation Finding"), "expected_activity");
    expect(screen.getByLabelText("Human Final Attack Classification")).toBeDisabled();
    expect(screen.getByLabelText("Human Final Attack Classification")).toHaveValue("");
    await userEvent.type(screen.getByLabelText("Investigation Reason"), "Authorized expected activity");
    await userEvent.click(screen.getByRole("button", { name: "Record Investigation Conclusion" }));
    await screen.findByText("Refresh conclusion");
    await userEvent.click(screen.getByRole("button", { name: "Record Investigation Conclusion" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[0]).toEqual(bodies[1]); expect(bodies[0]?.finalAttackCategory).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Human Investigation Finding"), "suspicious");
    await userEvent.selectOptions(screen.getByLabelText("Human Final Attack Classification"), "infiltration");
    await userEvent.click(screen.getByRole("button", { name: "Record Investigation Conclusion" }));
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(bodies[2]?.requestId).not.toBe(bodies[0]?.requestId);
  });
});
