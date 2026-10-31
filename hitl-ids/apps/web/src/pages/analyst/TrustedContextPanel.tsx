import type { Schemas } from "../../api/client";

type Resolution = Schemas["ResolvedTrustedContext"];
const labels: Record<string,string> = {
  assetCriticality:"Asset Criticality", knownMaliciousIndicator:"Known Malicious Indicator",
  responseRequired:"Response Required", confirmedMalicious:"Confirmed Malicious", evidenceConflict:"Evidence Conflict",
  repeatedCampaign:"Repeated Campaign", correlatedAlertCount:"Correlated Alert Count",
  analystEscalated:"Analyst Escalated", unresolvedByTier1:"Unresolved by Tier 1",
};

export function TrustedContextPanel({context}:{context?:Resolution|null}) {
  return <section aria-label="Trusted Context / Safety Evidence" className="min-w-0 space-y-3 border-t border-border pt-4">
    <h3 className="text-sm font-semibold">Trusted Context / Safety Evidence</h3>
    {!context?<p className="text-sm text-warn">Fact provenance unavailable. Safety context is unknown.</p>:<>
      <p className="break-words text-xs text-muted">As of {context.evaluatedAt} / {context.resolverVersion}</p>
      <dl className="grid min-w-0 gap-3 sm:grid-cols-2">
        {context.fields.map(field=><div key={field.contextKey} className="min-w-0 border-b border-border pb-3 text-sm">
          <dt className="font-semibold">{labels[field.contextKey]}</dt>
          <dd className="capitalize">{field.value===null?"Unknown":String(field.value)}</dd>
          <dd className="capitalize">Status: {field.status.replaceAll("_"," ")}</dd>
          {field.status!=="trusted"&&<dd className="text-warn">Effect: Must Review</dd>}
          <dd className="break-words text-xs text-muted">{field.explanation}</dd>
          <dd className="break-words text-xs">Available: {field.availableAt??"Unknown"}</dd>
          <dd className="break-words text-xs">Effective expiry: {field.expiresAt??"Unavailable"}</dd>
          {field.facts.map(fact=><dd key={fact.factRef} className="mt-2 break-words text-xs">
            <span className={fact.sourceType==="synthetic_fixture"?"font-semibold text-warn":""}>Source: {fact.sourceType}</span>
            <span className="block break-all">{fact.sourceReference} / {fact.factRef}</span>
            <span className="block">Subject: {fact.subjectType} / {fact.subjectValue}</span>
            <span className="block">Observed: {fact.observedAt}</span>
            <span className="block">Known: {fact.availableAt} / Valid from: {fact.validFrom}</span>
            <span className="block">{fact.reason}</span>
          </dd>)}
        </div>)}
      </dl>
    </>}
  </section>;
}
