"""
Run the ranking selection experiment and keep its record (decision Q26).

Every run is kept - nothing is overwritten - so the history of these tests can be read like the
notebooks:

    evaluation/ranking/runs/<run id>/config.json    settings, data sizes, severity-chart version, commit
    evaluation/ranking/runs/<run id>/results.json   control, every arm x seed, means, selection
    evaluation/ranking/runs/<run id>/METHOD.md      how this run was performed
    evaluation/ranking/history.jsonl                one line per run: id, commit, winner, headline

Method: docs/ranking-and-escalation-design.md §6. Needs data/processed/demo_sample.csv and
demo_ml_predictions_shap.json (see data/README.md).
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts.db import format_timestamp  # noqa: E402
from packages.detection.ranking.experiment import run_experiment  # noqa: E402
from packages.detection.ranking.severity import DEFAULT_CHART, load_severity_chart  # noqa: E402

OUT = HITL / "evaluation" / "ranking"

METHOD = """# Ranking selection experiment — method

Design: `docs/ranking-and-escalation-design.md` §6. Code: `packages/detection/ranking/`.

1. **Data.** All 5,000 demo flows, fused by the production engine (S5 rules + S6 fusion), ordered by
   timestamp. First half = calibration (the past); second half = future (never shown to the analyst).
2. **Families.** Predicted class + destination port + protocol + matched rule; unflagged flows add
   the destination IP. A verdict updates its family; future members inherit the family's state.
3. **Simulated Tier 1 analyst.** {rounds} rounds; each round reviews the top {batch} unreviewed
   calibration alerts plus {qa_sample} randomly sampled unflagged ones (QA sampling). Verdict =
   ground truth, flipped with probability 0 %, 5 % or 15 % (analyst error).
4. **Arms.** Formulas C0-C3 x movement M1/M2 x guardrails on/off x error rate x {n_seeds} seeds.
   Guardrails off removes the caps, floors, I3 and tier-loss protection; the 0-100 range remains.
5. **Metrics, future half only**: precision in the top 50/100/200; mean attack position (0-1, lower
   is better); last attack position; benign alerts in the top 100; Critical floor violations;
   true attacks demoted; Tier 2 load and precision; class changes during calibration.
6. **Selection ({selection_rule}).** Among guarded arms: safety first (no floor violation at any
   error rate; no attack demoted at 0 % error); then fewest true attacks demoted under analyst error
   (5 % + 15 %); then highest Tier 2 precision at 5 %; then lowest mean attack position at 5 %; then
   fewest class changes; then the simpler formula and movement.
   *sel-1* (run 20260911T111249Z) ranked on precision in the top 100 first; the control already
   scores 1.0 there, so it could not discriminate. sel-2 was written after seeing that run.
"""


def commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(HITL), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    chart = load_severity_chart(DEFAULT_CHART)
    started = datetime.now(UTC)
    result = run_experiment(HITL / "data" / "processed", chart)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    folder = OUT / "runs" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    config = {**result["config"], "run_id": run_id, "started": format_timestamp(started),
              "commit": commit(), "severity_chart_file": DEFAULT_CHART.relative_to(HITL).as_posix(),
              # the flow order depends on timestamp parsing, which has differed between versions
              "environment": {"python": platform.python_version(), "pandas": pd.__version__,
                              "numpy": np.__version__}}
    (folder / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (folder / "results.json").write_text(json.dumps(
        {key: result[key] for key in ("control", "runs", "aggregates", "selection")}, indent=2)
        + "\n", encoding="utf-8")
    (folder / "METHOD.md").write_text(METHOD.format(
        rounds=config["rounds"], batch=config["batch"], qa_sample=config["qa_sample"],
        n_seeds=len(config["seeds"]), selection_rule=config["selection_rule"]), encoding="utf-8")
    winner = result["selection"][0]
    with open(OUT / "history.jsonl", "a", encoding="utf-8") as history:
        history.write(json.dumps({"run_id": run_id, "commit": config["commit"],
                                  "severity_chart": chart.version,
                                  "selection_rule": config["selection_rule"], "winner": winner,
                                  "control": result["control"]}) + "\n")
    control = result["control"]
    print(f"run {run_id} ({config['selection_rule']}): control mean attack position "
          f"{control['mean_attack_position']}, Tier 2 load {control['tier2_load']}")
    for row in result["selection"]:
        print(f"  {row['formula']}+{row['movement']}  safe={row['safe']}  "
              f"demoted={row['attacks_demoted_under_error']}  "
              f"tier2_precision={row['tier2_precision']}  tier2_load={row['tier2_load']}  "
              f"mean_pos={row['mean_attack_position']}  class_changes={row['class_changes']}")
    print(f"wrote {folder.relative_to(HITL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
