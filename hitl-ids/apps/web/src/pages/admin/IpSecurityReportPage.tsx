import { useState, type FormEvent, type ReactNode } from "react";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { Card, PageHeader, Pill, StatStrip, type Stat, type Tone } from "../../components/ui";
import { formatDateTime, formatNumber, formatScore, humanise } from "../../design/format";

export type IpSecurityReport = Schemas["IpSecurityReport"];
type TimelineRow = Schemas["IpReportTimelineRow"];

interface ReportQuery {
  ip: string;
  fromDate: string;
  toDate: string;
}

export const REPORT_CSV_COLUMNS = [
  "capture_time",
  "alert_ref",
  "source_record_id",
  "source_ip",
  "destination_ip",
  "destination_port",
  "protocol",
  "attack_category",
  "detection_score",
  "operational_score",
  "effective_verdict",
  "status",
] as const;

const CONTROL_CLASS = "rounded-sm border border-border bg-raised px-3 py-1.5 text-sm text-text";
const PRIMARY_CLASS =
  "rounded-sm bg-primary px-4 py-1.5 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40";
const TH_CLASS = "whitespace-nowrap px-2 py-1.5 text-left font-medium";
const TD_CLASS = "whitespace-nowrap px-2 py-1.5 align-top text-text";

const VERDICT_TONE: Partial<Record<NonNullable<TimelineRow["effectiveVerdict"]>, Tone>> = {
  confirm_true_positive: "danger",
  escalate: "warn",
  mark_false_positive: "ok",
  mark_expected_activity: "accent",
  needs_investigation: "violet",
};

const VERDICT_LABEL: Partial<Record<NonNullable<TimelineRow["effectiveVerdict"]>, string>> = {
  confirm_true_positive: "True positive",
  escalate: "Escalated",
  mark_false_positive: "False positive",
  mark_expected_activity: "Expected activity",
  needs_investigation: "Needs investigation",
};

function csvCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function timelineValues(row: TimelineRow): readonly (string | number | null | undefined)[] {
  return [
    row.captureTime,
    row.alertRef,
    row.sourceRecordId,
    row.sourceIp,
    row.destinationIp,
    row.destinationPort,
    row.protocol,
    row.attackCategory,
    row.detectionScore,
    row.operationalScore,
    row.effectiveVerdict,
    row.status,
  ];
}

export function ipReportCsv(report: IpSecurityReport): string {
  const rows = (report.timeline ?? []).map((row) => timelineValues(row).map(csvCell).join(","));
  return [REPORT_CSV_COLUMNS.join(","), ...rows].join("\r\n");
}

function safeFilenamePart(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "unknown";
}

export function ipReportFilename(report: IpSecurityReport): string {
  const from = report.fromDate ?? "all";
  const to = report.toDate ?? "all";
  return `ip-security-report-${safeFilenamePart(report.sourceIp)}-${from}-to-${to}.csv`;
}

