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
  OVERVIEW_CSV_COLUMNS,
  REPORT_CSV_COLUMNS,
  ipReportCsv,
  ipReportFilename,
  sourceIpOverviewCsv,
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

const OVERVIEW: Schemas["SourceIpOverviewPage"] = {
  generatedAt: "2026-09-17T04:00:00Z",
  fromDate: null,
  toDate: null,
  items: [
    {
      sourceIp: REPORT.sourceIp,
      totalAlerts: 21,
      judgedAlerts: 3,
      confirmedMalicious: 2,
      confirmedMaliciousRate: 2 / 3,
      falsePositives: 1,
      benignPositives: 0,
      escalated: 1,
      needsInvestigation: 0,
      unjudged: 18,
      firstSeen: "2018-03-01 10:00:00",
      lastSeen: "2018-03-01 10:05:00",
    },
  ],
  page: { total: 1, limit: 25, offset: 0, returned: 1 },
  sort: "totalAlerts",
  direction: "desc",
};

type OverviewStub = Schemas["SourceIpOverviewPage"] | ((url: URL) => Schemas["SourceIpOverviewPage"]);

function stubReport(
  report: Schemas["IpSecurityReport"] = REPORT,
  overview: OverviewStub = OVERVIEW,
): Request[] {
  return stubFetch((request) => {
    const url = new URL(request.url);
    if (url.pathname === "/api/admin/reports/ips") {
      return jsonResponse(typeof overview === "function" ? overview(url) : overview);
    }
    if (url.pathname === `/api/admin/reports/ip/${REPORT.sourceIp}`) return jsonResponse(report);
    return jsonResponse({ error: { code: "NOT_FOUND", message: `No stub for ${url.pathname}` } }, 404);
  });
}

async function openSpecificReport(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: `Open report for ${REPORT.sourceIp}` }));
  await screen.findByRole("heading", { level: 2, name: "IP SECURITY REPORT" });
}

function installDownloadSpies() {
  const createObjectURL = vi.fn(() => "blob:test-download");
  const revokeObjectURL = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  return { createObjectURL, revokeObjectURL, click };
}

function overviewRow(index: number): Schemas["SourceIpOverviewRow"] {
  return {
    ...OVERVIEW.items[0]!,
    sourceIp: `10.0.${Math.floor(index / 250)}.${index % 250}`,
    totalAlerts: index + 1,
  };
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

  it("starts with the source-IP list and requires no manually entered IP", async () => {
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    expect(await screen.findByRole("heading", { level: 1, name: "IP Security Reports" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "All Source IPs" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "All source IPs" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Source IP")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate report" })).not.toBeInTheDocument();
  });

  it("opens one source IP with the overview's inclusive capture-date parameters", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.type(screen.getByLabelText("Overview from date"), "2018-03-01");
    await user.type(screen.getByLabelText("Overview to date"), "2018-03-01");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await openSpecificReport(user);

    const request = seen.find((item) => new URL(item.url).pathname.startsWith("/api/admin/reports/ip/"));
    expect(request).toBeDefined();
    const url = new URL(request?.url ?? "http://localhost");
    expect(url.pathname).toBe(`/api/admin/reports/ip/${REPORT.sourceIp}`);
    expect(url.searchParams.get("fromDate")).toBe("2018-03-01");
    expect(url.searchParams.get("toDate")).toBe("2018-03-01");
    expect(request?.headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("rejects a reversed overview date range without calling the report endpoint", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.type(screen.getByLabelText("Overview from date"), "2018-03-02");
    await user.type(screen.getByLabelText("Overview to date"), "2018-03-01");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Overview from date must be on or before overview to date");
    expect(seen.filter((request) => new URL(request.url).pathname.startsWith("/api/admin/reports/ip/"))).toHaveLength(0);
  });
});

