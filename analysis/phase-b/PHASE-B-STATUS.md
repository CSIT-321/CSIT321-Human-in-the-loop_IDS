# Phase B — status (2026-11-06, updated after grouping)

## Done

- **Routing core** (commit `9d210ea`): `packages/detection/flow_routing.py`, `config/flow-routing-v1.json`,
  `scripts/materialize_flow_queue.py`. Every flow alert/group gets one system routing decision in LCK's own tables.
- **Grouping, method B** (commit `82263b2`): migration 22 adds `alert_groups` + `alert_group_members` (append-only
  except the growing `last_seen_at`/`member_count` and one-time `representative`/`qualifying`/`case_ref` links).
  Each group = one operational alert (its first member in arrival order). Unflagged flows join no group.
- Routed Tier 1 groups are claimable (`is_tier1_work`). Candidate flag + reasons stored (review findings S2-01,
  S3-01, S3-02, S4-01, S6-02 backend part closed).
- Tests: 22 in `test_flow_queue.py` / `test_flow_routing.py` / `test_flow_routing_rules.py` + fixture
  `flow_group_fixture.py` (4 known groups: two E1 in the same minute, two Botnet candidates 41 min apart).
  Red checks (`red_check.sh`, `red_check_grouping.sh`): candidate-flag off, fail-safe removed, switch ignored,
  window ignored, unflagged join groups, limit ignored — each fails at least one test, restore passes all.

## Measured on copies

| Database | Alerts | Groups | Escalated | Candidate | Routine | Time |
|---|---|---|---|---|---|---|
| `demo.db` | 996 flagged | **81** | 3 | 74 | 4 | 5.7 s |
| `stress.db` | 1,346 flagged | 676 | 3 | 420 | 253 | 18.8 s |

Escalated demo groups = the 3 brute-force sources (18.221.219.4 ×80, 13.58.98.64 ×54, 13.59.126.31 ×66) — the
same 200 E1 flows measured before, now 3 queue items. Second run: 0 new. The 4 routine demo groups are
18.219.211.138 (2), 18.217.165.70 (1), 18.219.193.20 (**197**, all model-only DoS) and 172.31.64.109 (1).

Review after the model fallback (commit `e6292b4`, checks in `review_grouping.py`): the qualifying member was
always the first member (also on routine groups), a later member's detector conflict was missed, and candidate
reasons repeated once per member. All three fixed test-first; longest stored reason on `demo.db` is now 178 chars.

## Traps found and fixed during this step

1. Routing reasons on large groups exceed the audit `reason` column's 2000-char CHECK — cap `reason_audit` to
   1970 + marker before the routing-audit and case-event inserts (the triage state keeps the full text).
2. A test helper keyed groups by source IP; one IP legitimately owns several groups (10.0.0.66 twice in the
   fixture, `18.218.*` many times on `demo.db`). Key by group id.
3. Adding migration 22 breaks hard-coded `db.migrate()` expectations in 5 test files (`[20,21]` etc.).

## Not done yet

- **E1-suricata** is evaluated but not fed: `demo.db` has no Suricata alerts linked to flows. The replay source
  (next step) passes the linked severity.
- **Governance switches**: the policy file has them; no Admin UI yet (Phase C).
- B5 (re-evaluate on a trusted fact), B6 (one eligibility predicate), B7 (immutability triggers), B8 (one severity
  config).
- The one-vote group tag for family learning belongs to the verdict bridge (C1).

## Decision D4 (reviewed 2026-11-07): keep it, with three conditions

Measured on a copy of the routed `demo.db` (`analysis/phase-b/d4_cost_probe.py`):

- The 4,004 unflagged flows are all model class Benign, scores 0 to 42.77. 6 of them are real attacks
  (5 Infiltration, 1 Web Attack). One of them, `AL-03086`, is the approved demo's missed-attack story.
- Each unflagged flow projected and routed as a single item: 47.9 s in total (12 ms each). All 4,004 routed routine.
- Queue: 4,085 items. The 81 flagged groups keep ranks 1-81. `AL-03086` is at rank 83.
- `queue_page(50)` on 4,085 items: 108 ms.

Conditions:
1. Unflagged flows are never grouped. Each one is a single queue item.
2. Unflagged flows rank below every flagged group.
3. The Tier 1 workload count shows flagged groups and unflagged flows apart. This is a screen-layout
   choice, so supervisors confirm it in Phase C.

Not measured: cost at full-day scale (about 74,500 unflagged flows), and the summary query on 4,085 items.
The demo script quotes "rank 998 -> 997" for `AL-03086`. That number changes and must be updated in Phase F.

### D4 implemented (2026-11-07)

`scripts/materialize_flow_queue.py`: `materialize_unflagged` + `route_unflagged` (a group of one through the same
`route_flow_alert`; no routing rule changed). Tests: 5 new in `test_flow_queue.py` / `test_flow_routing.py`.
Red check (`red_check_grouping.sh`) now has 6 defects; each fails at least one test; restored code passes 23.

Measured on fresh copies:

