# Ranking selection experiment — method

Design: `docs/ranking-and-escalation-design.md` §6. Code: `packages/detection/ranking/`.

1. **Data.** All 5,000 demo flows, fused by the production engine (S5 rules + S6 fusion), ordered by
   timestamp. First half = calibration (the past); second half = future (never shown to the analyst).
2. **Families.** Predicted class + destination port + protocol + matched rule; unflagged flows add
   the destination IP. A verdict updates its family; future members inherit the family's state.
3. **Simulated Tier 1 analyst.** 10 rounds; each round reviews the top 25 unreviewed
   calibration alerts plus 5 randomly sampled unflagged ones (QA sampling). Verdict =
   ground truth, flipped with probability 0 %, 5 % or 15 % (analyst error).
4. **Arms.** Formulas C0-C3 x movement M1/M2 x guardrails on/off x error rate x 3 seeds.
   Guardrails off removes the caps, floors, I3 and tier-loss protection; the 0-100 range remains.
5. **Metrics, future half only**: precision in the top 50/100/200; mean attack position (0-1, lower
   is better); last attack position; benign alerts in the top 100; Critical floor violations;
   true attacks demoted; Tier 2 load and precision; class changes during calibration.
6. **Selection.** Among guarded arms: zero safety violations first (no floor violations at any error
   rate; no attack demoted at 0 % error), then precision in the top 100 at 5 % error, then fewer
   benign in the top 100, then fewer class changes, then the simpler formula.

---

**Note added 2026-09-16 — `config.json`'s `params` key is a serialisation artefact.**
This run's `config.json` contains `"params": {"formula": "C2", "movement": "M1", ...}`. That block is
**not** a record of what ran: the experiment wrote `asdict(RankingParams())`, which dumps the
dataclass's own *defaults*, under a key that reads as "the parameters used". Every arm here ran its
own formula — the arms are enumerated in `experiment.py` (`for formula in FORMULAS` → C0/C1/C2/C3),
each run entry in `results.json` records its own `formula` and `movement`, and the selection outcome
is `results.json.selection`, whose winner for this run is recorded there.

The formula actually in force is **C1** (chosen by `sel-3`; the code passes `formula="C1"`
explicitly in `packages/detection/feedback/learning.py`). **Do not read `params.formula` as a
decision.** The block was replaced by `candidate_space` in the next run (`20260916T073135Z`), which
reproduced this run's selection exactly. This file is left unedited as the historical record.
