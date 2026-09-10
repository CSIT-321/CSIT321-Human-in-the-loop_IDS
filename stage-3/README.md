# Stage 3 XGBoost ML Detection

## Purpose

Stage 3 prepares an XGBoost-based machine-learning IDS classifier for the Hybrid Human-in-the-Loop IDS Dashboard.

The future model will classify CSE-CIC-IDS2018 flow records into dashboard attack types using observable flow-level features.

Stage 3A scaffold exists in this folder. Stage 3B training should be performed in Google Colab using `stage-3/notebooks/xgboost_ids_training.ipynb`.

## Stage 3 Role in the Hybrid IDS

Stage 3 provides the machine-learning detection signal.

Later Stage 4 will combine:

- Stage 2 signature evidence.
- Stage 3 ML prediction.
- Stage 5 human feedback and Exception Memory.

## Input Data

Training will use CSE-CIC-IDS2018 flow features and supervised labels.

For Colab training, use either:

- An uploaded `/content/archive.zip`.
- A Google Drive archive such as `/content/drive/MyDrive/cse-cic-ids2018/archive.zip`.
- KaggleHub download using `solarmainframe/ids-intrusion-csv`.

Raw CSE-CIC-IDS2018 CSV files and dataset archives should not be committed to GitHub.

For local demo prediction, the smaller documented feature-only input is:

```txt
stage-1/data/processed/flow-feature-sample.csv
```

For aligned Stage 4 fusion, the current Colab workflow also exports:

```txt
stage-1/data/processed/flow-feature-full.csv
```

`flow-feature-full.csv` keeps the fuller CSE-CIC-IDS2018 feature set for the same sampled `AL-XXXX` rows, so the trained XGBoost model can generate predictions that align with the Stage 2 signature output.

Ground truth for evaluation is:

```txt
stage-1/data/processed/ground-truth.json
```

## Training Principle

Training may use both observable flow features and labels because supervised learning requires labelled examples.

Training should not use dashboard-derived or answer-derived fields such as:

```txt
Label
rawLabel
attackType
mappedAttackType
groundTruth
severity
similarityKey
```

Training should use only observable numeric or encoded categorical flow features.

## Prediction Principle

Prediction must use feature-only records.

The prediction step must not read ground truth, raw labels, mapped attack types, severity, or similarity keys. Ground truth should be joined only after prediction for evaluation.

After Colab training, only model artifacts and small output/evaluation files should be copied back into the repository.

## Local Inference Reproducibility

