# SOC design justification — tier views and automatic escalation

Branch `feat/tier-views-auto-escalation`. Written 2026-11-09 for review by SOC practitioners.

Each row gives: the design choice, the SOC problem it answers, the analyst's use case, and the evidence.
"Evidence" is a test, a measurement or a live check. A row with no evidence says so.

Decision owner: Glenn Ang (decisions D1–D8, `analysis/codebase-review/REVIEW-AND-PLAN.md` section 5b).

## 1. The problem the product answers

An SOC analyst gets more alerts than one person can read. Most are repeats of one event. A few need an
expert at once. The product must:

1. Show the analyst one item per event, not one per packet flow.
2. Send the clear, severe cases to Tier 2 without a Tier 1 click.
3. Tell the analyst why an alert is a Tier 2 candidate, and let a human decide.
4. Record who did what, so a shift lead or an auditor can follow the work.

Data used for every number below, unless the row says otherwise: a copy of `data/demo.db` (5,000 recorded
CSE-CIC-IDS2018 flows, 996 flagged), routed by `scripts/materialize_flow_queue.py`.

## 2. Queue shape: groups and tier views

| Choice | SOC problem | Analyst use case | Evidence |
|---|---|---|---|
| **Group flagged alerts** by source IP within 30 min (flow) or signature + source within 30 min (Suricata). One group = one queue item (D3b) | One attack makes hundreds of near-identical alerts (alert fatigue) | The analyst reads one item, "Group of 49", not 49 items | 996 flagged alerts -> **81** queue items (`PHASE-B-STATUS.md`, commit `82263b2`). Screen: "Tier 1 78 groups · 4,004 single" (`test-results/soc-guide/04-why-tier2.png`) |
| A group verdict counts as **one vote per family** toward learning (D3c) | One click on a 190-alert group must not count as 190 opinions | The analyst can judge a group without moving the whole family alone | Measured: per-member counting opens the 3-vote gate from one click (`analysis/spike/group_verdict_weight.py`). Test goes red if the group tag is dropped |
| **Unflagged flows stay in the queue**, below all flagged items (D4) | A missed attack must still be findable | The analyst can search a flow the detectors did not flag (approved demo story `AL-03086`) | 4,004 singles below 81 groups; `test_a_high_scoring_unflagged_item_still_ranks_below_every_group` |
| **Severity first**, then flagged, then priority (C9) | A severe alert must not sit below a busy but milder one | The top of the queue is the most urgent work | Before C9 a Critical group sat at rank 80 below 35 High/Medium groups; after, 0 severity inversions (`c9_effect.py`). 22 tests in `test_queue_severity.py`; 6 of 6 planted defects caught |
| **Tier views**: Active, Tier 1, Tier 2 candidates, Auto-escalated, Tier 2, plus counts (C2) | Tier 1 and Tier 2 staff need different lists | Each tier opens its own list in one click | `soc-flow.spec.ts` step 1 (tabs and the Auto-escalated count 3); `test-results/soc-guide/01-queue-views.png` |
| **Active is the default view**; completed and escalated work leaves it | Done work clutters the list | The analyst sees only open work at the start of a shift | `operational-queue.spec.ts` ("Active Tier 1" 8 = 11 routed - 3 completed) |

## 3. Automatic escalation (E1)

| Choice | SOC problem | Analyst use case | Evidence |
|---|---|---|---|
| **E1 auto-escalates** when score >= 80 and the ML model agrees with a rule (flow rule or Suricata) (D3) | Tier 1 time is spent on cases that are clearly severe | The case is already open in Tier 2 when the shift starts; Tier 1 never claims it | Demo: E1 = 200 alerts, **0 false positives**. Real packets 2018-02-14 by per-flow labels: 287,591 E1 flows, **precision 0.99986** (40 benign), recall 1.0 (`analysis/spike/SPIKE-RESULT.md`). Demo copy: 3 groups auto-escalated |
| E1 needs **two independent detectors to agree** | A single detector has false positives | Analysts can trust an auto case more than a single-source alert | `analysis/auto_escalation_safety.py`: score >= 90 + High without agreement = 648 hits / 342 false positives on the stress set (precision 0.4722). That rule was rejected |
| An auto case shows **"Rule"** as its creator, with the rule sentence | The expert must know a machine opened it | The Tier 2 expert reads why before investigating | Case list screen: "Rule — E1-flow-rule: the rule and the model agree on Brute Force at score 100 …" (`test-results/soc-guide/08-case-list.png`). Planted fault (creator shown instead of "Rule") fails `soc-flow.spec.ts` line 95 |
| **At most M = 5 new groups per minute** auto-escalate; a trip makes a candidate, never closes an alert (D3a) | A flood must not fill Tier 2 by machine | Under a burst, Tier 1 sees candidates and decides | Measured peak on the real day: 1 new group per minute. A 90%/500 share limit was dropped: it blocked 277,495 of 287,591 correct E1 flows on real packets |
| An **unknown classification goes to Tier 2** (V3 rule, `4e3a54a`, before this branch) | A type the system cannot classify should not be closed by Tier 1 | The expert classifies it | V3.1 replay: 1 auto case in 165 alerts. Cost: extra Tier 2 work for unknown types |

## 4. Tier 1 work

