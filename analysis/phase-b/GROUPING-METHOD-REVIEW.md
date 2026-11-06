# Grouping method review (2026-11-06)

Question: is migration 22 as planned (group tables + rebuild `tier2_case_events` so the system can `link` alerts
into one case) the best way to group alerts, or is there a better method?

## Facts found (measured or read in code)

| # | Fact | Source |
|---|---|---|
| F1 | `tier2_case_events` was already rebuilt 3 times (migrations 8, 14, 19). A 4th rebuild copies every row and recreates 3 append-only triggers. | `packages/contracts/*.sql` |
| F2 | The analyst `link` action records a link only. It does **not** move the linked alert's route. A linked alert stays in the Tier 1 queue. | `tier2_cases.py:358-366` |
| F3 | 4 readers find an alert's case only through `primary_operational_alert_id`. An alert in Tier 2 that is only *linked* shows "no case" there. | `routing_routes.py:45`, `selective_review.py:287`, `triage_memory.py:505`, `tier2_cases.py:289` |
| F4 | The evaluation code reads only `action='finding'` events, so neither method touches the frozen V3.1 evidence. | `temporal_source.py:44`, `prospective_recorded.py:120` |
| F5 | Group counts (source IP, 30 min) — `grouping_size.py`: demo.db 996 flagged → **81** groups (19 singletons; largest 197); replay window 16,724 → **5**; full spike day 287,639 → **23**. | measured |
| F6 | Groups whose first flagged member is not E1 but a later one is: **0** on all three datasets. | measured |
| F7 | Routing cost: 996 alerts in 10.4 s (≈ 96 alerts/s), so per-alert projection of the replay window's 16,724 flagged flows ≈ 175 s; the full day ≈ 50 min. | measured rate, inference for the totals |
| F8 | The system may append further `system_route` rows to `operational_routing_audit` for the same alert (only `request_id` must be unique); only `operational_system_routing` (the initial decision) is one-per-alert. | migration 14 CHECKs |

## The methods

**A — planned: every flow is its own operational alert, group tables on top, system links members into one case.**
16,724 V2 alerts in the replay window, each with ~5 audit rows. Needs: the events rebuild (F1); a new member
state, because a linked member stays in Tier 1 (F2) and moving it to `tier2_case` breaks 4 readers (F3); and
grouped queue SQL, because the queue would still list 16,724 rows.

**B — group at projection: one operational alert per group (the representative); members recorded in a group table.**
The representative is the first flagged alert of the group. Every member keeps its legacy alert (score, family,
verdict history — the approved engine is unchanged). The queue lists groups naturally (5 in the replay window).
Needs: 2 new append-only tables (`alert_groups`, `alert_group_members`), no rebuild, no change to LCK's tables or
readers. "Split out a member" = project that member as its own operational alert on demand (`materialize_source`
already exists) and record a `split` row. A later escalation of a Tier 1 group (F6: does not occur in the data, but
the rule needs it) = append a `system_route` audit row and open the case on the representative (F8).

**C — display-only grouping: no schema change; the queue collapses rows by source IP at read time.**
Nothing stored. But the 16,724 Tier 2 cases are still created (one per E1 flow) and the verdict cannot be
"one vote per group" without a stored group. Fails decisions D3b and the one-vote rule.

## Comparison

| Criterion | A (planned) | B (group at projection) | C (display only) |
|---|---|---|---|
| Tier 2 cases in the replay window | 2 | 2 | 16,713 |
| Operational alerts written (replay window) | 16,724 | 5 (+16,724 member rows) | 16,724 |
| Routing time, replay window (F7) | ≈ 175 s | seconds | ≈ 175 s |
| Change to LCK's audited tables | rebuild `tier2_case_events` | none | none |
| Readers that need changes (F3) | 4 + queue SQL + summary | 0 (queue shows a group count) | queue SQL |
| Split out one member | already an item | project on demand | n/a |
| One-vote tag (D3b) | yes | yes | no |
| Approved engine (scores, family learning) | unchanged | unchanged | unchanged |
| Risk to frozen V3.1 evidence (F4) | none | none | none |

## Recommendation: method B

Justification:
1. **Least change to audited history.** B adds two append-only tables. A rebuilds an audit table for the 4th time
   (F1); every rebuild is a chance to lose a trigger or a row, on the table that holds Tier 2's legal trail.
2. **No hidden breakage.** A puts alerts in Tier 2 without their own case, which 4 readers do not expect (F3). B
   keeps LCK's rule "one Tier 2 case = one primary alert" true.
3. **Scales to real traffic.** A writes one operational alert per flow — ≈ 50 min for one real day (F7). B writes one
   per group (23 for that day, F5) plus light member rows.
4. **The queue is right by construction.** In B the queue *is* the grouped list; in A every count and filter must
   be rewritten to collapse rows.
5. **The decided workflow is kept**: visible "Grouped: N alerts" flag, member list, group verdict to every member
   with one vote per family, split-out, whole-group escalation.

What B changes from earlier decisions (must be accepted):
- Phase A's test "every flagged alert is its own operational alert" becomes "every flagged alert is a member of
  exactly one group, and each group has one operational alert". The 996 flagged alerts on demo.db appear as
  **81** queue items.
- The workload counts show groups; a separate "alerts in groups" count shows flows.

Limit: the representative's detector evidence (title, ports, score) is one member's. The group view must show the
member list and the range (first/last seen, count, max score) so the analyst does not judge the group from one flow.
