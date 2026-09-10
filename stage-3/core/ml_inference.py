"""Reusable Stage 3 XGBoost inference utilities.

This module loads the committed Stage 3 model artifacts, validates feature-only
flow records against the saved 78-feature schema, and produces prediction
evidence. It does not read ground truth and it does not train or overwrite the
model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except ImportError as exc:  # pragma: no cover - exercised when deps are absent.
    xgb = None
    XGBOOST_IMPORT_ERROR = exc
else:
    XGBOOST_IMPORT_ERROR = None


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_1_PROCESSED_DIR = REPO_ROOT / "stage-1" / "data" / "processed"
DEFAULT_FEATURE_INPUT_PATH = STAGE_1_PROCESSED_DIR / "flow-feature-full.csv"
MODEL_DIR = REPO_ROOT / "stage-3" / "models"
DEFAULT_MODEL_PATH = MODEL_DIR / "xgboost_ids_model.json"
DEFAULT_FEATURE_COLUMNS_PATH = MODEL_DIR / "feature-columns.json"
DEFAULT_LABEL_MAPPING_PATH = MODEL_DIR / "label-mapping.json"
DEFAULT_PREPROCESSING_CONFIG_PATH = MODEL_DIR / "preprocessing-config.json"

FORBIDDEN_PREDICTION_FIELDS = {
    "Label",
    "rawLabel",
    "attackType",
    "mappedAttackType",
    "groundTruth",
    "severity",
    "similarityKey",
}
MAX_FLOAT32 = float(np.finfo(np.float32).max)
TREESHAP_METHOD = "xgboost_native_treeshap_pred_contribs"
TREESHAP_OUTPUT_SPACE = "raw_margin"
TREESHAP_ADDITIVITY_TOLERANCE = 1e-4
TREESHAP_DISPLAY_FEATURE_LIMIT = 5


class InferenceConfigurationError(RuntimeError):
    """Raised when committed model artifacts are inconsistent."""


@dataclass(frozen=True)
class ModelArtifacts:
    model: Any
    feature_columns: list[str]
    label_mapping: dict[int, str]
    preprocessing_config: dict[str, Any]
    provenance: dict[str, str]
    objective: str
    model_class_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def model_version_from_json(path: Path) -> str | None:
    model_json = load_json(path)
    version = model_json.get("version")
    if isinstance(version, list):
        return ".".join(str(part) for part in version)
    if version is None:
        return None
    return str(version)


def model_contract_from_json(path: Path) -> dict[str, Any]:
    model_json = load_json(path)
    learner = model_json.get("learner", {})
    objective = learner.get("objective", {})
    model_param = learner.get("learner_model_param", {})
    objective_name = objective.get("name")
    num_class = int(model_param.get("num_class", 0))
    return {
        "objective": objective_name,
        "numClass": num_class,
    }


def load_model_artifacts(
    model_path: Path = DEFAULT_MODEL_PATH,
    feature_columns_path: Path = DEFAULT_FEATURE_COLUMNS_PATH,
    label_mapping_path: Path = DEFAULT_LABEL_MAPPING_PATH,
    preprocessing_config_path: Path = DEFAULT_PREPROCESSING_CONFIG_PATH,
) -> ModelArtifacts:
    if xgb is None:
        raise InferenceConfigurationError(
            "xgboost is not installed. Install the pinned Stage 3 inference "
            "dependencies before running local ML inference."
        ) from XGBOOST_IMPORT_ERROR

    required_paths = [
        model_path,
        feature_columns_path,
        label_mapping_path,
        preprocessing_config_path,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Stage 3 model artifacts: {missing}")

    feature_columns = load_json(feature_columns_path)
    raw_label_mapping = load_json(label_mapping_path)
    preprocessing_config = load_json(preprocessing_config_path)

    if not isinstance(feature_columns, list) or not all(isinstance(item, str) for item in feature_columns):
        raise InferenceConfigurationError("feature-columns.json must contain a list of feature names.")
    if len(feature_columns) != 78:
        raise InferenceConfigurationError(f"Expected 78 feature columns, found {len(feature_columns)}.")
    if len(set(feature_columns)) != len(feature_columns):
        raise InferenceConfigurationError("feature-columns.json contains duplicate feature names.")

    label_mapping = {int(key): str(value) for key, value in raw_label_mapping.items()}
    expected_indexes = list(range(len(label_mapping)))
    if sorted(label_mapping) != expected_indexes:
        raise InferenceConfigurationError("label-mapping.json must use contiguous zero-based class indexes.")

    selected_features = preprocessing_config.get("selectedFeatures")
    if selected_features is not None and selected_features != feature_columns:
        raise InferenceConfigurationError(
            "preprocessing-config.json selectedFeatures must exactly match feature-columns.json."
        )

    contract = model_contract_from_json(model_path)
    if contract["objective"] != "multi:softprob":
        raise InferenceConfigurationError(
            f"Model objective must be multi:softprob, found {contract['objective']}."
        )
    if contract["numClass"] != len(label_mapping):
        raise InferenceConfigurationError(
            f"Model class count {contract['numClass']} does not match label mapping size {len(label_mapping)}."
        )

    model = xgb.Booster()
    model.load_model(str(model_path))

    model_feature_count = int(model.num_features())
    if model_feature_count != len(feature_columns):
        raise InferenceConfigurationError(
            f"Model expects {model_feature_count} features but feature schema has {len(feature_columns)}."
        )

    model_json_version = model_version_from_json(model_path)
    runtime_version = getattr(xgb, "__version__", "unknown")
    provenance = {
        "xgboostVersion": str(runtime_version),
        "modelArtifactVersion": model_json_version or "unknown",
        "modelSha256": sha256_file(model_path),
        "featureSchemaSha256": sha256_file(feature_columns_path),
        "preprocessingConfigSha256": sha256_file(preprocessing_config_path),
        "labelMappingSha256": sha256_file(label_mapping_path),
    }

    return ModelArtifacts(
        model=model,
        feature_columns=feature_columns,
        label_mapping=label_mapping,
        preprocessing_config=preprocessing_config,
        provenance=provenance,
        objective=contract["objective"],
        model_class_count=contract["numClass"],
    )


def duplicate_columns(columns: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for column in columns:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    return duplicates


def read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            return next(reader)
        except StopIteration:
            return []


def read_feature_csv(path: Path) -> tuple[pd.DataFrame, list[str]]:
    header = read_csv_header(path)
    duplicates = duplicate_columns(header)
    dataframe = pd.read_csv(path, low_memory=False)
    return dataframe, duplicates


def unavailable_record(
    alert_id: Any,
    failure_reason: str,
    missing_feature_columns: list[str] | None = None,
    invalid_feature_columns: list[str] | None = None,
    duplicate_feature_columns: list[str] | None = None,
    model_provenance: dict[str, str] | None = None,
    source_row_number: int | None = None,
) -> dict[str, Any]:
    return {
        "id": None if alert_id is None else str(alert_id),
        "sourceRowNumber": source_row_number,
        "predictionStatus": "unavailable",
        "failureReason": failure_reason,
        "missingFeatureColumns": missing_feature_columns or [],
        "invalidFeatureColumns": invalid_feature_columns or [],
        "duplicateFeatureColumns": duplicate_feature_columns or [],
        "predictedClassIndex": None,
        "predictedAttackType": None,
        "modelConfidence": None,
        "classProbabilities": None,
        "secondBestClass": None,
        "predictionMargin": None,
        "modelProvenance": model_provenance or {},
        "mlExplanation": unavailable_ml_explanation("prediction_unavailable"),
    }


def validate_dataframe_schema(dataframe: pd.DataFrame, feature_columns: list[str]) -> dict[str, list[str]]:
    input_columns = [str(column) for column in dataframe.columns]
    input_column_set = set(input_columns)
    return {
        "duplicateColumns": duplicate_columns(input_columns),
        "missingIdColumns": [] if "id" in input_column_set else ["id"],
        "missingFeatureColumns": [column for column in feature_columns if column not in input_column_set],
        "forbiddenColumns": [column for column in FORBIDDEN_PREDICTION_FIELDS if column in input_column_set],
    }


def row_id(row: pd.Series, fallback_index: int, allow_synthetic_ids: bool = False) -> str | None:
    value = row.get("id", None)
    if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == "":
        if allow_synthetic_ids:
            return f"ROW-{fallback_index + 1:04d}"
        return None
    if pd.isna(value):
        if allow_synthetic_ids:
            return f"ROW-{fallback_index + 1:04d}"
        return None
    return str(value).strip()


def unavailable_for_rows(
    dataframe: pd.DataFrame,
    failure_reason: str,
    artifacts: ModelArtifacts,
    missing_feature_columns: list[str] | None = None,
    invalid_feature_columns: list[str] | None = None,
    duplicate_feature_columns: list[str] | None = None,
    allow_synthetic_ids: bool = False,
) -> list[dict[str, Any]]:
    return [
        unavailable_record(
            row_id(row, index, allow_synthetic_ids),
            failure_reason,
            missing_feature_columns=missing_feature_columns,
            invalid_feature_columns=invalid_feature_columns,
            duplicate_feature_columns=duplicate_feature_columns,
            model_provenance=artifacts.provenance,
            source_row_number=index + 1,
        )
        for index, (_, row) in enumerate(dataframe.iterrows())
    ]


def duplicate_alert_ids(dataframe: pd.DataFrame) -> set[str]:
    if "id" not in dataframe.columns:
        return set()
    ids = dataframe["id"].apply(lambda value: None if pd.isna(value) else str(value).strip())
    valid_ids = ids[(ids.notna()) & (ids != "")]
    duplicate_mask = valid_ids.duplicated(keep=False)
    return set(valid_ids[duplicate_mask])


def validate_and_prepare_row(
    row: pd.Series,
    feature_columns: list[str],
) -> tuple[np.ndarray | None, list[str]]:
    values: list[float] = []
    invalid_columns: list[str] = []

    for column in feature_columns:
        value = row.get(column)
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(numeric):
            invalid_columns.append(column)
            continue
        numeric_float = float(numeric)
        if not np.isfinite(numeric_float):
            invalid_columns.append(column)
            continue
        if abs(numeric_float) > MAX_FLOAT32:
            invalid_columns.append(column)
            continue
        values.append(numeric_float)

    if invalid_columns:
        return None, invalid_columns

    return np.asarray(values, dtype=np.float32), []


def probability_record(
    alert_id: str,
    probabilities: np.ndarray,
    label_mapping: dict[int, str],
    provenance: dict[str, str],
) -> dict[str, Any]:
    probabilities = np.asarray(probabilities, dtype=float)
    sorted_indexes = np.argsort(probabilities)[::-1]
    predicted_index = int(sorted_indexes[0])
    second_index = int(sorted_indexes[1]) if len(sorted_indexes) > 1 else predicted_index
    confidence = float(probabilities[predicted_index])
    second_probability = float(probabilities[second_index]) if second_index != predicted_index else 0.0
    class_probabilities = {
        label_mapping[index]: round(float(probabilities[index]), 8)
        for index in sorted(label_mapping)
    }

    # Deprecated compatibility field for the existing Stage 4 input contract.
    # Stage 4 should migrate to deriving threat risk from prediction evidence.
    legacy_base_risk_score = int(round(confidence * 100))

    return {
        "id": str(alert_id),
        "predictionStatus": "available",
        "predictedClassIndex": predicted_index,
        "predictedAttackType": label_mapping[predicted_index],
        "modelConfidence": round(confidence, 8),
        "classProbabilities": class_probabilities,
        "secondBestClass": label_mapping[second_index],
        "predictionMargin": round(confidence - second_probability, 8),
        "modelProvenance": provenance,
        "legacyBaseRiskScore": legacy_base_risk_score,
        "baseRiskScore": legacy_base_risk_score,
        "baseRiskScoreStatus": "legacy_confidence_compatibility_not_threat_risk",
    }


def unavailable_ml_explanation(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "method": TREESHAP_METHOD,
    }


def feature_contribution_record(
    feature_name: str,
    feature_value: float,
    shap_contribution: float,
    direction: str,
) -> dict[str, Any]:
    return {
        "featureName": feature_name,
        "featureValue": float(feature_value),
        "shapContribution": float(shap_contribution),
        "direction": direction,
    }


def top_feature_contributions(
    feature_values: np.ndarray,
    contributions: np.ndarray,
    feature_columns: list[str],
    limit: int = TREESHAP_DISPLAY_FEATURE_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supporting_indexes = [index for index, value in enumerate(contributions) if float(value) > 0]
    opposing_indexes = [index for index, value in enumerate(contributions) if float(value) < 0]

    supporting_indexes.sort(key=lambda index: (-float(contributions[index]), feature_columns[index]))
    opposing_indexes.sort(key=lambda index: (float(contributions[index]), feature_columns[index]))

    supporting = [
        feature_contribution_record(
            feature_columns[index],
            float(feature_values[index]),
            float(contributions[index]),
            "supports_prediction",
        )
        for index in supporting_indexes[:limit]
    ]
    opposing = [
        feature_contribution_record(
            feature_columns[index],
            float(feature_values[index]),
            float(contributions[index]),
            "opposes_prediction",
        )
        for index in opposing_indexes[:limit]
    ]
    return supporting, opposing


def validate_prediction_output_shape(probabilities: np.ndarray, row_count: int, class_count: int) -> np.ndarray:
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim == 1:
        probabilities = probabilities.reshape(1, -1)
    if probabilities.shape != (row_count, class_count):
        raise InferenceConfigurationError(
            f"Probability vector length or output shape {probabilities.shape} does not match "
            f"expected shape ({row_count}, {class_count})."
        )
    return probabilities


def validate_raw_margin_shape(raw_margins: np.ndarray, row_count: int, class_count: int) -> np.ndarray:
    raw_margins = np.asarray(raw_margins, dtype=float)
    if raw_margins.shape != (row_count, class_count):
        raise InferenceConfigurationError(
            f"Raw-margin output shape {raw_margins.shape} does not match expected "
            f"shape ({row_count}, {class_count})."
        )
    return raw_margins


def validate_treeshap_contribution_shape(
    contributions: np.ndarray,
    row_count: int,
    class_count: int,
    feature_count: int,
) -> np.ndarray:
    contributions = np.asarray(contributions, dtype=float)
    expected_shape = (row_count, class_count, feature_count + 1)
    if contributions.shape != expected_shape:
        raise InferenceConfigurationError(
            f"TreeSHAP contribution shape {contributions.shape} does not match expected "
            f"shape {expected_shape}."
        )
    return contributions


def predicted_class_explanation(
    predicted_class_index: int,
    predicted_attack_type: str,
    feature_values: np.ndarray,
    raw_margin: float,
    contribution_vector: np.ndarray,
    feature_columns: list[str],
    tolerance: float = TREESHAP_ADDITIVITY_TOLERANCE,
) -> dict[str, Any]:
    feature_contributions = np.asarray(contribution_vector[:-1], dtype=float)
    base_value = float(contribution_vector[-1])
    if len(feature_contributions) != len(feature_columns):
        return unavailable_ml_explanation("unexpected_treeshap_feature_dimension")

    reconstructed_margin = base_value + float(np.sum(feature_contributions))
    difference = abs(reconstructed_margin - float(raw_margin))
    additivity_passed = difference <= tolerance
    supporting, opposing = top_feature_contributions(feature_values, feature_contributions, feature_columns)

    return {
        "status": "available" if additivity_passed else "unavailable",
        **({} if additivity_passed else {"reason": "additivity_check_failed"}),
        "method": TREESHAP_METHOD,
        "outputSpace": TREESHAP_OUTPUT_SPACE,
        "explainedClass": predicted_attack_type,
        "explainedClassIndex": predicted_class_index,
        "baseValue": base_value,
        "rawModelMargin": float(raw_margin),
        "topSupportingFeatures": supporting,
        "topOpposingFeatures": opposing,
        "additivityCheck": {
            "passed": additivity_passed,
            "difference": difference,
            "tolerance": tolerance,
        },
    }


def generate_treeshap_explanations(
    artifacts: ModelArtifacts,
    dmatrix: Any,
    feature_matrix: np.ndarray,
    prediction_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    row_count = len(prediction_records)
    class_count = len(artifacts.label_mapping)
    feature_count = len(artifacts.feature_columns)

    raw_margins = validate_raw_margin_shape(
        artifacts.model.predict(dmatrix, output_margin=True, strict_shape=True),
        row_count,
        class_count,
    )
    contributions = validate_treeshap_contribution_shape(
        artifacts.model.predict(dmatrix, pred_contribs=True, strict_shape=True),
        row_count,
        class_count,
        feature_count,
    )

    explanations: list[dict[str, Any]] = []
    for index, record in enumerate(prediction_records):
        predicted_index = int(record["predictedClassIndex"])
        explanations.append(
            predicted_class_explanation(
                predicted_index,
                str(record["predictedAttackType"]),
                feature_matrix[index],
                float(raw_margins[index, predicted_index]),
                contributions[index, predicted_index],
                artifacts.feature_columns,
            )
        )
    return explanations


def predict_dataframe(
    dataframe: pd.DataFrame,
    artifacts: ModelArtifacts,
    duplicate_header_columns: list[str] | None = None,
    allow_synthetic_ids: bool = False,
    include_explanations: bool = True,
) -> list[dict[str, Any]]:
    schema = validate_dataframe_schema(dataframe, artifacts.feature_columns)
    duplicate_inputs = sorted(set(schema["duplicateColumns"] + (duplicate_header_columns or [])))

    if schema["missingIdColumns"] and not allow_synthetic_ids:
        return unavailable_for_rows(
            dataframe,
            "missing_id_column",
            artifacts,
            invalid_feature_columns=schema["missingIdColumns"],
            allow_synthetic_ids=allow_synthetic_ids,
        )

    if duplicate_inputs:
        return unavailable_for_rows(
            dataframe,
            "duplicate_feature_columns",
            artifacts,
            duplicate_feature_columns=duplicate_inputs,
            allow_synthetic_ids=allow_synthetic_ids,
        )

    if schema["forbiddenColumns"]:
        return unavailable_for_rows(
            dataframe,
            "forbidden_prediction_fields_present",
            artifacts,
            invalid_feature_columns=schema["forbiddenColumns"],
            allow_synthetic_ids=allow_synthetic_ids,
        )

    if schema["missingFeatureColumns"]:
        return unavailable_for_rows(
            dataframe,
            "missing_required_feature_columns",
            artifacts,
            missing_feature_columns=schema["missingFeatureColumns"],
            allow_synthetic_ids=allow_synthetic_ids,
        )

    ambiguous_ids = duplicate_alert_ids(dataframe)

    prepared_rows: list[np.ndarray] = []
    prepared_indexes: list[int] = []
    prediction_records: list[dict[str, Any] | None] = [None] * len(dataframe)

    for index, (_, row) in enumerate(dataframe.iterrows()):
        alert_id = row_id(row, index, allow_synthetic_ids)
        if alert_id is None:
            prediction_records[index] = unavailable_record(
                None,
                "missing_or_invalid_alert_id",
                invalid_feature_columns=["id"],
                model_provenance=artifacts.provenance,
                source_row_number=index + 1,
            )
            continue
        if alert_id in ambiguous_ids:
            prediction_records[index] = unavailable_record(
                alert_id,
                "duplicate_alert_id",
                invalid_feature_columns=["id"],
                model_provenance=artifacts.provenance,
                source_row_number=index + 1,
            )
            continue
        prepared, invalid_columns = validate_and_prepare_row(row, artifacts.feature_columns)
        if invalid_columns:
            prediction_records[index] = unavailable_record(
                alert_id,
                "invalid_numeric_feature_values",
                invalid_feature_columns=invalid_columns,
                model_provenance=artifacts.provenance,
                source_row_number=index + 1,
            )
            continue
        prepared_rows.append(prepared)
        prepared_indexes.append(index)

    if prepared_rows:
        feature_matrix = np.vstack(prepared_rows).astype(np.float32)
        dmatrix = xgb.DMatrix(feature_matrix, feature_names=artifacts.feature_columns)
        probabilities = validate_prediction_output_shape(
            artifacts.model.predict(dmatrix, strict_shape=True),
            len(prepared_rows),
            len(artifacts.label_mapping),
        )
        available_records: list[dict[str, Any]] = []
        for output_index, probability_vector in zip(prepared_indexes, probabilities):
            record_id = row_id(dataframe.iloc[output_index], output_index, allow_synthetic_ids)
            record = probability_record(
                record_id,
                probability_vector,
                artifacts.label_mapping,
                artifacts.provenance,
            )
            available_records.append(record)
            prediction_records[output_index] = record

        if include_explanations:
            try:
                explanations = generate_treeshap_explanations(artifacts, dmatrix, feature_matrix, available_records)
            except Exception as exc:  # Explanation failure must not invalidate prediction.
                reason = f"treeshap_generation_failed: {type(exc).__name__}: {exc}"
                explanations = [unavailable_ml_explanation(reason) for _ in available_records]
        else:
            explanations = [unavailable_ml_explanation("explainability_disabled") for _ in available_records]

        for record, explanation in zip(available_records, explanations):
            record["mlExplanation"] = explanation

    for record in prediction_records:
        if record is not None and record.get("predictionStatus") == "unavailable":
            record["mlExplanation"] = unavailable_ml_explanation("prediction_unavailable")

    return [record for record in prediction_records if record is not None]


def predict_csv(input_path: Path, artifacts: ModelArtifacts, include_explanations: bool = True) -> list[dict[str, Any]]:
    dataframe, duplicate_header_columns = read_feature_csv(input_path)
    return predict_dataframe(
        dataframe,
        artifacts,
        duplicate_header_columns=duplicate_header_columns,
        include_explanations=include_explanations,
    )


def write_predictions(predictions: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions, indent=2) + "\n", encoding="utf-8")
