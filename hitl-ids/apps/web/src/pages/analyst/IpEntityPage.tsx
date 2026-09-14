/**
 * One address, as far as the recording is concerned (console rebuild R4).
 *
 * `GET /api/entities/ip/{ip}` counts the alerts that mention this address in either direction, how
 * they split across the queue's bands and attack classes, which verdicts are in force, who it talked
 * to, and on which ports. Every figure on the page is that one response, formatted — no arithmetic
 * happens here, because the API is the one place the demo's counts are defined.
 *
 * There is deliberately nothing more: the corpus is a capture of lab traffic, so a panel describing
 * an address beyond its own flows would be inventing data the demo does not have. When no alert
 * involves the address the API answers 404, and this page shows the API's own words with a retry.
 */

import type { ReactNode } from "react";
import { Link, useParams } from "react-router";

import { api, unwrap, type Schemas } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ApiView, EmptyState } from "../../components/states";
import { BandBadge, Card, KeyValues, PageHeader } from "../../components/ui";
import { QUEUE_BANDS } from "../../design/bands";
import { formatNumber } from "../../design/format";
import { categoryLabel } from "../../features/feedback/categories";
import { shortFlowTime } from "../../features/workstation/QueuePane";

type TopValue = Schemas["TopValue"];

interface CountRow {
  /** The contract's key, used as the React key. */
  readonly key: string;
  readonly label: ReactNode;
  readonly count: number;
}

/** A count map as rows, largest first; `label` names the key for the reader. */
function countRows(
  counts: { [key: string]: number } | undefined,
  label: (key: string) => ReactNode = (key) => key,
): readonly CountRow[] {
  return Object.entries(counts ?? {})
    .map(([key, count]) => ({ key, label: label(key), count }))
    .sort((left, right) => right.count - left.count);
}

/** A named thing and its alert count. The count is mono so the column can be scanned. */
function CountTable({ dimension, rows }: { dimension: string; rows: readonly CountRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-muted">
            <th scope="col" className="px-3 py-2 font-medium">
              {dimension}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Alerts
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-border">
              <th scope="row" className="px-3 py-1.5 text-left font-normal text-text">
                {row.label}
              </th>
              <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                {formatNumber(row.count)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * An address or a port, how many flows it accounts for, and how many of those a detector flagged.
 * `renderValue` is what makes a peer navigable and a port plain text.
 */
function TopValuesTable({
  dimension,
  values,
  renderValue,
}: {
  dimension: string;
  values: readonly TopValue[];
  renderValue: (value: string) => ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-muted">
            <th scope="col" className="px-3 py-2 font-medium">
              {dimension}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Flows
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Flagged
            </th>
          </tr>
        </thead>
        <tbody>
          {values.map((row) => (
            <tr key={row.value} className="border-t border-border">
              <th scope="row" className="px-3 py-1.5 text-left font-normal">
                {renderValue(row.value)}
              </th>
              <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                {formatNumber(row.count)}
              </td>
              <td className="px-3 py-1.5 font-mono tabular-nums text-warn">
                {formatNumber(row.flagged)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The address as the page's title, with the one action this page has: hand the address to the
 * workstation, which searches the queue for it. The header sits outside `ApiView`, so a failed load
 * still says which address failed.
 */
function AddressHeader({ ip }: { ip: string }) {
  return (
    <PageHeader
      title={ip}
      subtitle="What the recorded flows say about this address"
      actions={
        <Link
          to={`/analyst/workstation?search=${encodeURIComponent(ip)}`}
          className="rounded-sm border border-border bg-raised px-3 py-1.5 font-mono text-xs text-text hover:border-border-strong"
        >
          All alerts for this address
        </Link>
      }
    />
  );
}

export function IpEntityPage() {
  const params = useParams();
  const ip = params.ip ?? "";

  const entity = useApi(
    (signal) =>
      unwrap(
        api.GET("/api/entities/ip/{ip}", {
          params: { path: { ip }, query: { limit: 10 } },
          signal,
        }),
      ),
    [ip],
  );

  return (
    <div className="space-y-6">
      <AddressHeader ip={ip} />

      <ApiView resource={entity}>
        {(data) => {
          const queueCounts = data.byQueueClass ?? {};
          // The contract's band order, and only the bands this address actually has.
          const bandRows = QUEUE_BANDS.flatMap((band) => {
            const count = queueCounts[band.key];
            if (count === undefined) return [];
            return [{ key: band.key, label: <BandBadge queueClass={band.key} />, count }];
          });
          const classRows = countRows(data.byAttackCategory);
          const verdictRows = countRows(data.verdictMix, categoryLabel);
          const peers = data.topPeers ?? [];
          const ports = data.topDestinationPorts ?? [];

          return (
            <>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card title="Summary">
                  <KeyValues
                    rows={[
                      ["Alerts", formatNumber(data.alerts)],
                      ["As source", formatNumber(data.asSource)],
                      ["As destination", formatNumber(data.asDestination)],
                      ["Flagged", formatNumber(data.flagged)],
                      ["First seen", shortFlowTime(data.firstSeen)],
                      ["Last seen", shortFlowTime(data.lastSeen)],
                    ]}
                  />
                </Card>

                <Card title="Queue bands">
                  {bandRows.length === 0 ? (
                    <EmptyState title="No queue bands recorded" />
                  ) : (
                    <CountTable dimension="Band" rows={bandRows} />
                  )}
                </Card>

                <Card title="Attack classes">
                  {classRows.length === 0 ? (
                    <EmptyState title="No attack class recorded" />
                  ) : (
                    <CountTable dimension="Class" rows={classRows} />
                  )}
                </Card>
              </div>

              <Card title="Verdicts in force">
                {verdictRows.length === 0 ? (
                  <EmptyState title="No verdicts recorded for this address" />
                ) : (
                  <CountTable dimension="Verdict" rows={verdictRows} />
                )}
              </Card>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Top peers">
                  {peers.length === 0 ? (
                    <EmptyState title="No peers recorded" />
                  ) : (
                    <TopValuesTable
                      dimension="Address"
                      values={peers}
                      renderValue={(value) => (
                        <Link
                          to={`/analyst/entities/ip/${encodeURIComponent(value)}`}
                          className="font-mono text-accent hover:text-text"
                        >
                          {value}
                        </Link>
                      )}
                    />
                  )}
                </Card>

                <Card title="Destination ports">
                  {ports.length === 0 ? (
                    <EmptyState title="No ports recorded" />
                  ) : (
                    <TopValuesTable
                      dimension="Port"
                      values={ports}
                      renderValue={(value) => <span className="font-mono text-text">{value}</span>}
                    />
                  )}
                </Card>
              </div>
            </>
          );
        }}
      </ApiView>
    </div>
  );
}
