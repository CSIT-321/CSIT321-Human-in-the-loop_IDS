# Decision brief — final-product workflow (grilling session)

Each decision lists: the facts behind it (measured), the options, and the **workflow change** each option creates
against the intended workflow below. Facts are cited; inferences are labelled.

## The intended workflow (baseline every option is judged against)

1. **Admin** activates a database and starts arrivals (LCK, Workspaces page).
2. Alerts **arrive live** in the analyst console.
3. **Automation** handles what is safe to automate: some alerts go straight to Tier 2.
4. **Tier 1 analyst** sees every incoming alert and the Tier 2 candidates with the reasons; escalates, keeps, or
   records a verdict.
5. **Tier 2 analyst** sees only Tier 2 work; investigates and concludes.
6. The approved demo content stays: detection score, operational score, guardrails, family learning, the
   false-positive / missed-attack / family stories (`scripts/rehearse_demo.py`).

## Facts that change the options (measured 2026-11-05)

| # | Fact | Source |
|---|---|---|
| F1 | The live arrivals replay **200 Suricata alerts: 190 "SSH brute force", 10 "opaque anomaly", all severity 3, no ML model output.** | `evaluation/protocol-v3.1/workload/operational-workload.jsonl` |
| F2 | So **E1 (rule AND model agree) can never fire on the live replay** — there is no model on Suricata alerts. Under "E1 only", the live demo shows **0** automatic escalations. | F1 + `formulas.py` |
| F3 | The 1 automatic escalation in the replay today is one of the 10 "opaque anomaly" alerts (unknown classification rule). | replay DB, `system_routing.py:48-49` |
| F4 | E1 on the flow alerts: `demo.db` 200 escalated / 0 wrong; `stress.db` 148 / 0. E3: `stress.db` 648 / **342 wrong**. | `analysis/auto_escalation_safety.py` |
| F5 | The approved verdict has **5 categories**: confirm true positive **+10**, false positive **−30**, expected activity **−15**, needs investigation **0**, escalate **+15**. (My earlier "±30 / ±15 Likely…" labels were wrong; this is the code.) | `feedback/service.py:61-67` |
| F6 | LCK's verdict has **4 outcomes**: confirmed malicious, suspicious, expected activity, false positive. They map **one-to-one** onto 4 approved categories; the 5th, *escalate*, is already a separate Tier 2 action in LCK's design. **No information is lost by the mapping.** | `analyst_verdict.py:11` |
| F7 | The approved demo script uses `AL-03086`, an **unflagged** alert (bottom band, score 36.94), for "an attack both detectors missed, confirmed by a human". Phase A loads only the 996 flagged, so that step **cannot run**. | `scripts/rehearse_demo.py:48,151-155` |
| F8 | `/api/v2/alerts/summary` takes **8.2 s** with 996 alerts loaded; it is called on every arrival. 5,000 alerts would be slower until the fix (C8). | `spot_check.py` |
| F9 | Clicking a queue row claims the alert; a claim can never be released, even by an admin. | `analyst_work.sql:54-58`, `OperationalWorkstationPage.tsx:257-264` |
| F10 | LCK's selective review already marks some alerts `no_immediate_review` (deferred) — this is his "routine Tier 1 is automated" mechanism. | `selective_review_policy.py:14,117` |

## Q1 — Which alerts arrive live in the demo? (root: shapes Q4 and Q5)

| Option | Workflow change |
|---|---|
| **A. Both: the 200 Suricata replay AND the flow alerts arrive live, in capture order** (recommended) | Steps 1–6 all visible live. E1 auto-escalations appear as alerts arrive. Cost: a flow arrival source for LCK's replay (new work, Phase B). |
| B. Suricata replay live; flow alerts preloaded | Arrivals show Suricata only; automation shows 0 escalations live under E1 (F2). Flow alerts and their auto-escalations already sit in Tier 2 when the demo starts — automation is shown as a result, not as it happens. |
| C. Flow alerts only, Suricata replay dropped | Loses LCK's Suricata work and the "Suricata translated into our data types" direction the team agreed. Not recommended. |

