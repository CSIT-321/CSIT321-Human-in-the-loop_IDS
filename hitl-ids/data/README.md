# Data

What is in this folder, what is deliberately not, and how to reproduce every file.

## Raw dataset — not in git

| | |
|---|---|
| File | `raw/CSECICIDS2018_improved.zip` |
| Size | 10,426,851,729 bytes (10.4 GB · 36 GB uncompressed · 10 capture days · 63,195,145 flows) |
| SHA-256 | `7f7b6f8065a88527bcb6e1579f088e1d0480a49903c5fd7e4e907ab238344f6e` |
| Release | The **corrected** CSE-CIC-IDS2018 (Engelen et al., IEEE CNS 2022) |
| Source | https://intrusion-detection.distrinet-research.be/CNS2022/Datasets/CSECICIDS2018_improved.zip |

It cannot be committed: GitHub rejects files over 100 MB and Git LFS caps files at 2 GB.
Download it into `raw/`, then check the hash:

```
Get-FileHash raw\CSECICIDS2018_improved.zip -Algorithm SHA256    # PowerShell
sha256sum raw/CSECICIDS2018_improved.zip                          # bash
```

`../scripts/download_dataset.py` targets a Kaggle mirror and needs Kaggle credentials; the direct
URL above is the file this project used.

## Working samples

Built by `../scripts/build_samples.py`, which streams the zip (the 36 GB is never written to
disk) with the fixed seed `20260911`. The two samples are disjoint, and the script asserts it.

| File | Rows | In git | SHA-256 |
|---|---:|---|---|
| `processed/demo_sample.csv` | 5,000 | **Yes** (force-added, 2.9 MB) | `d37ed3678a5163a4700def73313baea6908714637e9d486dd56a6c4dfe8b3c24` |
| `processed/train_sample.csv` | 250,655 | No — 136 MB exceeds GitHub's limit | `703c54be2b81bdbc41011c8387024ff2c924442e2bdbde27fe865de738509a83` |

Demo composition: Benign 4,000 · DoS 200 · DDoS 200 · Brute Force 200 · Botnet 150 · Port Scan 150
· Web Attack 60 · Infiltration 40 (174 flows are attempted, not successful, attacks). The training
sample caps each class; see `processed/sample_manifest.json` for both.

Columns: `alert_id`, `attack_class`, `is_attempted`, then the corrected release's own columns.
**`attack_class`, `is_attempted`, `Label` and `Attempted Category` are ground truth — for
evaluation only. They must never reach a detector.**

## Derived files

| File | In git | Produced by |
|---|---|---|
| `processed/label_scan.json` | yes | `scan_labels.py` — label census of all 63M flows |
| `processed/sample_manifest.json` | yes | `build_samples.py` |
| `processed/demo_detection_input.csv` | no | `build_demo_detection.py` — the observable fields detectors see |
| `processed/demo_ground_truth.json`, `demo_ml_predictions.json`, `corrected_findings.json` | yes | `build_demo_detection.py` |
| `processed/retune_results.json` | yes | `retune_rules.py` — the S4b threshold search |
| `processed/demo_ml_input.csv` | no | `run_ml_inference.py` |
| `processed/demo_ml_predictions_shap.json` | no (16 MB, regenerable) | `run_ml_inference.py` |
| `processed/ml-explainability-summary.json` | yes | `run_ml_inference.py` |

Order from a fresh clone: download the zip → `scan_labels.py` → `build_samples.py` →
`build_demo_detection.py` → `run_ml_inference.py`. `train_model.py` rebuilds the model from
`train_sample.csv`; the committed model in `../models/` is the one every reported figure used.