| | demo.db | stress.db |
|---|---|---|
| Queue items | 4,085 (81 groups + 4,004 singles) | 4,330 (676 groups + 3,654 singles) |
| Singles routed | 4,004 routine | 3,654 routine |
| Ranks | groups 1-81, singles 82-4,085 | groups 1-676, singles 677-4,330 |
| Unrouted (unclaimable) items | 0 | 0 |
| queue_page(50) / summary | 106 ms / 97 ms | 96 ms / 87 ms |
| Full script run | about 50 s (not timed) | 2 min 54 s |

Missed attacks on demo.db: `AL-03086` rank 83, `AL-04260` 84, `AL-01456` 178, `AL-03070` 1,154, `AL-01903` 1,484,
`AL-00272` 1,490. Second run: all zeros.

**Limit — condition 2 is not enforced in code.** Singles rank below groups only because their scores are lower
(single max 42.77; group min 88.48 on demo, 60 on stress). Trusted context can add up to +25
(`config/operational-triage-v1.json`: 10 + 10 + 5), so a single can reach 67.77 and outrank a stress.db group
scoring 60-67.77. Today: 0 context facts on both. Enforcing it means changing the shared queue order
(`apps/api/operational_queue.py`), which is a Phase C decision.

**Summary count:** `tier1_review` is now 4,082 on demo.db. Condition 3 (show groups and singles apart) is Phase C.

## B7 and B8 done (2026-11-07)

- **B7** `e7e17f9`: migration 23 (`packages/contracts/integrity_guards.sql`). Refuses a change to
  `alerts.detection_score`, `alert_ref`, `evidence_class`, `dataset_id`, `run_id` (same-value writes allowed), and
  any delete from `operational_triage_state_v2`. Tests `tests/test_integrity_triggers.py` (8); with the triggers
  off, 7 fail. 412 related tests pass (feedback, learning, detection, contracts, migrations).
- **B8** `b900684`: `tests/test_policy_consistency.py` pins the shared policy values. Red check: changing any one
  copy fails a test. Selective review's campaign threshold (5) is a different, more cautious rule, not pinned.

## B5 and B6: need a decision

- **B5** Trusted context is read once, at routing. A fact recorded later does not re-route. Also measured:
  `flow_routing.py` uses context for the priority, but drops the triage policy's own Tier 2 recommendations
  (`priority.tier2_recommendation_reasons`): `tier2_recommended` comes from `route.tier2_reasons` only.
  0 trusted facts on demo.db and stress.db, so nothing is lost today.
- **B6** Four modules define "is Tier 1 work": claim and verdict need a routing row; selective review and the
  routing actions do not. Every flow item now has a routing row (0 unrouted), so the gap is only the historical
  non-bundle Suricata path, used by 8 test files (`legacy_suricata_fixture`).

## B5 done (scoped), B6 stopped (2026-11-07)

- **B5** `cac29b6`: flow routing keeps the triage policy's context recommendations as candidate reasons
  ("Context: ..."); they never change the route. Test-first (a trusted fact made no candidate before).
  The System Routing panel shows "Why Tier 2 is recommended" and states that context is read once.
- **B6 stopped before commit.** The shared rule (routing row required) breaks 11 tests in 5 files. They are not
  test-only scaffolding: they cover a live, labelled product path. `external_admission.py:173-186` (non-bundle
  branch) admits with `admit_tier1` and writes no routing row; the console labels its approve/reject actions
  "Historical Tier 2 candidate approval/rejection"; selective review and prospective collection run on those
  records. Under the shared rule they lose all Tier 1 actions. Review S3-10 says current staging always emits a
  bundle, so the branch is unreachable for new data; 0 such rows on the routed demo copy. The change is saved as
  `analysis/phase-b/b6-shared-predicate.patch` (applies cleanly); the tree is back to green.

## B6 done, option 1 (2026-11-07)

`beb257b`: `packages/detection/tier1_eligibility.py` owns the rule, with three results.

| Result | Meaning | Claim / verdict | Selective review / routing actions |
|---|---|---|---|
| current | tier1_review / triage + a system routing row | yes | yes |
| historical | tier1_review / triage, no routing row (non-bundle admission path) | no | yes ("Historical ..." labels) |
| none | any other route or stage | no | no (staged alerts keep `admit_tier1`) |

Callers moved onto it: `analyst_work.is_tier1_work`, `analyst_verdict._eligible`, `selective_review.read_review`,
`routing.allowed_actions` (status now required) and `route_alert`, `apps/api/routing_routes._view`, and the two
summary queries in `apps/api/operational_queue.py` (`CURRENT_TIER1_SQL`).

Checks:
- Behaviour baseline `b6_baseline.py`: 5 answers for 16 alerts of all three kinds + summary + review metrics;
  before and after byte-identical.
- Live API `b6_live_check.py` (old code from a git worktree vs the branch, real claim on a copy): identical.
- `tests/test_tier1_eligibility.py` (7). Red check `red_check_b6.sh`: 5 planted defects each fail a test.
- 438 tests in the 18 affected files; 117 web tests; OpenAPI unchanged.

Not moved on purpose: `packages/evaluation/*` (frozen research code), `selective_review_policy.py`
UNSUPPORTED_WORKFLOW (part of the recorded review input hash), `triage_policy_service.py` (a different question:
which states the policy may overwrite).
