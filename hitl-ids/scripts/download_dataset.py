"""
Acquire the corrected CIC-IDS datasets.

Why a *corrected* dataset:
    Engelen, Rimmer & Joosen (WTMC 2021) and Engelen et al. (IEEE CNS 2022, Best Paper)
    documented labelling errors, packet duplication, and a CICFlowMeter flow-termination bug
    across CIC-IDS-2017 and CSE-CIC-IDS-2018. The authors published corrected releases.
        https://intrusion-detection.distrinet-research.be/WTMC2021/index.html
        https://intrusion-detection.distrinet-research.be/CNS2022/index.html
        https://github.com/GintsEngelen/CICFlowMeter   (fixed flow exporter)

    Using the corrected data is a methodological contribution in its own right and pre-empts the
    obvious challenge to dataset validity.

Usage
-----
    python download_dataset.py                 # download to ../data/raw/
    python download_dataset.py --check         # report auth + target state only

Authentication
--------------
Kaggle requires credentials. Either:
    kaggle auth login                          # OAuth, recommended
or generate a token at https://www.kaggle.com/settings/api and set:
    KAGGLE_API_TOKEN=...                       # or save it to ~/.kaggle/access_token

This script never prompts for, prints, or stores credentials.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DATASET = "ernie55ernie/improved-cicids2017-and-csecicids2018"
HERE = Path(__file__).resolve().parent
DEST = HERE.parent / "data" / "raw"


def auth_state() -> "tuple[bool, str]":
    """Return (authenticated, human-readable reason). Never reads credential contents."""
    if os.environ.get("KAGGLE_API_TOKEN"):
        return True, "KAGGLE_API_TOKEN environment variable"
    for p in (Path.home() / ".kaggle" / "kaggle.json",
              Path.home() / ".kaggle" / "access_token"):
        if p.exists():
            return True, f"credentials file {p}"
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return True, "KAGGLE_USERNAME/KAGGLE_KEY environment variables"
    return False, "no Kaggle credentials found"


def report_target() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in DEST.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"target directory : {DEST}")
    print(f"files present    : {len(files)} ({total / 1e6:.1f} MB)")
    for p in files[:20]:
        print(f"    {p.relative_to(DEST)}  {p.stat().st_size / 1e6:.1f} MB")
    if len(files) > 20:
        print(f"    ... and {len(files) - 20} more")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report state and exit")
    args = ap.parse_args()

    ok, reason = auth_state()
    print(f"kaggle auth      : {'OK - ' + reason if ok else 'MISSING - ' + reason}")
    report_target()

    if args.check:
        return 0

    if not ok:
        print(
            "\nCannot download: Kaggle credentials are required.\n"
            "  Run  kaggle auth login  once in your terminal, then re-run this script.\n"
            "  Alternatively create a token at https://www.kaggle.com/settings/api\n"
            "  and save it to ~/.kaggle/access_token\n",
            file=sys.stderr,
        )
        return 2

    try:
        import kagglehub
    except ImportError:
        print("kagglehub not installed:  pip install kagglehub", file=sys.stderr)
        return 3

    print(f"\ndownloading {DATASET} ...")
    path = kagglehub.dataset_download(DATASET)
    print(f"kagglehub cache  : {path}")

    # Mirror into the project tree so the data lives beside the code that consumes it.
    import shutil
    src = Path(path)
    copied = 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        target = DEST / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(f, target)
            copied += 1
    print(f"copied {copied} new file(s) into {DEST}")
    report_target()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