The committed model can be used for local inference without retraining. Install the pinned Stage 3 inference dependencies in an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r stage-3\requirements.txt
```

Then regenerate prediction evidence from the committed artifacts:

```powershell
.\.venv\Scripts\python.exe stage-3\scripts\run_ml_prediction_demo.py
```

The script reads feature-only input from:

```txt
stage-1/data/processed/flow-feature-full.csv
```

and writes regenerated predictions to:

```txt
stage-3/outputs/ml-predictions.regenerated.json
```

The full regenerated prediction file is local derived evidence and is ignored by Git. The script also writes a small committed summary to:

```txt
stage-3/evaluation/ml-inference-reproducibility-summary.json
```

The committed `ml-predictions.sample.json` must not be overwritten in this increment. Stage 4 does not yet explicitly handle `predictionStatus = unavailable`, so replacing the Stage 4 input before that migration could accidentally change downstream behaviour.

Inference enforces the saved 78-feature schema from `feature-columns.json`, preserves feature order, detects missing or duplicate columns, coerces numeric values deterministically, and reports invalid rows as `predictionStatus = unavailable` instead of silently dropping them.

Formal inference also requires stable alert IDs. Missing `id` columns, blank row IDs, NaN row IDs, and duplicate alert IDs are reported as unavailable records. Synthetic row IDs are not generated unless a legacy compatibility option is explicitly enabled in code.

Stage 3 prediction output is model evidence, not threat risk. XGBoost probabilities are raw `multi:softprob` outputs and should not be treated as calibrated certainty.

For backward compatibility with the current Stage 4 fusion input contract, regenerated records still include `baseRiskScore`, but it is marked with:

```txt
baseRiskScoreStatus = legacy_confidence_compatibility_not_threat_risk
```

Stage 4 should later migrate to deriving risk from prediction evidence rather than treating Stage 3 confidence as threat risk, especially for high-confidence Benign predictions.

Each regenerated prediction also includes deterministic model provenance:

```txt
xgboostVersion
modelArtifactVersion
modelSha256
featureSchemaSha256
preprocessingConfigSha256
labelMappingSha256
```

## ML Explainability

Stage 3 now generates XGBoost native TreeSHAP explanation evidence during local inference. This uses the committed `xgboost_ids_model.json` Booster with native `pred_contribs=True`; the separate Python `shap` package is not required for this increment.

TreeSHAP is generated only after a row has passed feature validation and received a valid model prediction. Invalid rows keep `predictionStatus = unavailable` and receive an unavailable explanation with `reason = prediction_unavailable`.

For multiclass output, Stage 3 explains only the predicted class:

```txt
softprob argmax
-> predictedClassIndex
-> selected raw margin
-> selected TreeSHAP contribution vector
```

The explanation output space is `raw_margin`. SHAP contributions explain the raw XGBoost model margin for the predicted class. They are not probability changes, threat severity, Detection Score, Operational Priority, Fusion input, or HITL adaptation input.

Each available explanation includes:

```txt
method
outputSpace
explainedClass
explainedClassIndex
baseValue
rawModelMargin
topSupportingFeatures
topOpposingFeatures
additivityCheck
```

The full 78 feature contributions are used internally for additivity validation:

```txt
baseValue + sum(78 feature SHAP contributions) ~= predicted-class rawModelMargin
```

The display-oriented explanation keeps only the top supporting and opposing features, up to five each. Supporting features must have positive SHAP contributions, and opposing features must have negative SHAP contributions.

The compact explainability summary is written to:

```txt
stage-3/evaluation/ml-explainability-summary.json
```

Explanation coverage is reported across all input rows. Rows rejected before ML prediction are counted as unavailable explanations with `predictionUnavailable`, while valid predictions can separately report `treeShapGenerationFailure` or `additivityFailure`. An explanation is analyst-usable only when its TreeSHAP additivity check passes.

The full regenerated prediction output remains local/regenerable and should not be treated as the primary committed evidence.

## Expected Model Artifacts

Future training should write:

```txt
stage-3/models/xgboost_ids_model.json
stage-3/models/feature-columns.json
stage-3/models/label-mapping.json
stage-3/models/preprocessing-config.json
```

- `xgboost_ids_model.json`: trained XGBoost model.
- `feature-columns.json`: ordered feature list used during training and prediction.
- `label-mapping.json`: mapping between encoded model labels and dashboard attack types.
- `preprocessing-config.json`: preprocessing choices such as categorical encoding, scaling decisions, and forbidden fields.

## Expected ML Output Format

Future prediction output should be written to:

```txt
stage-3/outputs/ml-predictions.sample.json
```

This file should use the same `AL-XXXX` IDs as the Stage 1 / Stage 2 sample when it is intended for Stage 4 fusion. Notebook held-out test predictions should be kept separately, for example:

```txt
stage-3/outputs/held-out-test-predictions.json
```

Each prediction should eventually include:

```json
{
  "id": "AL-0001",
  "predictionStatus": "available",
  "predictedClassIndex": 4,
  "predictedAttackType": "DoS",
  "modelConfidence": 0.91,
  "classProbabilities": {
    "Benign": 0.01,
    "Botnet": 0.01,
    "Brute Force": 0.01,
    "DDoS": 0.03,
    "DoS": 0.91,
    "Web Attack": 0.03
  },
  "mlExplanation": {
    "status": "available",
    "method": "xgboost_native_treeshap_pred_contribs",
    "outputSpace": "raw_margin"
  }
}
```

`modelConfidence` is the classifier score for the selected class from XGBoost `multi:softprob`. It is not calibrated certainty and should not be used directly as threat risk.

## Evaluation Plan

Future evaluation should join predictions with `stage-1/data/processed/ground-truth.json` only after prediction.

Evaluation metrics should include:

- Accuracy.
- Precision.
- Recall.
- F1 score.
- Confusion matrix.
- Per-class performance.
- False positive count.
- False negative count.

Evaluation outputs should be stored under:

```txt
stage-3/evaluation/
```

## Infiltration Class Check

Stage 1 and Stage 2 contain `Infiltration` records, but the currently imported Stage 3 model artifacts do not include `Infiltration` in `stage-3/models/label-mapping.json`.

The Stage 3 notebook now checks this directly during training. It prints:

- Raw label distribution before and after cleaning.
- Unknown or unmapped labels.
- Mapped attack type distribution before sampling.
- Rows dropped during numeric cleanup, grouped by raw label where possible.
- Mapped attack type distribution after sampling.
- Final train/test class distribution.
- Final encoded label mapping before artifact export.

If an expected class such as `Infiltration` is missing, the notebook prints a warning. Common causes are restrictive `ROW_CAP_PER_CSV`, restrictive `MAX_CSV_FILES`, a selected source that does not include the relevant raw labels, or a spelling variant that needs to be mapped.

The current model should not be described as supporting `Infiltration` until it is retrained and verified with that class included.

## Current Model Limitation: Infiltration Class

Stage 1 and Stage 2 include `Infiltration`, but the current Stage 3 XGBoost model artifacts do not include `Infiltration` in `label-mapping.json`. This means the current ML model cannot predict `Infiltration`.

This is recorded in `preprocessing-config.json` under `missingExpectedAttackTypes`. The likely cause is the selected Stage 3 training source or row/file caps not including Infiltration rows during the current Colab training run.

This is a known limitation, not a silent model feature. Future retraining should include Infiltration by adjusting data loading, row caps, CSV selection, or targeted file inclusion.

> The current Stage 3 model should be interpreted as a six-class ML prototype. It supports Benign, Botnet, Brute Force, DDoS, DoS, and Web Attack, but it does not currently support Infiltration prediction. Infiltration remains covered only by the Stage 2 signature layer until the ML model is retrained with that class.

## What Is Not Included Yet

- No dashboard integration.
- No Fusion Engine.
- No human feedback adaptation.
- No production IDS deployment.
- No Snort or Suricata integration.
- No SHAP package dependency; explainability currently uses native XGBoost TreeSHAP only.

## How to Run Later

For Stage 3B training, open this notebook in Google Colab:

```txt
stage-3/notebooks/xgboost_ids_training.ipynb
```

The notebook supports `DATASET_SOURCE = 'kagglehub'`, `'upload_zip'`, `'drive_zip'`, or `'extracted_folder'`.

For free Colab RAM, start with the notebook's memory-safe defaults:

```python
ROW_CAP_PER_CSV = 20_000
MAX_ROWS_PER_CLASS = 2_000
```

If RAM still crashes, reduce `ROW_CAP_PER_CSV` to `5_000` or `10_000`, or set `MAX_CSV_FILES = 3` for a first test run.

The training script remains a scaffold for later local training reproducibility:

```powershell
python stage-3/scripts/train_xgboost_ids.py
```

The prediction script now performs local inference from committed artifacts:

```powershell
python stage-3/scripts/run_ml_prediction_demo.py
```

The Colab notebook exports artifacts that can later be copied into:

```txt
stage-3/models/
stage-3/outputs/
stage-3/evaluation/
```
