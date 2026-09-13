/**
 * The family panel (plan S12): why an alert nobody touched may have moved.
 *
 * Similar-alert learning is deliberately gated — one verdict is not evidence, three that agree are —
 * so the panel shows the gate and its reason rather than a bare "influenced by" flag. An alert can sit
 * in a family whose gate is shut and still carry an offset from an earlier, open one; `note` says so.
 */

import type { Schemas } from "../../api/client";
import { Card, KeyValues, Pill } from "../../components/ui";
import { formatDelta, formatNumber, formatPercent } from "../../design/format";
import { categoryLabel } from "../feedback/categories";

type FamilyPanel = Schemas["FamilyPanel"];

export function FamilyPanelCard({ family }: { family: FamilyPanel }) {
  return (
    <Card title="Similar alerts (family)">
      <KeyValues
        rows={[
          ["Family key", <span className="font-mono text-xs">{family.familyKey ?? "—"}</span>],
          ["Members", formatNumber(family.members)],
          [
            "Learning gate",
            family.gateOpen ? <Pill tone="ok">Open</Pill> : <Pill tone="muted">Closed</Pill>,
          ],
          ["Agreement", family.agreementRatio === null ? "—" : formatPercent(family.agreementRatio)],
          [
            "Dominant verdict",
            categoryLabel(family.dominantCategory),
          ],
          [
            "Applied adjustment",
            <span className="font-mono tabular-nums">{formatDelta(family.appliedAdjustment)}</span>,
          ],
          [
            "Band offset",
            <span className="font-mono tabular-nums">{formatNumber(family.appliedOffset)}</span>,
          ],
        ]}
      />

      {family.gateReason !== null && <p className="mt-4 text-sm text-muted">{family.gateReason}</p>}
      {family.note !== null && <p className="mt-2 text-sm text-muted">{family.note}</p>}

      <p className="mt-4 text-xs text-dim">
        Families group alerts by attack class, destination port, protocol and matched rule. Learning
        applies only once three verdicts in the family agree.
      </p>
    </Card>
  );
}
