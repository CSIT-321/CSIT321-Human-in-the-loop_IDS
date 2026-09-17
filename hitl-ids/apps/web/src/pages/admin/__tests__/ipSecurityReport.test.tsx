import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../../api/client";
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../../components/layout/AppShell";
import { ROLE_META } from "../../../session/roles";
import type { Session } from "../../../session/SessionContext";
import { THEME_STORAGE_KEY } from "../../../theme/ThemeContext";
import { jsonResponse, renderApp, stubFetch } from "../../../test/renderApp";
import {
  REPORT_CSV_COLUMNS,
  ipReportCsv,
  ipReportFilename,
} from "../IpSecurityReportPage";
import { ADMIN } from "./fixtures";

const ANALYST: Session = {
  username: "g.ang",
  displayName: "Glenn Ang",
  role: "security_analyst",
  token: "analyst-token",
};

const REPORT: Schemas["IpSecurityReport"] = {
  sourceIp: "172.31.69.25",
  fromDate: "2018-03-01",
  toDate: "2018-03-01",
  generatedAt: "2026-09-17T04:00:00Z",
  summary: {
    totalAlerts: 3,
    confirmedMalicious: 2,
    truePositive: 1,
    escalated: 1,
    falsePositive: 1,
    expectedActivity: 0,
    needsInvestigation: 0,
    distinctAttackCategories: 2,
    distinctDestinationHosts: 2,
    distinctDestinationPorts: 2,
    firstSeen: "2018-03-01 10:00:00",
    lastSeen: "2018-03-01 10:05:00",
  },
  attackBehaviour: [
    { attackCategory: "Brute Force", alertCount: 2, confirmedMalicious: 2 },
    { attackCategory: "Benign", alertCount: 1, confirmedMalicious: 0 },
  ],
  targetedHosts: [
    { destinationIp: "18.221.219.4", alerts: 2, confirmedMalicious: 2, lastSeen: "2018-03-01 10:05:00" },
    { destinationIp: "172.31.69.28", alerts: 1, confirmedMalicious: 0, lastSeen: "2018-03-01 10:02:00" },
  ],
  destinationPorts: [
    { port: 22, alerts: 2, confirmedMalicious: 2 },
    { port: 80, alerts: 1, confirmedMalicious: 0 },
  ],
  timeline: [
    {
      captureTime: "2018-03-01 10:00:00",
      alertRef: "AL-0001",
      sourceRecordId: "row,one",
      sourceIp: "172.31.69.25",
      destinationIp: "18.221.219.4",
      destinationPort: 22,
      protocol: "TCP",
      attackCategory: "Brute Force",
      detectionScore: 88,
      operationalScore: 92,
      effectiveVerdict: "confirm_true_positive",
      status: "in_progress",
    },
    {
      captureTime: "2018-03-01 10:02:00",
      alertRef: "AL-0002",
      sourceRecordId: "row-two",
      sourceIp: "172.31.69.25",
      destinationIp: "172.31.69.28",
      destinationPort: 80,
      protocol: "TCP",
      attackCategory: "Benign",
      detectionScore: 24,
      operationalScore: 18,
      effectiveVerdict: "mark_false_positive",
      status: "dismissed",
    },
  ],
  recommendation: {
    action: "Investigate / monitor",
    reason: "2 analyst-confirmed malicious alerts warrant investigation and monitoring.",
    advisory: "Recommendation is advisory. No network blocking action is performed.",
  },
};