describe("admin source IP security overview", () => {
  it("renders source-only helper text and verdict aggregates without a risk score", async () => {
    stubReport();
    const { container } = renderApp("/admin/reports/ip", { session: ADMIN });

    const table = await screen.findByRole("table", { name: "All source IPs" });
    expect(screen.getByText("Source IPs observed in recorded network flows. Destination-only appearances are excluded.")).toBeInTheDocument();
    expect(table).toHaveTextContent(REPORT.sourceIp);
    expect(table).toHaveTextContent("66.7%");
    expect(table).toHaveTextContent("18");
    expect(container).toHaveTextContent("All Source IPs");
    expect(container.textContent?.toLowerCase()).not.toContain("risk score");
  });

  it("sends search, inclusive dates, minimum count and server-side sorting", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    await screen.findByRole("table", { name: "All source IPs" });

    await user.type(screen.getByLabelText("Search source IP"), "172.31");
    await user.type(screen.getByLabelText("Overview from date"), "2018-03-01");
    await user.type(screen.getByLabelText("Overview to date"), "2018-03-01");
    await user.clear(screen.getByLabelText("Minimum alerts"));
    await user.type(screen.getByLabelText("Minimum alerts"), "5");
    await user.selectOptions(screen.getByLabelText("Sort by"), "confirmedMaliciousRate");
    await user.selectOptions(screen.getByLabelText("Sort direction"), "asc");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const requests = seen.filter((request) => new URL(request.url).pathname === "/api/admin/reports/ips");
      expect(requests.length).toBeGreaterThan(1);
      const url = new URL(requests.at(-1)?.url ?? "http://localhost");
      expect(Object.fromEntries(url.searchParams)).toMatchObject({
        search: "172.31",
        fromDate: "2018-03-01",
        toDate: "2018-03-01",
        minAlerts: "5",
        sort: "confirmedMaliciousRate",
        direction: "asc",
        offset: "0",
      });
    });
  });

  it("resets active filters and returns immediately to the complete source-IP list", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    await screen.findByRole("table", { name: "All source IPs" });

    await user.type(screen.getByLabelText("Search source IP"), "172.31");
    await user.type(screen.getByLabelText("Overview from date"), "2018-03-01");
    await user.clear(screen.getByLabelText("Minimum alerts"));
    await user.type(screen.getByLabelText("Minimum alerts"), "5");
    await user.selectOptions(screen.getByLabelText("Sort by"), "sourceIp");
    await user.selectOptions(screen.getByLabelText("Sort direction"), "asc");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));

    expect(screen.getByLabelText("Search source IP")).toHaveValue("");
    expect(screen.getByLabelText("Overview from date")).toHaveValue("");
    expect(screen.getByLabelText("Minimum alerts")).toHaveValue(1);
    expect(screen.getByLabelText("Sort by")).toHaveValue("totalAlerts");
    expect(screen.getByLabelText("Sort direction")).toHaveValue("desc");
    await waitFor(() => {
      const requests = seen.filter((request) => new URL(request.url).pathname === "/api/admin/reports/ips");
      const url = new URL(requests.at(-1)?.url ?? "http://localhost");
      expect(url.searchParams.get("search")).toBeNull();
      expect(url.searchParams.get("fromDate")).toBeNull();
      expect(url.searchParams.get("toDate")).toBeNull();
      expect(url.searchParams.get("minAlerts")).toBe("1");
      expect(url.searchParams.get("sort")).toBe("totalAlerts");
      expect(url.searchParams.get("direction")).toBe("desc");
      expect(url.searchParams.get("offset")).toBe("0");
    });
  });

  it("applies default controls as the complete source-IP list", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    await screen.findByRole("table", { name: "All source IPs" });

    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const requests = seen.filter((request) => new URL(request.url).pathname === "/api/admin/reports/ips");
      const url = new URL(requests.at(-1)?.url ?? "http://localhost");
      expect(url.searchParams.get("search")).toBeNull();
      expect(url.searchParams.get("fromDate")).toBeNull();
      expect(url.searchParams.get("toDate")).toBeNull();
      expect(url.searchParams.get("minAlerts")).toBe("1");
      expect(url.searchParams.get("offset")).toBe("0");
    });
  });

  it("opens the existing individual report when a source IP is selected", async () => {
    const user = userEvent.setup();
    const seen = stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await openSpecificReport(user);
    expect(await screen.findByRole("heading", { level: 2, name: "IP SECURITY REPORT" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Specific IP Report" })).toBeInTheDocument();
    expect(seen.some((request) => new URL(request.url).pathname === `/api/admin/reports/ip/${REPORT.sourceIp}`)).toBe(true);
  });

  it("returns to the preserved overview without re-entering the IP", async () => {
    const user = userEvent.setup();
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    await user.type(screen.getByLabelText("Search source IP"), "172.31");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await openSpecificReport(user);

    await user.click(screen.getByRole("button", { name: "Back to All Source IPs" }));
    expect(screen.getByRole("heading", { level: 1, name: "IP Security Reports" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search source IP")).toHaveValue("172.31");
    expect(screen.getByRole("table", { name: "All source IPs" })).toBeInTheDocument();
  });

  it("provides a separate View Report action for each source row", async () => {
    const user = userEvent.setup();
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.click(await screen.findByRole("button", { name: `View report for ${REPORT.sourceIp}` }));
    expect(await screen.findByRole("heading", { level: 1, name: "Specific IP Report" })).toBeInTheDocument();
  });

  it("requests stable server pages using the returned offset and limit", async () => {
    const user = userEvent.setup();
    const seen = stubReport(REPORT, {
      ...OVERVIEW,
      page: { total: 30, limit: 25, offset: 0, returned: 1 },
    });
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => {
      const requests = seen.filter((request) => new URL(request.url).pathname === "/api/admin/reports/ips");
      expect(new URL(requests.at(-1)?.url ?? "http://localhost").searchParams.get("offset")).toBe("25");
    });
  });

  it("exports every filtered row across server pages using the active sort", async () => {
    const user = userEvent.setup();
    const allRows = Array.from({ length: 201 }, (_, index) => overviewRow(index));
    const seen = stubReport(REPORT, (url) => {
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      if (limit === 200) {
        const items = allRows.slice(offset, offset + limit);
        return {
          ...OVERVIEW,
          items,
          page: { total: allRows.length, limit, offset, returned: items.length },
          sort: "sourceIp",
          direction: "asc",
        };
      }
      return { ...OVERVIEW, page: { total: allRows.length, limit: 25, offset, returned: 1 } };
    });
    const downloads = installDownloadSpies();
    renderApp("/admin/reports/ip", { session: ADMIN });

    await user.type(screen.getByLabelText("Search source IP"), "10.0");
    await user.type(screen.getByLabelText("Overview from date"), "2018-03-01");
    await user.type(screen.getByLabelText("Overview to date"), "2018-03-02");
    await user.clear(screen.getByLabelText("Minimum alerts"));
    await user.type(screen.getByLabelText("Minimum alerts"), "3");
    await user.selectOptions(screen.getByLabelText("Sort by"), "sourceIp");
    await user.selectOptions(screen.getByLabelText("Sort direction"), "asc");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await user.click(screen.getByRole("button", { name: "Export Overview CSV" }));

    await waitFor(() => expect(downloads.createObjectURL).toHaveBeenCalledOnce());
    const exportRequests = seen
      .filter((request) => {
        const url = new URL(request.url);
        return url.pathname === "/api/admin/reports/ips" && url.searchParams.get("limit") === "200";
      })
      .map((request) => new URL(request.url));
    expect(exportRequests.map((url) => url.searchParams.get("offset"))).toEqual(["0", "200"]);
    expect(Object.fromEntries(exportRequests[0]!.searchParams)).toMatchObject({
      search: "10.0",
      fromDate: "2018-03-01",
      toDate: "2018-03-02",
      minAlerts: "3",
      sort: "sourceIp",
      direction: "asc",
    });
    const csv = sourceIpOverviewCsv(allRows);
    expect(csv.split("\r\n")).toHaveLength(202);
    expect(csv.split("\r\n")[0]).toBe(OVERVIEW_CSV_COLUMNS.join(","));
    expect(csv).toContain(allRows.at(-1)?.sourceIp);
    expect(downloads.click).toHaveBeenCalledOnce();
  });
});

describe("admin IP security report: evidence and exports", () => {
  it("renders summary, behaviour, targets, ports, timeline and advisory without ground truth", async () => {
    const user = userEvent.setup();
    stubReport();
    const { container } = renderApp("/admin/reports/ip", { session: ADMIN });

    await openSpecificReport(user);

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

  it("keeps the specific-IP CSV export separate from the overview export", async () => {
    const user = userEvent.setup();
    const downloads = installDownloadSpies();
    stubReport();
    renderApp("/admin/reports/ip", { session: ADMIN });
    await openSpecificReport(user);

    await user.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(downloads.createObjectURL).toHaveBeenCalledOnce();
    expect(downloads.click).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Export Overview CSV" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Print / Save PDF" })).not.toBeInTheDocument();
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
