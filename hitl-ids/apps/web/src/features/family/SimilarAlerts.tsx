/**
 * Similar-alert learning, made visible (plan S7b).
 *
 * The product's claim is that a verdict on one alert re-ranks the alerts like it. Until this
 * module existed the console stated that claim in one sentence — "3 other alerts in this family
 * moved" — which is an assertion, not a demonstration. Two things turn it into one, and they are
 * the two components here:
 *
 * - `SimilarityFacets` — *what the system means by similar*. Exact match on attack class,
 *   destination port, protocol and matched rule; no score, no threshold. The API returns the
 *   family key already parsed into those fields, so the screen never has to know the key's format.
 * - `MovedAlerts` — *which* alerts moved, and from where to where. Score and band come from the
 *   family's learning; rank is the alert's position in the queue, measured either side of the same
 *   transaction. A score change nobody can locate in the queue demonstrates nothing.
 *
 * Both render from the API response and never recompute anything locally: only the guardrails and
 * the agreement gate know what was actually applied.
 */

import { Link } from "react-router";

import type { Schemas } from "../../api/client";
import { formatNumber } from "../../design/format";

type Basis = Schemas["SimilarityBasis"];
type Moved = Schemas["MovedMember"];

/** One component of the family key, as a labelled chip. */
function Facet({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-sm border border-border bg-bg px-2 py-1">
      <span className="text-[9px] uppercase tracking-wider text-dim">{label}</span>
      <span className="font-mono text-[11px] text-text">{value}</span>
    </span>
  );
}

/**
 * What makes these alerts similar — the membership test, spelled out.
 *
 * The chips are the fields that must match *exactly*; the sentence beneath is the rule itself, sent
 * by the API rather than written here, so the screen and the engine cannot describe similarity
 * differently.
 */
export function SimilarityFacets({
  basis,
  compact = false,
}: {
  basis: Basis | null | undefined;
  compact?: boolean;
}) {
  if (basis === null || basis === undefined) return null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <Facet label="Attack class" value={basis.attackCategory ?? "unflagged"} />
        <Facet label="Dest. port" value={basis.dstPort === null ? "—" : String(basis.dstPort)} />
        <Facet label="Protocol" value={basis.protocol ?? "—"} />
        <Facet label="Rule" value={basis.ruleId ?? "none matched"} />
        {basis.dstIp !== null && basis.dstIp !== undefined && <Facet label="Dest. IP" value={basis.dstIp} />}
      </div>
      {!compact && <p className="text-[12px] leading-relaxed text-muted">{basis.rule}</p>}
    </div>
  );
}

function Arrow() {
  return (
    <span aria-hidden className="px-1 text-dim">
      →
    </span>
  );
}

/** A rank that improved is worth seeing; one that worsened is worth seeing just as much. */
function RankMove({ before, after }: { before: number | null; after: number | null }) {
  if (before === null || after === null) return <span className="text-dim">—</span>;
  const moved = before - after;
  const tone = moved > 0 ? "text-ok" : moved < 0 ? "text-warn" : "text-muted";
  return (
    <span className="tabular-nums">
      <span className="text-muted">{formatNumber(before)}</span>
      <Arrow />
      <span className={tone}>{formatNumber(after)}</span>
    </span>
  );
}

/**
 * The alerts a verdict moved without anyone judging them.
 *
 * Ordered by where they landed, because the analyst's next question is "what should I look at
 * now?". `total` is the true count and `rows` may be a capped slice of it — the difference is
 * stated rather than hidden, since a table silently showing 25 of 147 would misrepresent the very
 * effect it exists to show.
 */
export function MovedAlerts({
  rows,
  total,
  familyKey,
}: {
  rows: readonly Moved[];
  total: number;
  familyKey?: string | null;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-sm border border-border">
      <div className="flex items-baseline justify-between border-b border-border bg-raised px-3 py-2">
        <h4 className="text-[13px] font-medium text-text">
          {formatNumber(total)} similar {total === 1 ? "alert" : "alerts"} re-ranked
        </h4>
        <span className="text-[11px] text-dim">
          {rows.length < total ? `showing the top ${rows.length}` : "nobody judged these"}
        </span>
      </div>
      <table className="w-full text-left text-[12px]">
        <thead className="bg-bg text-[10px] uppercase tracking-wider text-dim">
          <tr>
            <th scope="col" className="px-3 py-1.5 font-medium">
              Alert
            </th>
            <th scope="col" className="px-3 py-1.5 font-medium">
              Score
            </th>
            <th scope="col" className="px-3 py-1.5 font-medium">
              Band
            </th>
            <th scope="col" className="px-3 py-1.5 font-medium">
              Queue rank
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr key={row.alertRef}>
              <td className="px-3 py-1.5">
                <Link to={`/analyst/alerts/${row.alertRef}`} className="font-mono text-accent hover:text-text">
                  {row.sourceRecordId}
                </Link>
              </td>
              <td className="px-3 py-1.5 font-mono tabular-nums">
                <span className="text-muted">{row.scoreBefore}</span>
                <Arrow />
                <span className="text-text">{row.scoreAfter}</span>
              </td>
              <td className="px-3 py-1.5 font-mono text-[11px]">
                <span className="text-muted">{row.queueClassBefore}</span>
                <Arrow />
                <span className="text-text">{row.queueClassAfter}</span>
              </td>
              <td className="px-3 py-1.5 font-mono">
                <RankMove before={row.rankBefore ?? null} after={row.rankAfter ?? null} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {familyKey !== null && familyKey !== undefined && familyKey !== "" && (
        <div className="border-t border-border bg-bg px-3 py-2">
          <Link
            to={`/analyst/workstation?familyKey=${encodeURIComponent(familyKey)}`}
            className="text-[12px] text-accent hover:text-text"
          >
            Open the whole family in the queue →
          </Link>
        </div>
      )}
    </div>
  );
}
