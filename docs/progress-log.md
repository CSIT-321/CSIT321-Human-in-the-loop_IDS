# Progress Log

## Week 1

- Understood the project title and description.
- Identified the main idea: combine intrusion detection alerts with human feedback.
- Created initial documentation structure.
- Listed possible dashboard features and technology choices.
- Created a high-fidelity hardcoded frontend prototype using `prototype-demo/index.html`, `prototype-demo/styles.css`, and `prototype-demo/app.js`.
- Added dynamic SOC-style dashboard UI with alert queue, explanation panel, feedback controls, adaptive scoring, KPI cards, and charts.
- Verified that feedback changes risk scores and updates dashboard metrics.
- Separated documentation into `docs/` and the current demo into `prototype-demo/` so future formal development can be added cleanly.

## Week 2

- Fixed sidebar view-switching UX so Operations, Investigations, Feedback Model, and Reports behave like separate views.
- Ensured hidden sections are fully removed from display, sidebar active state stays consistent, and switching views scrolls back to the top of the selected workspace.
- Documented the Stage 1 dataset plan: CSE-CIC-IDS2018 will be the formal dataset source, sampled from raw CSV files and converted into dashboard-style IDS alert JSON under the future `stage-1/` folder.
- Selected CSE-CIC-IDS2018 as the formal dataset for Stage 1.
- Added Stage 1 folder structure for raw data, processed alert JSON, and sampling script preparation.
- Kept current prototype mock data unchanged.
- Added Stage 1 alert schema documentation to define the processed dashboard alert format for future CSE-CIC-IDS2018 integration.
- Added a Colab/Jupyter preprocessing notebook template for CSE-CIC-IDS2018 Stage 1 data exploration.
- Added a preprocessing log to record dataset files, sampling ratio, cleaning decisions, and output JSON details.
- Kept final reusable preprocessing logic planned under `stage-1/scripts/sample_cse_cic_ids2018.py`.
- Inspected the local CSE-CIC-IDS2018 `archive.zip` and updated the notebook to handle its mixed CSV schema, including files without `Src IP` and `Dst IP` columns.
- Improved the Stage 1 preprocessing notebook with stratified sampling, formal label mapping, severity/risk score mapping, stronger schema validation, and preprocessing summary records.
- Added a Stage 1 data processing summary text file describing the planned CSE-CIC-IDS2018 loading, cleaning, sampling, label mapping, severity/risk mapping, alert conversion, validation, and JSON export workflow.
- Validated the generated Stage 1 `sample-alerts.json`, copied it into `stage-1/data/processed/`, and recorded preprocessing run details including sample counts, distributions, validation checks, and current label-mapping limitation.
- Updated the Stage 1 preprocessing notebook to audit labels across all available CSE-CIC-IDS2018 CSV files and sample by mapped dashboard attack type so future samples can cover all available attack categories.
- Finalized Stage 1 attack label mapping so web attack variants such as `Brute Force -XSS`, `SQL Injection`, and `Brute Force -Web` map to `Web Attack`, and repaired the existing repository sample so it no longer contains `Unknown Attack` records.
- Validated and copied the final 1000-alert Stage 1 processed sample into `stage-1/data/processed/sample-alerts.json`, with 500 benign alerts, 500 malicious alerts, and no `Unknown Attack` records.

## Week 3

