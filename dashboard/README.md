# React Dashboard Integration

## Purpose

This dashboard visualises feedback-adjusted IDS detection records from the pipeline.

It is the formal React dashboard layer for the Human-in-the-Loop IDS project.

The layout was upgraded using the uploaded SOC-style HTML prototype as a visual reference. The implementation remains React + Vite + TypeScript; the uploaded HTML was used as layout inspiration, not as runtime code.

## Data Source

The dashboard reads static JSON copies from:

```txt
dashboard/src/data/feedback-adjusted-alerts.sample.json
dashboard/src/data/feedback-evaluation-summary.json
dashboard/src/data/fusion-evaluation-summary.json
```

These files were copied from:

```txt
stage-5/outputs/feedback-adjusted-alerts.sample.json
stage-5/evaluation/feedback-evaluation-summary.json
stage-4/evaluation/fusion-evaluation-summary.json
```

The original pipeline outputs are not moved. If the pipeline outputs change later, refresh the dashboard copies from the source files.

The JSON filenames may contain the word "alerts" for historical reasons, but the dashboard treats these records as detection records unless they satisfy the active alert criteria.

## How to Run

From this folder:

```powershell
npm install
npm run dev
```

For a production build:

```powershell
npm run build
```

## GitHub Pages Deployment

The public dashboard URL is:

```txt
https://lck0629.github.io/ids-dashboard/
```

GitHub Pages deployment is rebuilt automatically from `main` using the dashboard GitHub Actions workflow. The workflow installs dependencies from `dashboard/package-lock.json`, builds the Vite app from this folder, and deploys `dashboard/dist`.

Local development still uses:

```powershell
npm run dev
```

This deployed site is a static/offline prototype. It does not imply a backend, database, authentication, live packet capture, or production IDS monitoring.

## Dashboard Features

- KPI cards for pipeline feedback and review impact.
- Filter bar for review-required, adjusted, high-risk, score guardrail, exception trust-gate, benign, malicious, and attack type views.
- Active Alert Queue sorted by feedback-adjusted `currentRiskScore`.
- All Detection Records and Suppressed / Resolved filters for retained low-risk or resolved records.
- Latest Activity replay feed showing newly replayed detection records in arrival order, separate from the risk-sorted active alert queue.
- Alert detail panel showing signature evidence, ML prediction, fusion evidence, and feedback adjustment.
- Score comparison between `fusionRiskScore` and feedback-adjusted `currentRiskScore`.
- Sidebar navigation for Operations, Investigations, Feedback Model, and Reports views.

## View Structure

The Operations view contains the main operational metrics, queue, and triage workspace. Investigation, Feedback Model, and Reports views do not repeat the full metric dashboard. Instead, each view presents content specific to its purpose.

## What This Dashboard Shows

- Fusion score.
- Current feedback-adjusted score.
- Feedback adjustment.
- Signature evidence.
- ML prediction.
- Fusion decision and evidence.
- Analyst review flag.
- Guardrail and feedback reason.
- Model confidence is displayed as an XGBoost confidence score. It is not a calibrated probability and should not be interpreted as absolute certainty. Values very close to 1.0 are displayed as 99.9%+ to avoid implying guaranteed correctness.

## Flow Records, Detection Records, and Actionable Alerts

The dashboard separates the full processed dataset from the active alert queue.

A flow record is a network traffic record from the dataset. Each flow is processed by the signature, ML, fusion, and feedback stages to produce a detection record. However, not every detection record is an active alert.

The Active Alert Queue only shows records promoted for analyst attention based on risk score, signature evidence, fusion decision, or review requirement. Low-risk, benign, suppressed, and resolved records remain available through the All Detection Records and Suppressed / Resolved filters.

The sidebar displays separate counts for processed flows, detection records, active alerts, review-required alerts, high-risk records, and suppressed/resolved records.

The JSON filenames may contain the word "alerts" for historical reasons, but the dashboard treats them as detection records unless they satisfy active alert criteria.