## Q2 (D1) — Which store holds a flow alert's score and verdict?

| Option | Workflow change |
|---|---|
| **A. The approved engine stays the writer; the console reads it** (recommended) | A verdict on a flow alert moves its score within the guardrails, moves its unjudged family members, and the queue re-orders — exactly the approved demo. Suricata alerts keep LCK's behaviour (no score). |
| B. Copy into the new tables and keep both in step | Same visible behaviour, but two stores can disagree (S1-01); more code; more risk. |
| C. Drop the approved engine for flow alerts | The analyst's verdict changes nothing in the queue. **Loses guardrails and family learning — the core of the approved demo.** |

## Q3 (D2) — One verdict form, or two?

| Option | Workflow change |
|---|---|
| **A. One form, LCK's 4 outcomes; on flow alerts each is mapped to its approved category (F6); Escalate stays a separate button (+15 on flow alerts)** (recommended) | The analyst learns one form. Flow alerts still show the score chain and guardrail result after submit. Nothing lost (F6). |
| B. Two forms: 5 categories on flow alerts, 4 outcomes on Suricata | Matches each generation exactly, but the analyst sees two different forms in one queue; two vocabularies to document. |
| C. The approved 5 categories everywhere | Suricata alerts have no score to move, so +10/−30 means nothing there; LCK's memory learning must be re-keyed. |

## Q4 (D3) — What is automated?

| Option | Workflow change |
|---|---|
| **A. Auto-escalate E1 only. Unknown classification becomes a Tier 2 candidate for Tier 1 to review. Routine low-risk alerts deferred by LCK's selective review (F10).** (recommended) | Automation = E1 escalations + deferrals. Uncertain alerts reach a human at Tier 1 first. With Q1-A, E1 escalations appear live. |
| B. E1 + LCK's unknown-classification auto-case | Also auto-escalates the least certain alerts — contradicts "candidates that need a Tier 1 analyst before escalation". |
| C. E1 + E3 | 342 wrong escalations on the stress data (F4). Not safe. |

## Q5 (D4) — Which flow alerts enter the queue?

| Option | Workflow change |
|---|---|
| **A. All 5,000; unflagged in the bottom band** (recommended) | Keeps the approved "missed attack confirmed by a human" story (F7). Tier 1 sees every incoming alert, as the intended workflow says. Needs the summary speed fix (F8) first. |
| B. The 996 flagged only (Phase A today) | Smaller, faster queue; the missed-attack demo step is lost or rewritten. |
| C. 996 in the queue; unflagged reachable by search | Story kept only by searching an alert ID — not a real workflow. |

## Answers so far (round 1, 2026-11-05)

- **Q2 (D1) DECIDED:** the approved engine stays the writer for flow alerts; the console reads it.
- **Q3 (D2) DECIDED:** one form, LCK's 4 outcomes, mapped to approved categories on flow alerts; Escalate separate (+15).
- Q1, Q4, Q5 reopened. New facts (round 2):
  - F11 The 5,000 flow alerts are **CSE-CIC-IDS2018 flow records** (94 CICFlowMeter columns, `data/processed/demo_sample.csv`).
    They contain **no packets**, so they **cannot be fed through Suricata**. 0 `*.pcap` files exist under the FYP folder.
    Their "rule" detector is the project's own signature engine on flow features (`packages/detection/signature/engine.py`).
  - F12 The 200-alert live replay is **synthetic EVE** ("CONTROLLED V3 pattern …"), not real Suricata output. Real
    Suricata ran once, on LCK's machine, on 3 public PCAPs: 4 alerts admitted (`docs/real-suricata-pcap-validation.md`).
  - F13 Flow data by detector agreement (`analysis/soc_workload.py`): corroborated 200 (0 benign), ml_only 796
    (2 benign), none 4,004. E1 removes 200 of 996 flagged alerts (20%) from Tier 1 triage, 0 wrong.