- Refined the project direction into a staged Hybrid Human-in-the-Loop IDS Dashboard.
- Planned the formal pipeline as Stage 1 dataset preprocessing, Stage 2 flow-based signature detection, Stage 3 XGBoost ML detection, Stage 4 fusion, Stage 5 human feedback and Exception Memory, Stage 6 dashboard integration, and Stage 7 evaluation.
- Started Stage 2 by adding a standalone flow-based signature detection engine.
- Corrected the Stage 2 signature engine direction so rules use flow-level features instead of dataset-derived `attackType`, while `attackType` and `groundTruth` remain for evaluation only.
- Split Stage 1 processed outputs into feature-only detection input, ground-truth evaluation labels, and a dashboard-ready labelled sample to prevent future detection engines from using answer fields.
- Added environment documentation for Node.js and Python requirements, including a portable Node.js option for running Stage 2 without modifying the system PATH.
- Added formal signature-based detection design documentation explaining Stage 2 flow-level rules, allowed input fields, forbidden label-derived fields, heuristic limitations, and the role of signature evidence in the later Fusion Engine.
- Hardened Stage 2 signature rules by renaming rule output metadata to `predictedAttackType`, adding prototype heuristic validation status and rationale, and generating formal post-prediction evaluation summaries.
- Added a formal signature rule rationale document explaining how each Stage 2 rule was derived, why the selected flow features are reasonable, why the current perfect result should be interpreted carefully, and why threshold tuning is deferred until further validation.
- Added Stage 2B feature distribution audit to analyse rule feature distributions, rule boundary behaviour, benign near-misses, and rule strength without changing thresholds or performing tuning.
- Refined Stage 2B benign near-miss logic so near-miss records must be close to important numeric rule thresholds instead of merely matching broad conditions.
- Started Stage 3 by adding an XGBoost ML detection scaffold, including training notebook template, script structure, model artifact plan, prediction output plan, and documentation for feature-label separation.
- Upgraded the Stage 3 XGBoost notebook into a Colab-ready training workflow covering dataset loading, cleaning, label mapping, feature selection, XGBoost training, evaluation, artifact export, and sample ML prediction generation.
- Added KaggleHub as a Stage 3 notebook dataset input option so Colab training can download `solarmainframe/ids-intrusion-csv` directly instead of requiring manual archive upload.
- Adjusted the Stage 3 Colab notebook with memory-safe defaults, CSV row caps, optional CSV file limiting, numeric downcasting, and smaller class sampling to reduce RAM crashes during XGBoost training.
- Imported Stage 3 Colab-generated XGBoost artifacts, sample ML predictions, and evaluation summaries into the correct `stage-3/models/`, `stage-3/outputs/`, and `stage-3/evaluation/` folders.
- Added a Stage 2 signature detection notes notebook with a more natural walkthrough for checking feature-only input, signature rules, signature output, evaluation summaries, and Stage 2B audit files.
- Added Stage 3 checks for missing expected attack classes, including Infiltration, by printing raw label distributions, mapped class distributions, dropped-row diagnostics, and warnings when expected classes are absent from the trained model.
- Documented the current Stage 3 limitation that the imported XGBoost model is a six-class prototype and does not include the expected Infiltration class, which remains a future retraining requirement.
- Added Stage 4 Fusion Engine to combine Stage 2 signature evidence and Stage 3 XGBoost predictions into fused alert risk scores, decisions, and explanations, while explicitly handling the current Stage 3 Infiltration limitation.

## Week 4

