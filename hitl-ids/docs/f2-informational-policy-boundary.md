# RR-F2-01: strict informational/policy boundary

Base: `a769079de31b696d9b5d3e4bd9342a81e2121a63`.
Branch: `feat/f2-informational-policy-boundary`.

## Root cause and V2 → V3

V2 accepted `ET POLICY .+` and arbitrary suffixes after informational/policy/protocol
notification prefixes. A finite attack-word veto cannot recognize every unresolved attack
concept. Ruleset nomenclature is not evidence that a signal is a non-attack notification.
The reviewer counterexamples are synthetic boundary probes, not claims of exact ET rules.

New decisions default to `config/suricata-classification-v3.json`. V1/V2 configuration files
and stored snapshots remain intact. Existing known attack rules, specificity edges and veto
are copied unchanged; routing and Operational Priority are unchanged. V3 only narrows the
positive notification patterns. No new attack category or mapping is introduced.

## Exact V3 positive vocabulary

All signature matches are case-insensitive full matches, optionally prefixed by the literal
`SYNTHETIC `. No leading/trailing extra text or arbitrary suffix is allowed.

| Signature | Optional exact suffix | Required native category (full match) |
| --- | --- | --- |
| `Informational notice` or `Informational notification` | `: software version` | `Misc activity` or `Not Suspicious Traffic` |
| `Policy event` or `Policy notice` | `: application usage` | `Potential Corporate Privacy Violation` or `Misc activity` |
| `Protocol notice` or `Protocol informational event` | `: negotiation` | `Generic Protocol Command Decode` or `Misc activity` |

These retain the explicitly intended software-version/application-usage/negotiation controls
from repository tests. Bulk fixtures now repeat approved vocabulary with distinct flow IDs,
rather than grant informational status to arbitrary synthetic suffixes. No `ET POLICY`
signature is currently positive-allowlisted, including `ET POLICY Application usage`.

Informational rules MUST remain narrow positive allowlists, never detector-prefix catch-alls.
The veto is defense in depth, not a positive decision. A focused configuration test rejects
the reintroduction of `.*` / `.+` into V3 signature patterns; this is deliberately a narrow
regression check, not a claim of complete regex safety analysis. Historical V2 still loads.

Known attack mappings take precedence. Every related alert signature must be positively
recognized before a bundle can become informational. A known attack plus a notification
stays known; incompatible known classes retain conflict semantics. Any otherwise unmapped,
unrecognized signature defaults to `unknown_needs_expert`.

## Unknown product invariant

**Every final `unknown_needs_expert` automatically routes to Tier 2 Expert Review and creates
a formal Case with `decisionSource=system_policy`, null human creator/owner and no Tier 1
approval.** This fix changes classification boundaries, never this routing rule.

No severity shortcut is used. Approved positives remain informational at severities 1–4.
Informational status is not a benign/human verdict and still follows normal routing policy.

## Regression evidence

`tests/test_f2_informational_boundary.py` covers:

- All three reviewer examples becoming Unknown, plus three unfamiliar ET POLICY phrases
  and three arbitrary notification suffixes outside the unchanged veto vocabulary.
- Positive signatures across all native severities, retained match audit and V3 version.
- Four multi-signature cases: all-positive, positive+unknown, positive+known Web Attack,
  and positive+true incompatible attack evidence.
- Actual V2 admission and immutable saved classification followed by V3 admission;
  old V2 snapshot stays byte-for-byte unchanged while new evidence uses V3.
- A batch of **54 approved notifications → zero Expert Cases**, and **9 genuine Unknown
  signals → 9 formal system-created Expert Cases**, with null human creator/owner.

Existing `test_pre_freeze_review_fixes.py` retains all F1–F7 assertions; only expected default
version, unsafe ET POLICY expectation and approved bulk vocabulary are updated. Its batch
still verifies 53 approved notices and five required Unknown/conflict Cases.

The new browser suite uses real frontend/backend and a disposable database on ports 5186/8016.
It verifies approved informational, all three reviewer examples, vocabulary outside the veto,
and known ET POLICY SQL-injection text retaining Web Attack mapping. The existing pre-freeze
browser journey also runs against V3, including F1 recall, direct manual Case, old API block,
capture isolation and responsive themes. No demo database is used.

## Scope and remaining limitations

F1, F3–F7 designs, routing, scoring, capture identity, migrations, UI layout, ground-truth
protection, XGBoost boundary and Protocol V2 artifacts are unchanged. No collection is opened.
No Analyst Verdict, investigation assistance, streaming, new inference or PCAP feature is added.

The finite vocabulary intentionally sends unfamiliar notices to Expert Review until an
explicitly reviewed future policy version recognizes them. It does not claim broad coverage
of real ET policy rules. Sealed bundles, capture-scope operator responsibility, dynamic review
lookup cost and polling latency remain accepted limitations. A passed candidate is ready for
focused independent re-review, not permission to merge or open collection.

Previously stored V2 decisions retain their original classifications, including the former
boundary behavior. V3 applies to new decisions; this focused change does not silently repair
or reclassify historical alerts.

## Changed files

## Validation results (2026-11-01)

| Check | Result |
| --- | --- |
| Full backend `pytest -q --tb=short --basetemp=.pytest-tmp/full` | 1,343 passed, 5 unchanged optional-data skips; 525.35s |
| Final focused F2 + pre-freeze + Suricata/routing + queue + Protocol V2 regression | 154 passed; 31.78s |
| Full frontend | 232 tests / 31 files passed |
| TypeScript / OpenAPI / generated schema freshness | Passed |
| Production build | Passed; existing large-chunk advisory |
| New real frontend/backend F2 browser journey | 1 passed; 17.8s |
| Existing pre-freeze browser journey against V3 | 1 passed; 21.8s |
| V2 preservation, unchanged known mappings/compatibility/veto | Verified against base |
| Protocol V2 artifact hashes / collectionOpened=false | Verified |
| git diff --check | Passed |

The full backend run collected before the final configuration-pattern safeguard test was
added and the historical compatibility assertion was strengthened. The final 154-test pass
includes both final checks. No regression was disabled. Five optional tests require absent
gitignored historical samples/model outputs. Browser databases were disposable; demo.db and
operational collection state were not changed.

### Exact file inventory

Repository-relative paths:

```text
hitl-ids/config/suricata-classification-v3.json
hitl-ids/packages/detection/attack_classification.py
hitl-ids/tests/test_f2_informational_boundary.py
hitl-ids/tests/test_pre_freeze_review_fixes.py
hitl-ids/apps/web/e2e/pre-freeze-fixture.py
hitl-ids/apps/web/e2e/f2-boundary-fixture.py
hitl-ids/apps/web/e2e/f2-boundary.spec.ts
hitl-ids/apps/web/playwright.f2-boundary.config.ts
hitl-ids/docs/f2-informational-policy-boundary.md
```
