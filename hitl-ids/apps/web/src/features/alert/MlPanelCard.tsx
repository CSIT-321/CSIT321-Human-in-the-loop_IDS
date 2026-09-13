/**
 * Panel 3 — what the model said and why (plan S12, NFR-01).
 *
 * The contributions are TreeSHAP values in log-odds: they are additive with the base value, which is
 * what makes the panel checkable rather than decorative. The bars are coloured by sign (teal pushes
 * towards the prediction, orange pushes away) and the two lists name the same ten numbers.
 *
 * Charts carry explicit pixel sizes: `ResponsiveContainer` measures zero in jsdom and renders nothing.
 */

import type { ReactNode } from "react";
import { Bar, BarChart, Cell, XAxis, YAxis } from "recharts";

import type { Schemas } from "../../api/client";
import { EmptyState } from "../../components/states";
import { Card, KeyValues, Pill } from "../../components/ui";
import { formatNumber, formatPercent } from "../../design/format";

type MlPanel = Schemas["MlPanel"];
type ShapFeature = Schemas["ShapFeature"];

const CHART_WIDTH = 520;
const CHART_HEIGHT = 260;

/** A contribution with its sign and three decimals: "+0.412", "−0.138". */
function signed(value: number): string {
  if (value === 0) return "0.000";
  const magnitude = Math.abs(value).toFixed(3);
  return value > 0 ? `+${magnitude}` : `−${magnitude}`;
}

function renderValue(value: number | string | null): string {
  if (value === null) return "—";
  return typeof value === "number" ? formatNumber(value) : value;
}

function ContributionList({ heading, items }: { heading: string; items: readonly ShapFeature[] }) {
  if (items.length === 0) return null;

  return (
    <div>
      <h3 className="text-sm font-medium text-text">{heading}</h3>
      <ul className="mt-2 space-y-1">
        {items.map((item) => (
          <li
            key={item.featureName}
            className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm"
          >
            <span className="font-mono text-xs text-muted">{item.featureName}</span>
            <span className="ml-auto font-mono tabular-nums text-muted">
              {renderValue(item.featureValue)}
            </span>
            <span
              className={`w-20 text-right font-mono tabular-nums ${
                item.shapContribution >= 0 ? "text-ok" : "text-warn"
              }`}
            >
              {signed(item.shapContribution)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MlPanelCard({ ml }: { ml: MlPanel }) {
  if (ml.predictedClass === null) {
    return (
      <Card title="Model prediction">
        <EmptyState title={ml.note ?? "The model did not score this flow."} />
      </Card>
    );
  }

  const predictedClass = ml.predictedClass;
  const contributions: readonly ShapFeature[] = [...(ml.topSupporting ?? []), ...(ml.topOpposing ?? [])];
  const chartRows = contributions.map((item) => ({
    name: item.featureName,
    value: item.shapContribution,
  }));

  const rows: (readonly [string, ReactNode])[] = [
    ["Predicted class", predictedClass],
    ["Confidence", ml.probability === null ? "—" : formatPercent(ml.probability)],
    ["Model", <span className="font-mono">{ml.modelVersion ?? "—"}</span>],
    ["Explanation", ml.explanationStatus ?? "—"],
  ];
  if (ml.additivityPassed === true) {
    rows.push(["Additivity", <Pill tone="ok">Additivity check passed</Pill>]);
  }

  return (
    <Card title="Model prediction">
      <KeyValues rows={rows} />

      <div className="mt-4 space-y-4">
        <ContributionList heading={`Pushed towards ${predictedClass}`} items={ml.topSupporting ?? []} />
        <ContributionList heading="Pushed away" items={ml.topOpposing ?? []} />
      </div>

      {chartRows.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <BarChart
            layout="vertical"
            width={CHART_WIDTH}
            height={CHART_HEIGHT}
            data={chartRows}
            margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
          >
            <XAxis
              type="number"
              stroke="var(--color-border)"
              tick={{ fill: "var(--color-muted)", fontSize: 10 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={150}
              stroke="var(--color-border)"
              tick={{ fill: "var(--color-muted)", fontSize: 10 }}
            />
            <Bar dataKey="value" isAnimationActive={false}>
              {chartRows.map((row, index) => (
                <Cell
                  key={`${row.name}-${index}`}
                  fill={row.value >= 0 ? "var(--color-ok)" : "var(--color-warn)"}
                />
              ))}
            </Bar>
          </BarChart>
        </div>
      )}

      <p className="mt-3 text-xs text-dim">
        Contributions are TreeSHAP values in log-odds; they sum with the base value to the model's raw
        margin.
      </p>
    </Card>
  );
}
