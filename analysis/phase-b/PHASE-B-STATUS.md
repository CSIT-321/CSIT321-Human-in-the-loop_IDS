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
