# Environment Setup

This project is currently lightweight, but it uses both Node.js and Python in different stages.

## Environment Overview

| Environment | Used For |
|---|---|
| Node.js | Stage 2 signature engine scripts and future dashboard integration. |
| Python | Stage 1 preprocessing and future Stage 3 ML experiments. |

## Node.js

Recommended version:

```txt
Node.js 20 or later
```

Check whether Node.js is available:

```powershell
node -v
npm -v
```

Run the Stage 2 demo:

```powershell
node stage-2/scripts/run-signature-demo.js
```

Stage 2 currently uses Node.js built-in modules only. No `npm install` is required yet.

## Portable Node.js Option

To avoid installing Node.js system-wide, use the Windows binary zip from the Node.js download page.

Suggested approach:

```txt
1. Download the Windows Binary (.zip) LTS version.
2. Extract it to a local tools folder.
3. Run node.exe directly from that folder.
```

Example:

```powershell
& "C:\Users\cheek\tools\node-v22.x.x-win-x64\node.exe" stage-2\scripts\run-signature-demo.js
```

This avoids modifying the system PATH. Removing the extracted folder removes the portable Node.js runtime.

## Codex Bundled Node.js

Inside Codex, the bundled Node.js runtime can be used without installing Node.js separately:

```powershell
& "C:\Users\cheek\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" stage-2\scripts\run-signature-demo.js
```

This is useful for Codex-assisted runs, but a local Node.js runtime is recommended for normal project development.

## Python

Recommended version:

```txt
Python 3.10 or later
```

Python is used for:

- Stage 1 preprocessing.
- Jupyter / Colab notebooks.
- Future Stage 3 XGBoost ML detection.
- Future evaluation scripts.

Future Python dependencies are expected to include:

```txt
pandas
numpy
scikit-learn
xgboost
matplotlib
jupyter
```

These dependencies will be formalized later in:

```txt
requirements.txt
```

Stage 3 local inference uses a smaller pinned dependency set:

```txt
stage-3/requirements.txt
```

The current committed XGBoost model artifact was saved with XGBoost `3.3.0`, so local inference should use the matching `xgboost==3.3.0` runtime.

## Current Status

- Node.js is needed to run the Stage 2 signature demo.
- Python is needed for preprocessing notebooks and future ML work.
- No backend or database setup is required yet.
- No `node_modules/` or Python virtual environment is committed to the repository.