## Ground Truth and Evaluation Fields

Ground truth is joined only after detection, fusion, and feedback. It is used for evaluation, reporting, and dashboard explanation, not for prediction or scoring. Benign and Malicious filters use only ground-truth fields and do not fall back to model or fusion predictions.

## Guardrail and Trust-Gate Semantics

The dashboard separates score guardrails from exception trust-gate rejections. Score guardrails limit unsafe risk-score reduction, while trust-gate rejections indicate that exception memory was ignored because it was not reliable enough.

## Simulated Replay and Interactive Feedback

The dashboard includes an offline replay mode and UI-only analyst feedback controls. Detection records are replayed from the static pipeline JSON output to simulate an operational triage queue. Analyst feedback changes the dashboard's local state and recalculates risk scores for demonstration purposes only.

This does not write back to the pipeline JSON files, does not retrain the model, and does not perform live packet capture.

The Latest Activity panel is driven by replay progress. It starts empty before replay, then grows as detection records are replayed so the demo can show incoming activity separately from the main risk-prioritised queue.

Replay controls:

- Start, pause, resume, and reset replay.
- Replay speed options: 1x, 2x, and 5x.
- Show all records.
- Replay mode can be toggled on or off.

Feedback controls:

- Confirm Threat.
- Mark False Positive.
- Expected Activity.
- Needs Investigation.
- Escalate.
- Reset Feedback.

Local-only score adjustment uses front-end guardrails. Scores stay between 0 and 100, Critical records are not reduced below 70, Infiltration records are not reduced below 75, and signature/ML disagreement remains review-required.

Reset Replay clears local feedback overrides for the current browser session. No feedback is persisted.

## Human Feedback Impact

The dashboard demonstrates human-in-the-loop triage through local analyst feedback controls. Analyst actions can confirm threats, mark false positives, identify expected activity, request further investigation, or escalate records.

These actions update the dashboard's local current risk score, review status, queue ranking, and session metrics. The original pipeline JSON outputs are not modified. This allows the prototype to demonstrate adaptive triage behaviour without backend persistence.

The Investigation view also supports analyst feedback decisions. This allows an analyst to review feature-level evidence and immediately apply a decision such as Confirm Threat, Mark False Positive, Expected Activity, Needs Investigation, or Escalate. Feedback submitted from Investigations uses the same local state as the Operations view, so risk score, review status, queue ranking, and session metrics update consistently across the dashboard.

Guardrails prevent unsafe suppression of critical, Infiltration, or conflicting-evidence records. When a guardrail applies, the detail panel and queue show the guardrail result so the analyst can see why priority or review status was preserved.

The pipeline provides offline simulated feedback and exception memory. The dashboard provides interactive UI-only analyst feedback for demonstration.

## Signature Evidence Explanations

The dashboard separates signature evidence into plain-language explanations and technical rule details. Plain explanations help analysts understand why a rule matched, while technical details preserve auditability by listing the matched flow conditions.

Signature explanations use cautious wording such as "may indicate" and "prototype heuristic" because flow-level signatures suggest suspicious behaviour but do not prove an attack by themselves.

## Investigation View

The Investigation view provides feature-level context for the selected detection record. It groups key flow features into traffic identity, volume, rate, timing, packet-size, and TCP-flag categories. It also explains the signature result, ML prediction, fusion decision, feedback impact, and analyst recommendation.

The view uses flow-level statistical features only. It does not inspect packet payloads and does not provide SHAP-level model attribution.

## What Is Not Included Yet

- No live backend.
- No database.
- No real analyst write-back.
- No authentication.
- No live traffic.
- No model retraining.
- No live replay from network traffic.
- No backend persistence for dashboard feedback.

## Limitations

- Static JSON dashboard.
- Simulated feedback.
- Prototype evaluation.
- Layout inspired by a static SOC HTML prototype, but data still comes from static pipeline JSON outputs.
- Not production IDS.
