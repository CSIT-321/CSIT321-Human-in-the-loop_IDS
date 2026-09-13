/**
 * Panel 1 — the flow itself (plan S12).
 *
 * Everything here is what the API recorded for the flow: the five-tuple an analyst writes on a ticket
 * and the CICFlowMeter vector underneath it. Nothing is derived client-side, because the flow is the
 * one thing in the detail view that no amount of feedback can change.
 */

import type { Schemas } from "../../api/client";
import { Card, KeyValues } from "../../components/ui";
import { formatNumber } from "../../design/format";

type FlowPanel = Schemas["FlowPanel"];

/**
 * A flow duration runs from microseconds to hours, so two decimals would print every short flow as
 * "0.00". Six significant digits keeps the small ones readable and the long ones short.
 */
function significant(value: number, digits = 6): string {
  if (!Number.isFinite(value) || value === 0) return "0";
  return Number.parseFloat(value.toPrecision(digits)).toString();
}

function renderFeature(value: number | string | null): string {
  if (value === null) return "—";
  return typeof value === "number" ? formatNumber(value) : value;
}

export function FlowPanelCard({ flow }: { flow: FlowPanel }) {
  const features = Object.entries(flow.features ?? {});

  return (
    <Card title="Flow">
      <KeyValues
        rows={[
          ["Source", <span className="font-mono">{`${flow.srcIp}:${flow.srcPort}`}</span>],
          ["Destination", <span className="font-mono">{`${flow.dstIp}:${flow.dstPort}`}</span>],
          ["Protocol", flow.protocol],
          ["Duration", `${significant(flow.durationSeconds)} seconds`],
          ["Packets", formatNumber(flow.packets)],
          ["Bytes", formatNumber(flow.bytes)],
          ["Source record", <span className="font-mono">{flow.sourceRecordId}</span>],
        ]}
      />

      {features.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-muted">
            {`All flow features (${formatNumber(features.length)})`}
          </summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-muted">
                  <th scope="col" className="px-3 py-2 font-medium">
                    Feature
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody>
                {features.map(([name, value]) => (
                  <tr key={name} className="border-t border-border">
                    <th scope="row" className="px-3 py-1.5 text-left font-normal text-muted">
                      {name}
                    </th>
                    <td className="px-3 py-1.5 font-mono tabular-nums text-text">
                      {renderFeature(value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </Card>
  );
}