function downloadCsv(report: IpSecurityReport): void {
  const url = URL.createObjectURL(new Blob([ipReportCsv(report)], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = ipReportFilename(report);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function Verdict({ verdict }: { verdict: TimelineRow["effectiveVerdict"] }) {
  if (verdict === null) return <span className="text-dim">No verdict</span>;
  return <Pill tone={VERDICT_TONE[verdict] ?? "muted"}>{VERDICT_LABEL[verdict] ?? humanise(verdict)}</Pill>;
}

function DataTable({ headings, children, label }: { headings: readonly string[]; children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-dim">
            {headings.map((heading) => (
              <th key={heading} scope="col" className={TH_CLASS}>{heading}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function ReportBody({ report }: { report: IpSecurityReport }) {
  const { summary } = report;
  const stats: readonly Stat[] = [
    { label: "Total alerts", value: formatNumber(summary.totalAlerts), tone: "text-text" },
    { label: "Confirmed malicious", value: formatNumber(summary.confirmedMalicious), tone: "text-danger" },
    { label: "True positive", value: formatNumber(summary.truePositive), tone: "text-danger" },
    { label: "Escalated", value: formatNumber(summary.escalated), tone: "text-warn" },
    { label: "False positive", value: formatNumber(summary.falsePositive), tone: "text-ok" },
    { label: "Expected activity", value: formatNumber(summary.expectedActivity), tone: "text-accent" },
  ];

  return (
    <article className="print-report space-y-4" aria-label="Generated IP security report">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <p className="label-mono">System administrator report</p>
          <h2 className="mt-1 text-2xl font-semibold text-text">IP SECURITY REPORT</h2>
          <p className="mt-1 font-mono text-sm text-accent">{report.sourceIp}</p>
        </div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs">
          <dt className="text-dim">Capture dates</dt>
          <dd className="font-mono text-text">{report.fromDate ?? "All"} to {report.toDate ?? "All"}</dd>
          <dt className="text-dim">Generated</dt>
          <dd className="font-mono text-text">{formatDateTime(report.generatedAt)}</dd>
        </dl>
      </div>

      <StatStrip label="IP activity summary" stats={stats} />

      <Card title="Coverage summary" subtitle="Counts use recorded capture time and the latest effective analyst verdict.">
        <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["Needs investigation", summary.needsInvestigation],
            ["Attack categories", summary.distinctAttackCategories],
            ["Destination hosts", summary.distinctDestinationHosts],
            ["Destination ports", summary.distinctDestinationPorts],
            ["First / last seen", `${summary.firstSeen ?? "—"} / ${summary.lastSeen ?? "—"}`],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="label-mono text-[10px]">{label}</dt>
              <dd className="mt-1 break-words font-mono text-sm text-text">
                {typeof value === "number" ? formatNumber(value) : value}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      {summary.totalAlerts === 0 ? (
        <EmptyState title="No source-IP activity found" hint="No recorded flow matched this source IP and capture-date range." />
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-3">
            <Card title="Attack behaviour" subtitle="Alert categories assigned by the detection pipeline.">
              <DataTable label="Attack behaviour" headings={["Category", "Alerts", "Confirmed malicious"]}>
                {(report.attackBehaviour ?? []).map((row) => (
                  <tr key={row.attackCategory} className="border-t border-border">
                    <th scope="row" className={TD_CLASS}>{row.attackCategory}</th>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.alertCount)}</td>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.confirmedMalicious)}</td>
                  </tr>
                ))}
              </DataTable>
            </Card>

            <Card title="Targeted hosts" subtitle="Destinations contacted by this source IP.">
              <DataTable label="Targeted hosts" headings={["Destination", "Alerts", "Confirmed", "Last seen"]}>
                {(report.targetedHosts ?? []).map((row) => (
                  <tr key={row.destinationIp} className="border-t border-border">
                    <th scope="row" className={`${TD_CLASS} font-mono text-accent`}>{row.destinationIp}</th>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.alerts)}</td>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.confirmedMalicious)}</td>
                    <td className={`${TD_CLASS} font-mono text-muted`}>{row.lastSeen ?? "—"}</td>
                  </tr>
                ))}
              </DataTable>
            </Card>

            <Card title="Destination ports" subtitle="Ports observed on matching recorded flows.">
              <DataTable label="Destination ports" headings={["Port", "Alerts", "Confirmed malicious"]}>
                {(report.destinationPorts ?? []).map((row) => (
                  <tr key={row.port} className="border-t border-border">
                    <th scope="row" className={`${TD_CLASS} font-mono`}>{row.port}</th>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.alerts)}</td>
                    <td className={`${TD_CLASS} text-right font-mono`}>{formatNumber(row.confirmedMalicious)}</td>
                  </tr>
                ))}
              </DataTable>
            </Card>
          </div>

          <Card title="Alert timeline" subtitle="Capture-time order. Detection Score and Operational Score remain separate.">
            <DataTable
              label="Alert timeline"
              headings={["Capture time", "Alert", "Destination", "Port", "Protocol", "Attack category", "Detection", "Operational", "Effective verdict", "Status"]}
            >
              {(report.timeline ?? []).map((row) => (
                <tr key={row.alertRef} className="border-t border-border">
                  <td className={`${TD_CLASS} font-mono text-muted`}>{row.captureTime ?? "—"}</td>
                  <td className={`${TD_CLASS} max-w-36 truncate font-mono`} title={row.alertRef}>{row.alertRef}</td>
                  <td className={`${TD_CLASS} font-mono text-accent`}>{row.destinationIp}</td>
                  <td className={`${TD_CLASS} text-right font-mono`}>{row.destinationPort}</td>
                  <td className={`${TD_CLASS} font-mono`}>{row.protocol}</td>
                  <td className={TD_CLASS}>{row.attackCategory ?? "—"}</td>
                  <td className={`${TD_CLASS} text-right font-mono`}>{formatScore(row.detectionScore)}</td>
                  <td className={`${TD_CLASS} text-right font-mono`}>{formatScore(row.operationalScore)}</td>
                  <td className={TD_CLASS}><Verdict verdict={row.effectiveVerdict} /></td>
                  <td className={TD_CLASS}>{humanise(row.status)}</td>
                </tr>
              ))}
            </DataTable>
          </Card>
        </>
      )}

      <Card title="Advisory recommendation" subtitle="Derived from visible alert and effective analyst-verdict counts.">
        <div className="space-y-2">
          <p className="text-base font-semibold text-text">{report.recommendation.action}</p>
          <p className="text-sm text-muted">{report.recommendation.reason}</p>
          <p className="border-l-2 border-warn pl-3 text-xs text-warn">{report.recommendation.advisory}</p>
        </div>
      </Card>
    </article>
  );
}

