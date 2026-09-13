/**
 * Panel 4 — how the rule and the model were combined (plan S12).
 *
 * The paragraph is the API's, not the screen's: it is the sentence an analyst repeats in a handover,
 * so it is rendered verbatim above the numbers that back it.
 */

import type { Schemas } from "../../api/client";
import { BandBadge, Card, EvidenceBadge, KeyValues } from "../../components/ui";

type EvidencePanel = Schemas["EvidencePanel"];

export function EvidencePanelCard({ evidence }: { evidence: EvidencePanel }) {
  return (
    <Card title="Combined explanation">
      <p className="text-sm leading-relaxed text-text">{evidence.explanation}</p>

      <div className="mt-4">
        <KeyValues
          rows={[
            ["Evidence class", <EvidenceBadge evidenceClass={evidence.evidenceClass} />],
            ["Rule and model agree", evidence.agreement ? "Yes" : "No"],
            ["Queue band", <BandBadge queueClass={evidence.queueClass} />],
            ["Fusion scheme", <span className="font-mono">{evidence.fusionScheme ?? "—"}</span>],
          ]}
        />
      </div>
    </Card>
  );
}