function stubReport(report: Schemas["IpSecurityReport"] = REPORT): Request[] {
  return stubFetch((request) => {
    const url = new URL(request.url);
    if (url.pathname === `/api/admin/reports/ip/${REPORT.sourceIp}`) return jsonResponse(report);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${url.pathname}` } }, 404);
  });
}

async function generateReport(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Source IP"), REPORT.sourceIp);
  await user.type(screen.getByLabelText("From date"), "2018-03-01");
  await user.type(screen.getByLabelText("To date"), "2018-03-01");
  await user.click(screen.getByRole("button", { name: "Generate report" }));
  await screen.findByRole("heading", { level: 2, name: "IP SECURITY REPORT" });
}

describe("admin IP security report: access and scope", () => {
  it("is present only in administrator navigation and its route rejects an analyst", async () => {
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    const adminNav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(adminNav).getByRole("link", { name: "IP Security Report" })).toBeInTheDocument();
    expect(ROLE_META.security_analyst.nav.some((item) => item.to === "/admin/reports/ip")).toBe(false);

    const second = renderApp("/admin/reports/ip", { session: ANALYST });
    await waitFor(() => expect(second.router.state.location.pathname).toBe("/analyst/workstation"));
  });

  it("requests one source IP with inclusive capture-date parameters", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await generateReport(user);

    const request = seen.find((item) => new URL(item.url).pathname.startsWith("/api/admin/reports/ip/"));
    expect(request).toBeDefined();
    const url = new URL(request?.url ?? "http://localhost");
    expect(url.pathname).toBe(`/api/admin/reports/ip/${REPORT.sourceIp}`);
    expect(url.searchParams.get("fromDate")).toBe("2018-03-01");
    expect(url.searchParams.get("toDate")).toBe("2018-03-01");
    expect(request?.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("rejects a reversed date range without calling the report endpoint", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.type(screen.getByLabelText("Source IP"), REPORT.sourceIp);
    await user.type(screen.getByLabelText("From date"), "2018-03-02");
    await user.type(screen.getByLabelText("To date"), "2018-03-01");
    await user.click(screen.getByRole("button", { name: "Generate report" }));

    expect(screen.getByRole("alert")).toHaveTextContent("From date must be on or before To date");
    expect(seen).toHaveLength(0);
  });
});

describe("admin IP security report: evidence and exports", () => {
  it("renders summary, behaviour, targets, ports, timeline and advisory without ground truth", async () => {
    const user = userEvent.setup();
    stubReport();
    const { container } = renderApp("/admin/reports/ip", { session: ADMIN });

    await generateReport(user);

    expect(screen.getByLabelText("IP activity summary")).toHaveTextContent("Confirmed malicious2");
    expect(screen.getByRole("table", { name: "Attack behaviour" })).toHaveTextContent("Brute Force");
    expect(screen.getByRole("table", { name: "Targeted hosts" })).toHaveTextContent("18.221.219.4");
    expect(screen.getByRole("table", { name: "Destination ports" })).toHaveTextContent("22");
    const timeline = screen.getByRole("table", { name: "Alert timeline" });
    expect(timeline).toHaveTextContent("True positive");
    expect(timeline).toHaveTextContent("False positive");
    expect(screen.getByText(REPORT.recommendation.advisory)).toBeInTheDocument();
    expect(container.textContent?.toLowerCase()).not.toContain("ground truth");
    expect(container.textContent?.toLowerCase()).not.toContain("raw label");
  });

  it("prints through the browser without adding a PDF dependency", async () => {
    const user = userEvent.setup();
    stubReport();
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderApp("/admin/reports/ip", { session: ADMIN });
    await generateReport(user);

    await user.click(screen.getByRole("button", { name: "Print / Save PDF" }));
    expect(print).toHaveBeenCalledOnce();
  });

  it("exports the documented columns, quotes CSV values and creates a portable filename", () => {
    const csv = ipReportCsv(REPORT);
    expect(csv.split("\r\n")[0]).toBe(REPORT_CSV_COLUMNS.join(","));
    expect(csv).toContain('"row,one"');
    expect(csv).toContain("confirm_true_positive");
    expect(ipReportFilename(REPORT)).toBe("ip-security-report-172.31.69.25-2018-03-01-to-2018-03-01.csv");

    expect(ipReportFilename({ ...REPORT, sourceIp: "2001:db8::1" })).toBe(
      "ip-security-report-2001-db8-1-2018-03-01-to-2018-03-01.csv",
    );
  });

  it("works with the light theme and a persisted collapsed sidebar", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "true");
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(nav).toHaveAttribute("data-collapsed", "true");
    await user.click(within(nav).getByRole("button", { name: "Expand sidebar" }));
    expect(within(nav).getByRole("link", { name: "IP Security Report" })).toBeInTheDocument();
  });
});
