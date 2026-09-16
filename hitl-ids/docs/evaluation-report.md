# S15 — the three-arm evaluation: method and first result

**Run** `20260916T063856Z` · commit `650d844` · pre-registration `s15-preregistration-1`
(digest `079a194282a6324e`) · 40 verdicts · **444 tests pass, 0 skipped**

> **Re-baselined in v1.31.** The queue order changed: it was band-then-score, and it is now
> severity-then-score (changelog v1.30/v1.31). The band put Tier 2 candidates that are not severe at
> the top of the queue, so it was demoted to a label. Every number below is the **new** run. The
> previous run, `20260912T032022Z`, reported **precision@50 falling 1.000 → 0.980 under feedback, with
> one false positive in the top 50 and a benign alert promoted to rank 1**. Under the new order
> **none of that happens**: precision@50 holds at 1.000, the top 50 carries zero false positives in
> every arm, and the promoted benign alert reaches only rank 186. That earlier result is preserved in
> `evaluation/three-arm/runs/20260912T032022Z/` and in the changelog. Nothing was deleted — the
> measurement changed because the product did.

Reproduce with:

```
python scripts/run_detection.py       # if data/demo.db is absent
python scripts/run_evaluation.py      # ~3 s
```

Full record: [`../evaluation/three-arm/`](../evaluation/three-arm/) — `history.jsonl` plus
`runs/20260912T032022Z/{config,results}.json`.
Method: [`METHOD.md`](../evaluation/three-arm/METHOD.md).

---

## 1. What was run

| Arm | Feedback | Guardrails | Purpose |
|---|---|---|---|
| **A — control** | none | on | what the system does unaided |
| **B — treatment** | 40 scripted verdicts | on | the claim being tested |
| **C — guardrail probe** | the same 40 | **off** | what the guardrails prevented |

**The arms are byte copies of one detection database.** Dataset, model version (`xgb-8class-20260911`),
rule-set version (`s4b-1`) and seed (`20260911`) are therefore identical *by construction*, not by
promise, and the only two things that differ are the feedback sequence and `guardrails_active`.
Re-running detection three times would have been weaker: it would put the whole pipeline's
determinism between the arms and the comparison, leaving any difference ambiguous.

**Reproducibility (NFR-05).** Verdict timestamps are pinned (`2026-01-01T00:00:00Z` + n seconds),
never wall-clock. Two independent evaluations produce byte-identical metrics;
`tests/test_evaluation.py` asserts it.

## 2. The pre-registered sequence

Plan v0.2 set the exit criterion *"run C shows ≥ 1 critical suppression that run B prevents (if
zero, the scripted sequence is too weak — strengthen it)"*. That instructs tuning the experiment
until it yields the wanted answer, and v0.3 struck it out. The sequence is instead **derived by a
rule fixed before any arm ran**:

1. **Domain** — alerts a detector flagged (every band but `none`), in the queue's contract order:
   what an analyst actually works down.
2. **Subset** — at most 5 per family, only from families of ≥ 8 members, so every judged family
   keeps untouched members. Without that, an effect on *similar* alerts is unmeasurable.
3. **Size** — the first 40 alerts satisfying 1 and 2.
4. **Category from ground truth** — an *oracle* analyst: benign → `mark_false_positive`;
   attack of chart severity ≥ 7.0 → `escalate`; any other attack → `confirm_true_positive`.

It selected **40 verdicts across 8 families, 5 each**: Brute Force (TCP/21 and TCP/22), DDoS, DoS,
Botnet, Web Attack, and Infiltration on TCP/443 and TCP/31337. Categories: 25 `escalate`,
15 `confirm_true_positive`, and — see finding 5 — **zero dismissals**.

## 3. Results, as measured

| | A — control | B — treatment | C — guardrails off |
|---|---|---|---|
| Verdicts applied | 0 | 40 | 40 |
| Precision @10 / @50 / @200 | 1.000 / 1.000 / 1.000 | 1.000 / **1.000** / 0.990 | 1.000 / 1.000 / 0.990 |
| False positives in top 50 | **0** | **0** | **0** |
| MRR of true positives | 0.0074804 | 0.0074742 | 0.0074742 |
| Mean rank of true positives | 511.1 | 511.6 | 511.6 |
| Critical preservation rate | 1.000 | 1.000 | 1.000 |
| Critical floor breaches | 0 | **0** | **0** |
| True positives suppressed | 0 | **0** | **0** |
| Guardrail actions | — | `capped` 40 | `capped` 40 |

**Detection metrics are identical in all three arms** (macro F1 0.9884; Infiltration recall 0.875;
Web Attack precision 0.9672). Feedback reordered the queue and did not touch the detector — which is
the difference between reordering alerts and quietly retraining a model.

## 4. Findings

**1 — Similar-alert learning works, and stays where it was taught.** All 8 judged families opened
their gate at agreement 1.000. Of the 805 untouched members of those families, **205 were adjusted,
681 changed rank, and 9 true positives were promoted**. Of the **4,155 alerts outside any judged
family, 0 were adjusted** — no score, no band, and only 1 changed rank, which is other alerts moving
past it. This is S7b's core claim, measured on a real database, and it holds.

