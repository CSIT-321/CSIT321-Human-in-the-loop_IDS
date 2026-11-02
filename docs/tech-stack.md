> Historical technology-planning record. Stage 6 dashboard/ has been retired; use ../README.md and ../hitl-ids/docs/preliminary-user-manual.md for the current runtime.

# Tech Stack Notes

## Frontend Options

- React
- Vue
- Next.js

Recommended choice: React or Next.js, because they are suitable for building interactive dashboards and reusable UI components.

## Backend Options

- Flask
- FastAPI
- Node.js / Express

Recommended choice: FastAPI, because it works well with Python-based data processing and can provide clean API endpoints for the dashboard.

## Database Options

- SQLite
- PostgreSQL

Recommended choice for prototype: SQLite. It is simple, local, and suitable for an FYP prototype.

Recommended choice for larger deployment: PostgreSQL.

## Visualization Libraries

- Chart.js
- Recharts
- D3.js

Recommended choice: Recharts or Chart.js for faster development.

## Dataset Options

- CSE-CIC-IDS2018
- CICIDS2017
- UNSW-NB15
- NSL-KDD
- Simulated IDS alert logs

Formal dataset decision: use CSE-CIC-IDS2018. It is newer than CICIDS2017, suitable for intrusion detection, and can be sampled and converted into dashboard-style IDS alerts.

Stage 1 will not build the full dataset pipeline yet. The planned data handling flow is:

```txt
CSE-CIC-IDS2018 raw CSV files
-> sample selected rows
-> export observable flow features for detection
-> export ground truth labels for evaluation
-> export dashboard-ready labelled alerts for UI/reference use
```

Stage 1 dataset-related files will be placed under:

```txt
stage-1/
|-- data/
|   |-- raw/
|   |   `-- cse-cic-ids2018/
|   `-- processed/
|       |-- flow-feature-sample.csv
|       |-- ground-truth.json
|       `-- sample-alerts.json
|-- schema/
|   |-- flow-feature-schema.md
|   `-- ground-truth-schema.md
`-- scripts/
    `-- sample_cse_cic_ids2018.py
```

The current mock alert data remains in use for dashboard UX testing, feedback button testing, adaptive scoring testing, and Investigations / Feedback Model / Reports view testing before full dataset integration.

Detection engines must use `stage-1/data/processed/flow-feature-sample.csv` and must not use `attackType` or `groundTruth` from `sample-alerts.json` as detection input. `sample-alerts.json` is retained as a dashboard-ready labelled sample, UI sample, and evaluation reference.

## Formal Technical Direction

- Python / Pandas for CSE-CIC-IDS2018 preprocessing.
- CSE-CIC-IDS2018 as the formal flow-level intrusion detection dataset.
- Flow-based signature rules for known attack pattern detection using `protocol`, `port`, and `flowFeatures`.
- XGBoost for supervised flow-based attack classification in Stage 3.
- Pandas and scikit-learn for ML preprocessing, train/test splitting, and evaluation metrics.
- Notebook / Google Colab workflow for training experiments on larger CSE-CIC-IDS2018 data.
- JSON artifacts for model metadata, feature columns, label mappings, preprocessing configuration, and later Fusion Engine integration.
- Node.js rule-based Fusion Engine for Stage 4.
- Fusion logic combines JSON outputs from Stage 2 signature detection and Stage 3 ML prediction.
- Fusion output is designed for later dashboard integration with fused attack type, risk score, decision, evidence, and analyst review flag.
- Node.js JSON-based feedback adaptation logic for Stage 5.
- Stage 5 feedback memory uses prototype JSON storage for simulated analyst feedback and exception patterns.
- Future dashboard integration can replace JSON samples with interactive analyst feedback.
- React, Vite, and TypeScript for the Stage 6 dashboard integration.
- Stage 6 reads static JSON outputs from Stage 4 and Stage 5.
- No backend API is required for the current dashboard prototype.
- Later work may replace static JSON imports with API and database integration.
- Exception Memory to store repeated analyst feedback patterns.
- Beta-Bernoulli feedback scoring to model repeated true-positive and false-positive feedback.
- HTML / CSS / JavaScript dashboard for the current frontend prototype.
- ML + workload + usability evaluation for final project assessment.

## Machine Learning Detection

Stage 3 will use XGBoost as the supervised ML detection layer. Training may use observable flow features with ground-truth labels, but prediction must use feature-only input from `stage-1/data/processed/flow-feature-sample.csv`.

Current XGBoost model artifacts are six-class prototype artifacts. `Infiltration` is excluded from the current ML class mapping and should be restored in a future retraining run.

The planned Stage 3 output is:

```txt
stage-3/outputs/ml-predictions.sample.json
```

The expected prediction fields are `id`, `predictedAttackType`, `modelConfidence`, and `baseRiskScore`. These ML outputs will later be combined with Stage 2 signature evidence in the Stage 4 Fusion Engine.

Stage 3 model artifacts are planned under:

```txt
stage-3/models/
|-- xgboost_ids_model.json
|-- feature-columns.json
|-- label-mapping.json
`-- preprocessing-config.json
```

Ground truth should be joined only after prediction for evaluation under `stage-3/evaluation/`.

## Environment Requirements

- Node.js 20 or later is recommended for Stage 2 signature scripts, Stage 4/5 JSON processing scripts, and the Stage 6 React dashboard.
- Python 3.10 or later is recommended for Stage 1 preprocessing and future Stage 3 ML experiments.
- Stage 2, Stage 4, and Stage 5 currently use Node.js built-in modules only. Stage 6 requires `npm install` inside `dashboard/` for React, Vite, and TypeScript.
- Detailed setup notes are documented in `docs/environment.md`.

Full Snort or Suricata packet inspection is not implemented in the current prototype because the project uses flow-level CSE-CIC-IDS2018 records, not raw packet payloads.

The Stage 2 signature engine should not use `attackType` or `groundTruth` as detection inputs. These fields come from dataset labels and are kept for evaluation, summary reporting, and dashboard explanation only.

## Staged Pipeline

```txt
Stage 1: CSE-CIC-IDS2018 dataset preprocessing
Stage 2: Flow-based signature detection
Stage 3: XGBoost ML Detection Engine
Stage 4: Fusion Engine
Stage 5: Human feedback and Exception Memory
Stage 6: React Dashboard Integration
Stage 7: Evaluation
```

## Adaptive Logic Options

- Rule-based scoring
- Simple machine learning model
- Hybrid rule-based and feedback-based scoring

Recommended initial approach: rule-based adaptive scoring. This is easier to explain, test, and demonstrate during FYP evaluation.

## Possible Architecture

Frontend dashboard sends user feedback to the backend API. The backend stores alert data and feedback in the database. The scoring logic recalculates alert priority based on feedback history. The frontend displays updated scores, charts, and summary reports.

## Personal Notes

- 中文备注：先做 rule-based，不要一开始就把 ML 做得太复杂。
- 重点是 dashboard + feedback loop + clear evaluation。