function LoadedReport({ query }: { query: ReportQuery }) {
  const queryParams = {
    ...(query.fromDate === "" ? {} : { fromDate: query.fromDate }),
    ...(query.toDate === "" ? {} : { toDate: query.toDate }),
  };
  const report = useApi(
    (signal) => unwrap(api.GET("/api/admin/reports/ip/{ip}", {
      params: { path: { ip: query.ip }, query: queryParams },
      signal,
    })),
    [query.ip, query.fromDate, query.toDate],
  );

  return (
    <ApiView resource={report}>
      {(data) => (
        <div className="space-y-4">
          <div className="print-hidden flex flex-wrap justify-end gap-2">
            <button type="button" className={CONTROL_CLASS} onClick={() => window.print()}>Print / Save PDF</button>
            <button type="button" className={PRIMARY_CLASS} onClick={() => downloadCsv(data)}>Export CSV</button>
          </div>
          <ReportBody report={data} />
        </div>
      )}
    </ApiView>
  );
}

export function IpSecurityReportPage() {
  const [ip, setIp] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [query, setQuery] = useState<ReportQuery | null>(null);
  const [validation, setValidation] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sourceIp = ip.trim();
    if (sourceIp === "") {
      setValidation("Enter a source IP address.");
      return;
    }
    if (fromDate !== "" && toDate !== "" && fromDate > toDate) {
      setValidation("From date must be on or before To date.");
      return;
    }
    setValidation(null);
    setQuery({ ip: sourceIp, fromDate, toDate });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="IP Security Report"
        subtitle="Read-only source-IP activity report over recorded flows and effective analyst verdicts."
      />

      <Card className="print-hidden" title="Report scope" subtitle="Dates are inclusive and use recorded flow capture time.">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <label className="min-w-56 flex-1 text-xs text-dim">
            Source IP
            <input
              aria-label="Source IP"
              required
              value={ip}
              onChange={(event) => setIp(event.target.value)}
              placeholder="e.g. 172.31.69.25"
              className={`${CONTROL_CLASS} mt-1 w-full font-mono`}
            />
          </label>
          <label className="text-xs text-dim">
            From date
            <input aria-label="From date" type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} className={`${CONTROL_CLASS} mt-1 block`} />
          </label>
          <label className="text-xs text-dim">
            To date
            <input aria-label="To date" type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} className={`${CONTROL_CLASS} mt-1 block`} />
          </label>
          <button type="submit" className={PRIMARY_CLASS}>Generate report</button>
        </form>
        {validation !== null && <p role="alert" className="mt-3 text-sm text-danger">{validation}</p>}
      </Card>

      {query === null ? (
        <EmptyState title="Choose one source IP" hint="Generate a report to review its captured activity, effective verdicts and advisory recommendation." />
      ) : (
        <LoadedReport key={`${query.ip}:${query.fromDate}:${query.toDate}`} query={query} />
      )}
    </div>
  );
}