| Choice | SOC problem | Analyst use case | Evidence |
|---|---|---|---|
| **Opening a row claims it** | Two analysts must not work the same alert | The second analyst sees "In Review — Glenn Ang" and moves on | `shared-work.spec.ts` (3 analysts, contention); `soc-flow.spec.ts` step 2 checks the stored claim |
| **Claim expires after 15 min idle**; Release with reason; admin release needs a reason (D5, C7) | A claim left by someone off shift blocks the alert | Shift change: release your claims, or a lead releases them | `test_work_release.py` 15 tests; 9 of 9 planted defects caught; `soc-flow.spec.ts` step 8 (Release -> stored `available`) |
| **Why Tier 2 panel**: the reasons, then Escalate or Keep in Tier 1, a reason required (C3) | A machine recommendation must not decide alone | The analyst confirms or rejects with one short reason ("Time constraints" is enough) | `test_tier2_recommendation_panel.py` 16 tests; 11 of 11 planted defects caught; `soc-flow.spec.ts` step 4 (case opened, work `escalated`) |
| **One verdict form, 4 outcomes**; each maps to a guardrailed score change (D2) | Verdicts must teach the system without letting one person swing it | Confirmed +10, Suspicious 0, Expected -15, False positive -30, Escalate +15 | `test_verdict_bridge.py` 19 tests; 9 of 9 planted defects. Live: false positive on a group moved it from rank 1 to 75 |
| **Learning gate: 3 agreeing verdicts at 0.67** before a family moves | One wrong verdict must not move a family | The analyst's verdict counts, but alone it does not re-rank similar alerts | Settled decision; `verdict-memory.spec.ts`, `automatic-learning.spec.ts` pass |
| **Append-only notes**, only the claim owner adds (C6) | Notes must be a reliable record | "Checking scope" notes survive release and shift change | Database triggers refuse update/delete; `test_alert_notes_v2.py` 10 tests; `soc-flow.spec.ts` step 3 checks the stored author |
| **Flow & Score tab**: 7 read-only cards for flow alerts (C5) | An analyst must see the evidence, not only a score | Ports, packet counts, rule clauses, model features in one place | `soc-flow.spec.ts` step 5; `06-flow-score.png` |

## 5. Tier 2 work

| Choice | SOC problem | Analyst use case | Evidence |
|---|---|---|---|
| **Case list opens on Active** (open + investigating); resolved cases stay findable (D1) | Closed cases clutter the expert's list | The expert sees open work; an auditor filters "Resolved" | `case-resolution.spec.ts` and `soc-flow.spec.ts` step 7 check both directions |
| **Escalated by** column names the person or "Rule" | The expert needs the source of the case | Ask the Tier 1 analyst, or read the rule | `08-case-list.png` |
| Start -> Conclusion -> Resolve; **Resolve stays off until a conclusion exists** | A case must not close without a finding | The case record always holds a finding and a reason | `case-resolution.spec.ts` (button disabled first); `soc-flow.spec.ts` step 7; stored status `resolved` |
| **Response plans are approved, never executed** | The tool has no authority to block hosts | The expert records the plan; another system or person acts | Screen: "APPROVAL DOES NOT EXECUTE THE ACTION." (`10-resolved.png`); `case-resolution.spec.ts` asserts no `/execute` request |
| **Resolved case is read-only** (UI and server) | A closed record must not change | Audit trail stays fixed | `case-resolution.spec.ts`: note after close -> HTTP 409 |

## 6. Accountability

| Choice | SOC problem | Analyst use case | Evidence |
|---|---|---|---|
| **Every "who acted" line shows the person's name** (`/api/auth/actors`, commits `bcee22a`, `598210c`) | "Actor #1" cannot be read in a review or an audit | A lead reads "Escalated by Glenn Ang" | 0 screen strings print "actor #" (search of `apps/web/src`, case-insensitive). `test_actor_names.py`; `suricata-routing.spec.ts` asserts the name and no "Actor #" |
| Each claim, release, note, verdict, escalation and resolution writes an **audit event with the actor** | Auditors must replay the work | Shift lead review; incident report | `soc-flow.spec.ts` reads each stored row after each step |

## 7. Limits a SOC reviewer must know

These are measured or recorded limits, not hidden faults.

1. **The data is recorded, not live.** The demo queue is CSE-CIC-IDS2018 flows. Real packet replay exists
   (3 slices, 27,516 flows) but is not a continuous live sensor.
2. **The 0.9882 macro F1 is a testbed result.** It is not a real-world detection rate.
3. **Suricata-plus-ML corroboration on real traffic is not measured.** E1-suricata is ON by decision
   (D3, risk accepted). On the recorded day, Suricata fired 46 SSH scan alerts and no FTP brute-force rule.
4. **Expiry runs only when someone claims.** No scheduler sweeps idle claims (`PHASE-C-STATUS.md`).
5. **No return path from Tier 2 to Tier 1** (D8 deferred).
6. **The "Operational Priority" number on screen is the routing-time value.** The queue orders by the
   priority plus the verdict change. The screen does not show the adjusted value.
7. **Mixed-source queue order** (Suricata and flow together) is proven by tests only. The routed demo copy
   holds flow alerts only.
8. **Prospective collection and the old S16 console have no browser test** (`RETIRED-SPECS.md`).

## 8. What a SOC expert should try first

The short demo guide (`test-results/soc-guide/` images, built by `soc-flow.spec.ts`) follows sections 2–6
in order. The self-test checklist lets an analyst repeat each step on their own copy.
