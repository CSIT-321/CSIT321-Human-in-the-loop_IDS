"""Run reproducible local Stage 3 XGBoost inference.

This script loads committed model artifacts and feature-only flow records,
validates the exact 78-feature schema, writes prediction evidence, and can
compare regenerated predictions with the committed Stage 3 sample output.

It does not read ground truth and it does not train or overwrite the model.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "stage-3" / "core"))

from ml_inference import (  # noqa: E402
    DEFAULT_FEATURE_INPUT_PATH,
    TREESHAP_ADDITIVITY_TOLERANCE,
    TREESHAP_METHOD,
    TREESHAP_OUTPUT_SPACE,
    load_model_artifacts,
    predict_csv,
    sha256_file,
    write_predictions,
)

OUTPUT_DIR = REPO_ROOT / "stage-3" / "outputs"
EVALUATION_DIR = REPO_ROOT / "stage-3" / "evaluation"
DEFAULT_OUTPUT_PATH = OUTPUT_DIR / "ml-predictions.regenerated.json"
COMMITTED_OUTPUT_PATH = OUTPUT_DIR / "ml-predictions.sample.json"
SUMMARY_OUTPUT_PATH = EVALUATION_DIR / "ml-inference-reproducibility-summary.json"
EXPLAINABILITY_SUMMARY_OUTPUT_PATH = EVALUATION_DIR / "ml-explainability-summary.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def index_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record.get("id")): record for record in records}


def repo_relative_path(path: Path) -> str:
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def compare_predictions(regenerated: list[dict[str, Any]], committed_path: Path = COMMITTED_OUTPUT_PATH) -> dict[str, Any] | None:
    if not committed_path.exists():
        return None

    committed = load_json(committed_path)
    regenerated_by_id = index_by_id(regenerated)
    committed_by_id = index_by_id(committed)
    shared_ids = sorted(set(regenerated_by_id) & set(committed_by_id))
    agreement_count = 0
    confidence_differences: list[float] = []
    mismatch_examples: list[dict[str, Any]] = []

    for alert_id in shared_ids:
        new_record = regenerated_by_id[alert_id]
        old_record = committed_by_id[alert_id]
        if new_record.get("predictionStatus") != "available":
            continue
        if new_record.get("predictedAttackType") == old_record.get("predictedAttackType"):
            agreement_count += 1
        elif len(mismatch_examples) < 10:
            mismatch_examples.append({
                "id": alert_id,
                "committedPredictedAttackType": old_record.get("predictedAttackType"),
                "regeneratedPredictedAttackType": new_record.get("predictedAttackType"),
                "committedConfidence": old_record.get("modelConfidence"),
                "regeneratedConfidence": new_record.get("modelConfidence"),
            })

        old_confidence = old_record.get("modelConfidence")
        new_confidence = new_record.get("modelConfidence")
        if old_confidence is not None and new_confidence is not None:
            confidence_differences.append(abs(float(new_confidence) - float(old_confidence)))

    unavailable_count = sum(1 for record in regenerated if record.get("predictionStatus") != "available")
    confidence_stats = {
        "count": len(confidence_differences),
        "max": max(confidence_differences) if confidence_differences else None,
        "mean": statistics.fmean(confidence_differences) if confidence_differences else None,
        "median": statistics.median(confidence_differences) if confidence_differences else None,
    }

    return {
        "regeneratedRows": len(regenerated),
        "committedRows": len(committed),
        "sharedRows": len(shared_ids),
        "availableRows": sum(1 for record in regenerated if record.get("predictionStatus") == "available"),
        "unavailableRows": unavailable_count,
        "predictedClassAgreementCount": agreement_count,
        "predictedClassAgreementRate": round(agreement_count / len(shared_ids), 6) if shared_ids else 0,
        "confidenceDifferenceStats": confidence_stats,
        "mismatchExamples": mismatch_examples,
    }


def summarize_explainability(
    predictions: list[dict[str, Any]],
    artifacts: Any,
    input_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    available_predictions = [record for record in predictions if record.get("predictionStatus") == "available"]
    unavailable_predictions = [record for record in predictions if record.get("predictionStatus") != "available"]
    available_explanations = [
        record for record in predictions if record.get("mlExplanation", {}).get("status") == "available"
    ]
    unavailable_explanations = [
        record for record in predictions if record.get("mlExplanation", {}).get("status") != "available"
    ]

    additivity_differences: list[float] = []
    additivity_passed_count = 0
    additivity_failed_count = 0
    unavailable_reason_counts = {
        "predictionUnavailable": 0,
        "treeShapGenerationFailure": 0,
        "additivityFailure": 0,
        "other": 0,
    }
    per_class: dict[str, dict[str, int]] = {
        label: {
            "predictions": 0,
            "explanationsAvailable": 0,
            "explanationsUnavailable": 0,
            "additivityPassed": 0,
            "additivityFailed": 0,
        }
        for label in artifacts.label_mapping.values()
    }

    for record in available_predictions:
        predicted_class = str(record.get("predictedAttackType"))
        per_class.setdefault(
            predicted_class,
            {
                "predictions": 0,
                "explanationsAvailable": 0,
                "explanationsUnavailable": 0,
                "additivityPassed": 0,
                "additivityFailed": 0,
            },
        )
        per_class[predicted_class]["predictions"] += 1
        explanation = record.get("mlExplanation", {})
        if explanation.get("status") == "available":
            per_class[predicted_class]["explanationsAvailable"] += 1
            additivity_check = explanation.get("additivityCheck", {})
            difference = additivity_check.get("difference")
            if difference is not None:
                additivity_differences.append(float(difference))
            if additivity_check.get("passed") is True:
                additivity_passed_count += 1
                per_class[predicted_class]["additivityPassed"] += 1
            else:
                additivity_failed_count += 1
                per_class[predicted_class]["additivityFailed"] += 1
        else:
            per_class[predicted_class]["explanationsUnavailable"] += 1
            additivity_check = explanation.get("additivityCheck", {})
            difference = additivity_check.get("difference")
            if difference is not None:
                additivity_differences.append(float(difference))
            if additivity_check.get("passed") is False:
                additivity_failed_count += 1
                per_class[predicted_class]["additivityFailed"] += 1

    for record in unavailable_explanations:
        explanation = record.get("mlExplanation", {})
        reason = str(explanation.get("reason", ""))
        if reason == "prediction_unavailable":
            unavailable_reason_counts["predictionUnavailable"] += 1
        elif reason.startswith("treeshap_generation_failed"):
            unavailable_reason_counts["treeShapGenerationFailure"] += 1
        elif reason == "additivity_check_failed":
            unavailable_reason_counts["additivityFailure"] += 1
        else:
            unavailable_reason_counts["other"] += 1

    return {
        "method": TREESHAP_METHOD,
        "outputSpace": TREESHAP_OUTPUT_SPACE,
        "inputPath": repo_relative_path(input_path) if input_path is not None else None,
        "outputPath": repo_relative_path(output_path) if output_path is not None else None,
        "inputCount": len(predictions),
        "availablePredictionCount": len(available_predictions),
        "unavailablePredictionCount": len(unavailable_predictions),
        "availableExplanationCount": len(available_explanations),
        "unavailableExplanationCount": len(unavailable_explanations),
        "unavailableExplanationReasons": unavailable_reason_counts,
        "validTreeShapExplanationCount": len(available_explanations),
        "treeShapGenerationFailureCount": unavailable_reason_counts["treeShapGenerationFailure"],
        "additivityPassedCount": additivity_passed_count,
        "additivityFailedCount": additivity_failed_count,
        "additivityTolerance": TREESHAP_ADDITIVITY_TOLERANCE,
        "maxAdditivityDifference": max(additivity_differences) if additivity_differences else None,
        "meanAdditivityDifference": statistics.fmean(additivity_differences) if additivity_differences else None,
        "predictedClassesRepresented": sorted(
            class_name for class_name, coverage in per_class.items() if coverage["predictions"] > 0
        ),
        "perPredictedClassExplanationCoverage": per_class,
        "modelSha256": artifacts.provenance["modelSha256"],
        "featureSchemaSha256": artifacts.provenance["featureSchemaSha256"],
        "xgboostVersion": artifacts.provenance["xgboostVersion"],
        "notes": [
            "TreeSHAP explains the predicted class raw margin, not probability change.",
            "TreeSHAP values are explanation-only and are not Detection Score, Operational Priority, or Fusion input.",
            "The current ML model remains a six-class prototype and does not predict Infiltration.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 3 local XGBoost inference.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_FEATURE_INPUT_PATH,
        help="Feature-only CSV input. Defaults to stage-1/data/processed/flow-feature-full.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Prediction JSON output. Defaults to stage-3/outputs/ml-predictions.regenerated.json.",
    )
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=COMMITTED_OUTPUT_PATH,
        help="Optional committed prediction output to compare against.",
    )
    parser.add_argument(
        "--overwrite-sample",
        action="store_true",
        help="Blocked until Stage 4 explicitly supports unavailable ML prediction records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.overwrite_sample:
        raise SystemExit(
            "--overwrite-sample is blocked for this increment. Stage 4 does not yet "
            "understand predictionStatus=unavailable, so the committed Stage 4 input "
            "must not be replaced silently."
        )

    output_path = args.output
    artifacts = load_model_artifacts()
    predictions = predict_csv(args.input, artifacts)
    write_predictions(predictions, output_path)
    comparison = compare_predictions(predictions, args.compare_with)

    available_count = sum(1 for record in predictions if record.get("predictionStatus") == "available")
    unavailable_count = len(predictions) - available_count
    summary = {
        "inputPath": repo_relative_path(args.input),
        "outputPath": repo_relative_path(output_path),
        "referencePredictionPath": repo_relative_path(args.compare_with),
        "inputRowCount": len(predictions),
        "availablePredictionCount": available_count,
        "unavailablePredictionCount": unavailable_count,
        "comparison": comparison,
        "modelSha256": artifacts.provenance["modelSha256"],
        "featureSchemaSha256": artifacts.provenance["featureSchemaSha256"],
        "preprocessingConfigSha256": artifacts.provenance["preprocessingConfigSha256"],
        "labelMappingSha256": artifacts.provenance["labelMappingSha256"],
        "inputCsvSha256": sha256_file(args.input),
        "pythonVersion": sys.version.split()[0],
        "xgboostVersion": artifacts.provenance["xgboostVersion"],
        "modelArtifactVersion": artifacts.provenance["modelArtifactVersion"],
        "mlClasses": list(artifacts.label_mapping.values()),
        "infiltrationSupportedByMl": "Infiltration" in set(artifacts.label_mapping.values()),
        "notes": [
            "Prediction output is model evidence, not calibrated certainty or threat risk.",
            "The full regenerated prediction artifact is reproducible and should not be treated as the primary committed evidence.",
            "The committed Stage 3 sample should not be overwritten until Stage 4 supports predictionStatus=unavailable.",
        ],
    }
    SUMMARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUTPUT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    explainability_summary = summarize_explainability(predictions, artifacts, args.input, output_path)
    EXPLAINABILITY_SUMMARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPLAINABILITY_SUMMARY_OUTPUT_PATH.write_text(
        json.dumps(explainability_summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Input: {args.input}")
    print(f"Predictions written: {output_path}")
    print(f"Reproducibility summary written: {SUMMARY_OUTPUT_PATH}")
    print(f"Explainability summary written: {EXPLAINABILITY_SUMMARY_OUTPUT_PATH}")
    print(f"Total rows: {len(predictions)}")
    print(f"Available predictions: {available_count}")
    print(f"Unavailable predictions: {unavailable_count}")
    print(f"ML classes: {list(artifacts.label_mapping.values())}")
    print("Infiltration supported by ML:", "Infiltration" in set(artifacts.label_mapping.values()))
    print("Model provenance:")
    for key, value in artifacts.provenance.items():
        print(f"- {key}: {value}")

    if comparison is not None:
        print("Prediction comparison:")
        print(json.dumps(comparison, indent=2))
    else:
        print("Prediction comparison: committed output not found.")
    print("Explainability summary:")
    print(json.dumps(explainability_summary, indent=2))


if __name__ == "__main__":
    main()
