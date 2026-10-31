# Prospective Unbound Override Integrity

Base: `f403359d8b3c9e70fbe96b459b652448d3efbe91`
(`feat/prospective-readiness-final-integrity-fixes`).
Branch: `feat/prospective-readiness-unbound-override-integrity`.
Status: automated verification passed, pending another independent final read-only review.
Protocol V2 is unchanged: draft, undated and unopened. Do not start collection.

## Evidence boundary

Any event consumed by a registered prospective metric must pass full integrity validation, even when
that event is not a run-bound collection ledger event.

Ledger reconciliation still validates every recorded event and all global raw identities before cohort
selection. The evaluator then builds a separate validated recall-evidence set. Raw archive rows are no
longer consumed directly as trusted override evidence. There is no change to the operational override
service, API contracts, database schema, policy or UI.

Recall candidates are recognized using raw and original-request action/alert identities plus snapshot
provenance, so corrupting only one representation cannot hide an otherwise relevant event. Raw or original
snapshot timestamps inside the relevant window trigger full validation; the two must then agree.
Malformed timestamps on potentially relevant overrides fail explicitly.

Full validation requires positive strict numeric event/actor/alert IDs, UUID event_ref/request_id/alertRef,
aware timestamp, nonblank reason, original ReviewCommand, and a complete ReviewSnapshot. It verifies raw
request_id against the original request, action/event_type, request action/alert/reason, raw alert identity
against both snapshot alert and triage identity, and raw time against context evaluatedAt. Human overrides
must have Must Review, human_override source, the exact override reason code/explanation, no matched lesson,
matching policy version and the supported Tier 1/triage snapshot. Collection receipts must agree with the
original selected run. Existing recorded sidecar actor/action/time/snapshot checks remain intact.

The raw server-stamped actor is required and positive. Original ReviewCommand and ReviewSnapshot do not
duplicate that actor identity; the evaluator does not invent a second actor field or infer missing identity.
Authenticating an unbound actor against an independent user directory still requires trusted source provenance.

## Time and counts

Only `decisionAt < overrideAt < outcomeCutoff` contributes recall. Corrupting the raw time to equal/before
decisionAt or equal/after cutoff while leaving its original in-window snapshot intact is rejected.
A genuine service-created override at/before decisionAt or at/after cutoff is valid operational history,
but is excluded from recall. This distinction preserves the previously reviewed exclusive time boundaries.
No timestamps are backdated and no current memory/policy state is reconstructed.

- `run.decisionCount`: all run-bound recorded ledger events, including repeat evaluations/in-window overrides.
- `eligibleAlerts`: the unique first-eligible applied alert cohort.
- A valid unbound/not-recorded override can contribute recall without incrementing decisionCount.

Global numeric ID/event_ref/request_id uniqueness still covers the whole raw archive, including unrelated
rows. UUID uppercase/braced/compact representations normalize to the same identity. Impossible duplicate
source identities fail even on an unrelated row.

Unrelated future snapshots that do not affect any metric are not parsed into today's full ReviewSnapshot.
Only the existing global identity/request-envelope checks apply to those rows. Genuine post-cutoff additions
do not alter the closed report. Coherently replacing an entire archive is not prevented cryptographically.
Other outcome/observation and recorded-ledger validation paths remain in place; this increment does not
claim new external source authentication or add raw outcome ledgers.

## Verification

The valid control uses actual services: persist No Immediate Review, create Require Human Review with no
selected run, verify sticky operational state/audit and unchanged collection decisions, close the disposable
run, then evaluate one recall with decisionCount=1 and eligibleAlerts=1.

Corruption tests cover the requested A-T cases: actor/request/snapshot omissions, malformed/null/empty UUIDs,
duplicate identities, mismatched raw/request/snapshot alert/action/reason, invalid event types and timestamps,
temporal boundary tampering, and snapshot disposition/source/policy/reason/route/stage/triage identity.
Separate controls prove genuine out-of-window events are excluded and unrelated future snapshots are stable.
No existing test assertion or browser fixture is weakened.

| Check | Result |
| --- | --- |
| New override, archive, collection and read-only suites | 322 passed, including all 53 new cases |
| Full Python | 1164 passed, 5 existing data-artifact skips |
| Frontend / TypeScript | 207 tests passed (29 files); TypeScript passed |
| OpenAPI / frontend schema / Vite | All passed; existing Vite chunk-size warning remains |
| Routing / Prospective / pristine S16 browser | 10 / 2 / 1 passed; optional S16 guide capture skipped |

The four original corruption reproductions also returned HTTP 400 `ARCHIVE_INTEGRITY` through the real
report handler in an isolated in-memory test probe. The committed regression file contains 53 cases:
42 corruption cases, six UUID duplicate-format cases, the valid control, three genuine time-boundary
controls and an unrelated-future-history control. Existing jsdom navigation notices remain non-failing.
The five Python skips require gitignored generated samples/predictions; they are not new failures.
The 322-test run includes the inspection-readonly suite covering all 40 database-backed GET routes,
legacy-schema inspection, missing database handling and read-only authentication/filter dependencies.

Source `data/demo.db` SHA-256 and UTC modification ticks remained unchanged:
`DF34AB87760A8BB51DDF5A74D84A2B4C89DE0C5B157777292F15FC132A83AC00`, `639252641490430974`.

All fixtures are disposable. No source demo.db mutation, attack traffic, real response execution or actual
registered collection is performed. Synthetic test windows are not research registration or participant UAT.

## Scope and next review

Exact files relative to hitl-ids/:

```text
packages/evaluation/prospective_recorded.py
tests/test_unbound_override_integrity.py
docs/HANDOVER.md
docs/prospective-readiness-final-integrity-fixes.md
docs/prospective-unbound-override-integrity.md
```

No changes to Selective Review pure policy, Triage Memory, Trusted Context resolver, temporal replay,
Suricata staging/admission, tier routing/cases/UX, response approval, legacy feedback/guardrails or detectors.
No changes to the 40 strict read-only GET dependencies, mutation dependencies, draft protocol or S16 setup.

Next: independently compare the final feature commit with the base above, reproduce the valid unbound
control and every corruption family, verify temporal exclusion/global uniqueness/count separation, and
rerun the prior readiness/browser checks. Do not claim readiness until that independent review returns PASS.