- Diagnosed the Stage 4 fusion output showing `1000 + 2186 = 3186` records instead of a true fusion: Stage 2 signature output (1000 `AL-XXXX` records, from the Stage 1 sample) and Stage 3 ML predictions (2186 records) were never the same flows. Stage 3's predictions came from the trained model's own internal Colab train/test split of the full KaggleHub dataset, with row-index ids unrelated to Stage 2, and the feature schema also did not match (Stage 1's `flow-feature-sample.csv` has 17 dashboard-only columns, while the trained model expects the full 79 raw CSE-CIC-IDS2018 feature columns).
- Fixed the Stage 4 Fusion Engine (`stage-4/core/fusion-engine.js`, `stage-4/scripts/run-fusion-demo.js`) so fusion scope is defined by Stage 2 signature records instead of unioning both id sets. Stage 3 predictions are only joined in when their id matches; unmatched Stage 3 predictions are now reported separately as out-of-scope instead of inflating the fused alert count.
- Updated the Stage 1 preprocessing notebook to additionally export `flow-feature-full.csv`: the full raw-feature columns for the same 1000 sampled rows, in the same row order used to assign `AL-XXXX` ids, so Stage 3 has a feature-only input that actually matches Stage 2's sample.
- Updated the Stage 3 training notebook to add a prediction step that runs the already-trained model on `flow-feature-full.csv` and writes `ml-predictions.sample.json` keyed by `AL-XXXX` ids, aligned with Stage 2. Renamed the notebook's previous internal test-split predictions to `held-out-test-predictions.json` since that split is for model evaluation only and should not be consumed by Stage 4.
- Imported the regenerated Stage 3 artifacts from the latest Colab run. `ml-predictions.sample.json` now uses aligned `AL-XXXX` ids for the Stage 1 / Stage 2 sample, while the notebook's internal model test predictions are kept separately as `held-out-test-predictions.json`.
- Reran Stage 4 fusion with the aligned Stage 3 predictions. The fused output now contains 1000 alerts, matching the Stage 2 signature scope, instead of incorrectly combining unrelated Stage 3 held-out test rows into the dashboard fusion output.
- Improved Stage 4 prototype evaluation with classification metrics, fusion behaviour metrics, risk prioritisation metrics, and analyst review metrics so the Fusion Engine is evaluated as more than a simple classifier.
- Added binary TP/TN/FP/FN detection metrics to the Stage 4 evaluation using malicious as the positive class and benign as the negative class.
- Hardened Stage 4 fusion alignment reporting by adding ID overlap metrics, out-of-scope ML prediction ID samples, low-overlap warnings, and clearer documentation for Stage-2-scoped fusion mode.
- Added Stage 5 Human Feedback and Exception Memory prototype to apply simulated analyst feedback, adjust current alert risk scores, preserve original fusion scores, and evaluate before/after workload and false-positive priority effects.
- Clarified Stage 5 guardrail evaluation metrics by separating score adjustment guardrails from exception trust-gate rejections for more accurate report interpretation.
- Added Stage 6 React dashboard integration to visualise Stage 5 feedback-adjusted alerts, including alert queue, KPI cards, filters, score comparison, signature evidence, ML prediction, fusion evidence, and feedback adjustment details.
- Clarified Stage 6 dashboard model confidence wording and formatting so near-100% XGBoost scores are displayed as confidence scores rather than absolute certainty.
- Adjusted Stage 4 ML-only fusion scoring so high-confidence ML predictions without signature support remain review-worthy but are slightly discounted, preserving Signature + ML agreement as the strongest evidence case.
- Upgraded the Stage 6 React dashboard layout using the uploaded SOC-style HTML prototype as a visual reference while keeping the implementation in React, Vite, and TypeScript.
- Added Stage 6B simulated alert replay and UI-only analyst feedback controls to demonstrate human-in-the-loop triage without backend persistence or live packet capture.
- Added a Stage 6B Latest Activity replay feed so the dashboard can show newly replayed alerts gradually in arrival order, separate from the risk-prioritised alert queue.
- Added attack type filtering to the Stage 6 dashboard so analysts can filter the queue by Benign, Botnet, Brute Force, DDoS, DoS, Web Attack, or any future attack type present in the replayed data.
- Added a dynamic internal structure HTML slide deck to explain the staged IDS pipeline, data separation, detection engines, fusion, feedback, dashboard replay, and current prototype limitations.
- Clarified Stage 6 dashboard semantics by separating processed flow records, detection records, and actionable alerts. The dashboard now defaults to an Active Alert Queue instead of treating every processed flow as an active alert.
- Added sidebar and KPI breakdowns that distinguish processed flow records, detection records, active alerts, and suppressed/resolved records so the dashboard no longer implies that every flow is an alert.
- Updated dashboard-facing wording to describe the system as a unified pipeline instead of exposing internal stage numbers in the user interface.
- Strengthened the dashboard human-in-the-loop workflow by adding clearer UI-only analyst feedback impact, local risk-score adjustment summaries, guardrail messaging, and current-session feedback metrics.
- Improved signature evidence explanations by separating user-friendly summaries from technical rule conditions in the dashboard.
- Added feature-level Investigation context for selected detection records, including grouped flow features, case-style investigation timeline, ML-only signature gap explanation, and analyst recommendation.
- Added analyst feedback controls to the Investigation view so analysts can review feature-level evidence and apply feedback decisions without returning to Operations.
- Refined Stage 6 dashboard view structure so global operational metrics appear only in the Operations view, while Investigations, Feedback Model, and Reports focus on their specific workflows.
- Fixed Stage 6 dashboard correctness issues by propagating per-record ground truth after feedback evaluation, preventing Benign/Malicious filters from using predictions as truth, separating score guardrails from exception trust-gate rejections, and aligning local Expected Activity feedback with Stage 5.
- Updated the system architecture slide deck to reflect the current pipeline wording, ground-truth joining boundary, score guardrail versus trust-gate semantics, Operations-only global metrics, and Investigation feedback workflow.
- Started the ML explainability workstream by adding reproducible local Stage 3 inference from committed XGBoost artifacts, strict 78-feature validation, model provenance hashes, class probability output, and regenerated prediction evidence without retraining or changing the dashboard.
- Hardened Stage 3 local inference by enforcing stable alert IDs, validating the model/class/schema contract, blocking unsafe replacement of the Stage 4 ML sample input, and replacing the committed full regenerated prediction artifact with a compact reproducibility summary.
- Added native XGBoost TreeSHAP explainability for Stage 3 inference, explaining only the predicted class raw margin and recording compact explainability coverage without changing prediction, risk, fusion, dashboard, or HITL adaptation behaviour.
- Hardened Stage 3 TreeSHAP explanation integrity so failed additivity checks are not marked analyst-usable and explainability coverage reports prediction-unavailable, TreeSHAP-generation, and additivity-failure counts separately.

## Notes

Use this file to record weekly progress, decisions, problems, and next steps. Short but consistent updates are better than writing everything at the end.