## Answers so far (round 2, 2026-11-05)

- **Q4 DECIDED:** flow alerts: E1 auto-escalates; bottom band and family learning stay. Suricata: unknown
  classification -> Tier 2 candidate, no Suricata auto-escalation. **Plus** repeated Suricata alerts (same signature,
  same source) grouped into one Tier 1 item, and **every grouped item carries a visible "Grouped: N alerts" flag**
  with the member list. (Name search found no grouping in `triage_memory.py`; not confirmed it is absent.)
- **Q5 DECIDED:** all 5,000 flow alerts; unflagged in the bottom band; summary speed fix first.
- **Q1 REOPENED — contradiction found.** The user's model: "Suricata takes network flows and converts them into
  data that fits the flow summaries." The project's own record says this was tested and **rejected**:
  - `docs/HANDOVER.md:489` — "Suricata as the prefix module: REJECTED. Cannot emit CIC flow features; use the
    GintsEngelen CICFlowMeter fork instead."
  - `docs/detector-agnostic-hitl-architecture.md:182` — "Suricata ... cannot replace CICFlowMeter for the current
    XGBoost path: that model requires the CIC feature schema used in training."
  - The model needs **82** CICFlowMeter features (`models/feature-columns.json`).
- F14 The 5,000 are **not an obsolete pipeline**. They are the CICFlowMeter half of the real pipeline: Engelen et al.
  ran the CICFlowMeter fork on the CSE-CIC-IDS2018 packet captures (GintsEngelen/CNS2022_Code README). Suricata is
  the other half: it reads the same packets and gives rule evidence.
- F15 The original captures are on AWS open data (`registry.opendata.aws/cse-cic-ids2018`). One day is about
  37-42 GiB (ResearchGate listing — external, not verified by download).

## Q1 round 3 — how to make the product run start to end

Real pipeline: packets -> Suricata (rule evidence) + CICFlowMeter fork (82 features -> XGBoost) -> correlate by
5-tuple and time -> one alert with both detectors -> approved engine -> Tier 1 / Tier 2.

| Option | Workflow change | Cost / risk |
|---|---|---|
| A. Two workspaces, honest framing | Suricata workspace shows the live front end; flow workspace shows detection and learning. Not one input from start to end. | Least work; no new risk |
| B. Real end-to-end on one capture slice | One input from packets to Tier 2; E1 fires on live arrivals; the whole thesis in one demo | New correlation module; Java CICFlowMeter on Windows; ~40 GiB download; ground truth for the slice; must be spiked first |
| C. Drop the 5,000; Suricata only | Loses the ML model, scores, guardrails, family learning, E1, and every measured result | Contradicts the approved thesis |
| D. Generate EVE from the 5,000 | Looks end to end, but the sensor output is invented | Fake data; the project already rejected curated demo slices (`HANDOVER.md:490`) |

## Answers so far (round 3, 2026-11-05)

- **Q1 DECIDED: A + B-spike.** A (two labelled workspaces) is the committed plan. One time-boxed spike (1 day) tests
  B: packets -> Suricata + CICFlowMeter fork -> linked alert -> approved engine. Spike passes -> B is the live input;
  spike fails -> A stays.
