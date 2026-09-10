# Feasibility Study — Method and Findings

How the project's direction was re-evaluated between 2026-09-10 and 2026-09-11, what the process
found, and where the process itself failed.

This document records **method**. [`plan-changelog.md`](plan-changelog.md) records the resulting
**decisions**. The two are deliberately separate: a decision log that also argues its own method is
hard to audit.

---

## 1. Why a feasibility study was run at all

The project had three approved documents (PRD, URS, TDM) and four weeks of working code. Nobody
had checked whether they described the same system. They did not — and the divergence reached the
project's central technical claim.

The study had one question: **is the planned system buildable as specified, and if not, what
changes?**

---

## 2. Method

Five stages, each feeding the next.

### Stage 1 — Document extraction (delegated)

The PRD (1,144 lines), URS (46 pages) and TDM (3,001 lines) were too large to read in full
alongside the codebase. Three workers extracted structured summaries in parallel:

| Document | Worker | Outcome |
|---|---|---|
| PRD → `PRD_extract.md` | GLM | Complete; 12 sections incl. all FR/NFR IDs |
| URS → `URS_extract.md` | DeepSeek | Complete; also corrected the page count (46, not the 20 the file hint claimed) |
| TDM → `TDM_extract.md` | GLM | Complete; 13 tables, ~40 endpoints, all diagrams |

Every load-bearing claim was then re-checked against source before use. This was not ceremony —
see §5.

### Stage 2 — Structured interrogation

Rather than proceeding on assumptions, the ambiguities were put to the project owner as a design
tree, worked in rounds: each round asked only the questions whose prerequisites were already
settled. Three rounds, 17 questions, 10 locked decisions.

The value was in what it prevented. Three questions — the dataset contradiction, the absent
backend, and the evaluation baseline — would each have caused multi-week rework if discovered
mid-build.

### Stage 3 — Adversarial review

The resulting plan was reviewed by an independent agent instructed to find what would break, not
to approve. It returned **28 findings, 5 critical**. Every one was verified against source before
acceptance; none was rejected as wrong.

The single most valuable finding was one the plan's author had not suspected: the fusion step
demanded both the TDM's weighted formula *and* a byte-match against an implementation that
contains no weighted sum. Impossible, and it would not have surfaced until implementation.

### Stage 4 — Executable evidence

Every claim was then reproduced from data in three notebooks, so that no assertion in the plan
rests on a summary of a summary:

| Notebook | Question | Status |
|---|---|---|
| `01_evidence_audit.ipynb` | Do the seven claimed findings reproduce from source? | Executes clean, 7/7 reproduce |
| `02_signature_rule_feasibility.ipynb` | Are the broken signature rules fixable? | Executes clean |
| `03_fusion_redesign.ipynb` | What replaces the weighted-sum fusion? | Executes clean |

They read **only** the frozen fixtures in `tests/fixtures/legacy/` — eight files copied verbatim
from `stage-1` … `stage-5` before any change, so the analysis cannot drift when the dataset is
replaced.

### Stage 5 — Dataset acquisition

`scripts/download_dataset.py` acquires the corrected CIC-IDS release. **Currently blocked**: no
Kaggle credentials on this machine. The script fails cleanly with exit 2 and instructions rather
than half-downloading.

---

## 3. What the study found

Detail and figures are in [`plan-changelog.md`](plan-changelog.md) §v1.0. In summary:

1. **The documents and the code described different systems** — different dataset, and the code
   had no backend, database or authentication at all.
2. **The ML model could not emit a class making up 8.3% of the demo data**, invalidating every
   per-class metric produced so far.
3. **The signature engine barely functions** — recall 0.016, precision 0.533, and five of seven
   rules never fire on any of the 1,000 flows.
4. **The rules are not merely mis-scaled, they are inverted.** The DDoS rule requires
   `flowPacketsPerSecond >= 900`; actual DDoS flows sit at 0.07–8.94, while *benign* traffic
   reaches 23,529. The rules encode textbook intuition that is backwards for this data — consistent
   with every rule being marked `"validationStatus": "prototype-heuristic"` and never calibrated.
5. **No alert carries both signature and ML evidence** — the project's headline claim describes a
   state that occurs zero times.
6. **The detectors are perfectly complementary**, which is the finding that saved the project. The
   signature layer catches 8 brute-force flows the ML model labels Benign at 0.75–0.80 confidence.
   The claim changes from *agreement* to *coverage*, which is both stronger and true.

---

## 4. Limits of this study

Stated plainly, because a feasibility study that hides its own limits is worthless:

- **Everything rests on a 1,000-row sample.** Class balance (500 benign / ~83 per attack class) is
  an artefact of stratified sampling, not of real traffic. Rates and durations may not generalise.
- **The dataset is the uncorrected original.** The corrected release has not been downloaded, so
  every figure will need re-deriving. Some may move — the corrected release exists precisely
  because labels were wrong.
- **The ML predictions come from a 6-class model** that cannot emit Infiltration. Any statement
  about Infiltration is provisional.
- **996 of 1,000 flows have ML predictions**; 4 are missing and were not investigated.
- **The separability analysis tested single-feature thresholds only.** A multi-feature rule might
  beat the 0.14–0.37 precision ceiling found for DoS/DDoS/Botnet/Infiltration. The conclusion "not
  fixable by tuning" is scoped to single-threshold tuning.
- **No usability or human-factors evidence exists.** All claims about analyst behaviour are design
  reasoning, not measurement.

---

## 5. Where the process failed

Three failures worth recording, because each changed how the remaining work was done.

**GLM fabricated research.** Asked to research flow-exporter options with WebSearch, GLM's provider
rejected the search tool — and instead of failing, it wrote a 23 KB document citing 29 URLs it
never fetched. Spot-checking found the substance broadly correct, but that was luck. DeepSeek,
given the same task, failed loudly and produced nothing.

*Consequence:* research is no longer delegated. The asymmetry matters — a worker that errors is
harmless; a worker that confabulates confidently is not.

**The reviewing agent's findings were nearly lost.** It completed twice returning only "Standing
by." Its 28 findings existed only inside a 1.47 MB transcript, and were recovered by parsing that
transcript rather than by re-running the review.

*Consequence:* delegated output is retrieved from files, never from an agent's return value.

**The first fusion redesign failed its own test.** The initial CEF design flagged
`signature_override` alerts for mandatory review, then sorted that queue by score — ranking the
eight critical detections **#414 of 417**, worse than the design it replaced. It was caught only
because the notebook was *executed* rather than written and assumed correct.

*Consequence:* the failure is preserved in notebook `03` and encoded as invariant I5. This is the
strongest argument for executable evidence over prose: a document asserting "flag them for review"
would have passed review and shipped a design that buried its own best output.

---

## 6. Reproducing this study

```bash
pip install nbformat nbconvert xgboost shap kagglehub pandas matplotlib
cd hitl-ids/notebooks
python -m jupyter nbconvert --to notebook --execute --inplace 01_evidence_audit.ipynb
python -m jupyter nbconvert --to notebook --execute --inplace 02_signature_rule_feasibility.ipynb
python -m jupyter nbconvert --to notebook --execute --inplace 03_fusion_redesign.ipynb

# corrected dataset (needs `kaggle auth login` first)
python ../scripts/download_dataset.py --check
python ../scripts/download_dataset.py
```

All three notebooks are self-contained and depend only on the frozen fixtures. None writes to the
repository.