**2 — It promoted two benign alerts, the best of them only to rank 186.** Alert 11 — a genuinely
benign flow the model classifies as `Web Attack` — sits at rank 442 in the control. Five `escalate`
verdicts on *other* members of its family opened the gate, the family adjustment lifted it
99.89 → 100.0, and it surfaced at **rank 186**. This is the mechanism's cost, and it is intrinsic
rather than a bug: a family is a coarse key, so a false positive sharing an attack family with
confirmed attacks inherits their promotion. **Under the band order this same alert reached rank 1**,
which is the harm that re-ordering by severity removed: severity caps what a promotion can do,
because a `Web Attack` cannot be graded above High.

**3 — Feedback no longer damages the top of the queue.** The control's precision is **1.000 at every
cut-off to 200**; the flagged queue holds **2 false positives in 996 alerts**. There was no false
positive at the top to clean up, so feedback could only disturb a perfect ordering, never improve it.
Under the band order it did: precision@50 fell to 0.980 and a benign alert reached rank 1. **Under
the severity-first order the top 50 is untouched — 0 false positives in every arm, precision@50
1.000** — and the disturbance is confined to the slow metrics (precision@200 −0.01, mean rank
−0.515). This is the testbed artefact the handover already flags, surfacing in a third place: a macro
F1 of 0.9882 leaves the feedback loop nothing to correct.

**4 — Score saturation leaves the ranking formula no headroom.** **975 of 996** flagged alerts sit
at exactly 100.0, across only **13 distinct scores**. A confirming verdict on an alert already at 100
is clamped to 100 — every one of the 40 verdicts was recorded `capped`, by `score_range_clamped`
alone. Ordering inside the top band therefore falls to the contract's `id ASC` tie-break rather than
to anything the analyst said. Only 1 of the 40 judged alerts changed score at all.

**5 — Arm C has no power on this sequence, and that is a property of the rule.** C is identical to B
in *every* metric. The reason is structural: the oracle analyst plus a near-perfect detector produced
**no dismissals**, and every guardrail that could have bound — the −30 cap, the Critical floor (70),
the Infiltration floor (75) — protects against *downward* pressure. The only guardrail with anything
to do was the 0–100 range, which is not a policy. **Zero suppressions is recorded as measured**, per
the plan's exit criterion. But it must be read as *"this sequence could not test the guardrails"*,
not as *"the guardrails are unnecessary"* — a distinction the raw number does not make on its own.

**6 — `signature_override` has zero instances, so I3 is untested here.** The corrected dataset's
`signature_only = 0` finding means no alert carries that evidence class. Preservation is reported as
`alerts: 0, preservation_rate: null` with an explicit note, rather than as a flattering 100%.
Invariant I3 is guaranteed by S7's unit tests, not by this evaluation.

**7 — A nomenclature hazard worth fixing before the viva.** Five judged `ml_only` alerts were
promoted one band and now sit in the band *named* `signature_override`, while their `evidence_class`
remains `ml_only`. The queue bands reuse the evidence-class names, so a band can appear to claim
evidence the alert does not have. "Why is a model-only alert in the signature-override band?" is an
easy question to ask and an awkward one to answer.

**8 — The rule's `max_per_family = 5` saturates M1 exactly.** M1's class offset accumulates one band
per confirming verdict and clamps at −5. Five verdicts per family therefore drive every judged
family's untouched members the *full* distance to the top band rather than one step. The value was
chosen to clear the gate's minimum of 3 while leaving members untouched; that it also maximises the
movement is a coincidence of the rule, recorded here rather than quietly re-tuned.

## 5. What this supports, and what it does not

**Supported.** Feedback reorders the queue without touching detection. Similar-alert learning reaches
untouched members of judged families and reaches nothing else. The guardrails let no true positive be
suppressed and breached no floor. The whole thing reproduces byte-for-byte.

**Not supported.** That feedback *improves* triage efficiency. On this sample it measurably did not —
it moved a false positive to the top of a queue that was already perfect. The efficiency claim
remains untested, exactly as `ranking-and-escalation-design.md` §8 predicted it would be without a
weaker or drifting detector.

**Not tested at all.** The guardrails' protective value (finding 5), invariant I3 (finding 6), and
any behaviour under a fallible analyst — the oracle is a ceiling, not a simulation.

## 6. For the project lead

1. **The efficiency question needs the stress test** named in `ranking-and-escalation-design.md` §8:
   a weaker or drifting detector, so the top of the queue holds false positives to learn from. The
   harness supports it — it takes any detection database. It must be pre-registered and reported as a
   *separate, clearly-labelled* experiment, never folded into the headline.
2. **A dismissal-direction sequence is needed for arm C to have any power.** That means a second
   pre-registered rule, fixed before running, drawing from the queue's false positives. Proposed, not
   adopted: changing the rule after seeing a result is precisely what v0.3 forbids, so this is your
   call.
3. **Finding 2 is a genuine design cost.** Options: accept it and present it as the honest trade-off;
   add the fine family key (open question 2b) as defence in depth; or require corroboration before a
   family promotion may cross a band.
4. **Finding 7** — rename the queue bands, or accept the collision knowingly.