- **Owner of the decision: Glenn Ang.** No supervisor sign-off needed (user's statement, 2026-11-05). This decision
  reverses the recorded `docs/HANDOVER.md:489` rejection only in this sense: Suricata is added **beside**
  CICFlowMeter, not as its replacement. Must be written into `docs/deviations.md` in Phase E.
- **User requirement for the spike:** the packet feed must give enough data to **both** workspaces to show the
  whole combined workflow.

## Answers so far (round 4, 2026-11-05)

- **Spike day DECIDED:** 2018-02-14 (`Wednesday-14-02-2018/pcap.zip`, 37.17 GiB, measured from the S3 listing).
  Demo data from that day: 533 flows (399 benign, 134 brute force); 135 flagged; **all 134 brute force are E1 in
  the demo data** (`analysis/e1_by_day.py`); holds the false-positive story `AL-00478`.
- **Spike pass criteria DECIDED:** (1) Suricata and CICFlowMeter both run on the same packets on this PC; (2) at least
  90% of Suricata alerts link to a CICFlowMeter flow by addresses, ports and time; (4) at least one alert where both
  detectors agree arrives live and E1 escalates it. Feature comparison deferred.
- Local readiness (measured): Java 21 present; Suricata **not installed**; C: 443 GiB free, D: 1.4 TiB free.
- **Q6 (D5) DECIDED:** claims expire after N minutes of no activity, plus Admin release. N still open.
- **Product framing (user, 2026-11-05):** sold as a SOC team product that raises analyst efficiency and response
  and fights alert fatigue. Documentation waits until the product is verified working.

## Answers so far (round 5, 2026-11-05)

- **Q7 DECIDED:** keep all 7 analyst menu entries as today. No menu change.
- **Q6 N DECIDED:** claim expires after **15 minutes** with no activity (open, note, verdict); Admin can change it in
  Governance; Admin release with a reason; every expiry and release audited.
- **E1 signal DECIDED: either one.** E1 = ML model agrees with **Suricata** OR with **our flow rule engine**, and
  score >= 80. Two branches: `E1-flow-rule` (measured: 0 wrong on demo and stress) and `E1-suricata`
  (**not measured** — no labelled Suricata data exists until the spike).
- **Q8-Q10 DECIDED:** Admin switch per automatic rule; keep a rate limit with a high threshold; Return to Tier 1 waits.
- Open: rate-limit form (see round 6) — any share-of-last-50 threshold below 100% trips on `demo.db` (peak share
  1.000, 134 E1 in a row; `analysis/e1_burst_profile.py`).

## Answers so far (round 6, 2026-11-05)

- **Rate limit DECIDED:** share limit, last **500** arrivals, threshold **90%**. When it trips, extra automatic
  escalations become Tier 2 candidates; nothing is closed or lost. Measured (`analysis/share_limit_500.py`):
  peak E1 share per 500 = **0.268** on `demo.db` (by id and by capture time), 0.184 on `stress.db`; **0 correct E1
  alerts blocked**. It trips only if 450 of 500 arrivals are automatic escalations.
  Limit: it has no effect until 500 alerts have arrived (inference from the window design).
- **E1-suricata start state DECIDED:** both branches ON from the start. Risk accepted by Glenn Ang: an unmeasured
  rule escalates without review; protection = rate limit + Admin switch per branch.

## Answers so far (round 7, 2026-11-05)

- **Grouping key DECIDED:** same Suricata signature + same source IP, any destination, within 30 minutes.
- **Group escalation DECIDED:** when any member qualifies (E1, or the analyst escalates), the whole group moves as one
  Tier 2 case, with the qualifying member marked.
- **Group verdict DECIDED (by orchestrator, on the user's delegation):** one verdict applies to every member; each
  member gets its own audit record naming the group verdict; the analyst can split out one member and judge it
  alone. **Family learning counts a group verdict once**, not once per member — the agreement gate counts verdicts
  (`packages/detection/ranking/formulas.py:140-147`), so N copies of one human decision would look like N
  independent confirmations and saturate the family. Guardrails still run per member on flow-linked alerts.
- Every grouped item shows a visible **"Grouped: N alerts"** flag and its member list (round 2).

## Later rounds (depend on these answers)

- Q6 (D5) claim release — who may release, and is click-to-claim kept? (F9)
- Q7 (D6) final product vs research pages.
- Q8 Suricata automatic rule (only if Q1 ≠ A, to keep automation visible).
- Q9 Admin switch per automatic rule; rate limit dropped (measured trip on correct E1 bursts).
- Q10 Return from Tier 2 to Tier 1 (migration 22) now or later.
