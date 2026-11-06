# Phase B — status and the grouping design (2026-11-06)

## Done (commit pending full suite)

- `packages/detection/flow_routing.py`, `config/flow-routing-v1.json`, `scripts/materialize_flow_queue.py`
  (`route_flagged`). Every projected flow alert gets one system routing decision in LCK's own tables
  (`operational_triage_state_v2`, `operational_routing_audit`, `operational_triage_policy_audit`,
  `operational_system_routing`, `tier2_cases`). No schema change.
- Routed flow alerts in Tier 1 are now claimable (`is_tier1_work` is true), which closes review findings S2-01,
  S3-01, S4-01, S6-02 (backend part), and S3-02 for flow alerts (the candidate flag and reasons are stored).
- Tests: `tests/test_flow_routing.py`, 14 tests; red check `analysis/phase-b/red_check.sh` — the candidate flag
  hard-coded False (LCK's defect), the fail-safe removed, and the Admin switch ignored each fail at least one test.

## Measured on copies (`analysis/phase-b/routing_truth.py`)

| Database | Auto-escalated (wrong) | Candidates (wrong) | Routine (wrong) |
|---|---|---|---|
| `demo.db` (996 flagged) | 200 (0) | 444 (1 = `AL-00478`) | 352 (1 = `AL-02717`) |
| `stress.db` (1,346 flagged) | 148 (0) | 700 (342) | 498 (258) |

10.4 s for 996 alerts; a second run routes 0.

## Not done in this step

- **E1-suricata is evaluated but not fed** in the batch path: `demo.db` has no Suricata alerts linked to flows.
  The replay source (next step) passes the linked Suricata severity.
- **Admin switch** exists in the policy file only; no Governance control yet (Phase C).
- **New-groups limit (M = 5/min)** is in the policy file but not enforced: it acts on groups, which do not exist yet.
- B5 (re-evaluate on a trusted fact), B6 (one eligibility predicate), B7 (immutability triggers), B8 (one severity
  config) — not started.

## Grouping needs a schema change (migration 22)

Two constraints in LCK's schema block grouping as decided (D3b):

1. `tier2_cases.primary_operational_alert_id` is UNIQUE — one case per alert.
2. `tier2_case_events` CHECK allows the system (`decision_source='system_policy'`) only the `create` action — the
   system cannot `link` a further alert into an existing case.

Without grouping, the replay window would open **16,713** Tier 2 cases (one per E1 flow).

Design (migration 22, additive except one CHECK):

- New `alert_groups` (group_ref, grouping key = source IP, first/last seen, case_ref nullable, created_at) and
  `alert_group_members` (group_id, operational_alert_id UNIQUE, joined_at, reason). Both append-only.
- Rebuild `tier2_case_events` to allow `decision_source='system_policy'` with `action='link'` (the table is already
  rebuilt the same way in migration 14).
- Routing: an alert joins the open group for its source IP if the group's last member is within 30 minutes; else it
  opens a new group. The first E1 member opens the case; later members are `link`ed into it, with the qualifying
  member marked. The new-groups limit counts new groups per minute.
- The **one-vote tag** belongs to the verdict bridge (C1), where group verdicts are first written to
  `feedback_events`; its red-capable test is written there.
