# Ranking selection experiment — method

Design: `docs/ranking-and-escalation-design.md` §6. Code: `packages/detection/ranking/`.

1. **Data.** All 5,000 demo flows, fused by the production engine (S5 rules + S6 fusion), ordered by
   timestamp. First half = calibration (the past); second half = future (never shown to the analyst).
2. **Families.** *Coarse*: predicted class + destination port + protocol + matched rule; unflagged
   flows add the destination IP. *Fine*: every flow adds the destination IP. A verdict updates its
   family; future members inherit the family's state.
3. **Simulated Tier 1 analyst.** 10 rounds; each round reviews the top 25 unreviewed
   calibration alerts plus 5 randomly sampled unflagged ones (QA sampling). Verdict =
   ground truth, flipped with probability 0 %, 5 % or 15 % (analyst error).
4. **Arms.** Formulas C0-C3 x movement M1/M2 x guardrails on/off x agreement gate on/off x family
   key coarse/fine x error rate x 3 seeds.
   Guardrails off removes the caps, floors, I3 and tier-loss protection; the 0-100 range remains.
   The gate (the collaborator's aggregation rule) applies a family's learning only once it has at
   least 3 learning verdicts, no tie, and a dominant direction holding at least
   0.67 of them - and then only the learning that points that way.
5. **Metrics, future half only**: precision in the top 50/100/200; mean attack position (0-1, lower
   is better); last attack position; benign alerts in the top 100; Critical floor violations;
   true attacks demoted; Tier 2 load and precision; class changes during calibration.
6. **Selection (sel-3), fixed in code before the run.** Candidates: guarded, gated arms.
   Ranked by: the step depends on the attack type's severity (Q27 - C0 does not); safety (no floor
   violation at any error rate, no attack demoted at 0 % error); fewest true attacks demoted under
   analyst error (5 % + 15 %); highest Tier 2 precision at 5 %; lowest mean attack position at 5 %;
   fewest class changes; then the simpler formula, movement and family key.
   History: *sel-1* (run 20260911T111249Z) could not discriminate - the control already scores 1.0
   in the top 100. *sel-2* (run 20260911T111625Z) was written after run 1, and its deciding metric
   traced to one family collision (changelog v1.12).
