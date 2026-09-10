from __future__ import annotations

import math
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "stage-3" / "core"))
sys.path.insert(0, str(REPO_ROOT / "stage-3" / "scripts"))

from ml_inference import (  # noqa: E402
    DEFAULT_FEATURE_COLUMNS_PATH,
    DEFAULT_FEATURE_INPUT_PATH,
    DEFAULT_LABEL_MAPPING_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_PREPROCESSING_CONFIG_PATH,
    InferenceConfigurationError,
    TREESHAP_ADDITIVITY_TOLERANCE,
    TREESHAP_METHOD,
    TREESHAP_OUTPUT_SPACE,
    load_json,
    load_model_artifacts,
    predict_dataframe,
    sha256_file,
)
from run_ml_prediction_demo import compare_predictions, repo_relative_path, summarize_explainability  # noqa: E402


def load_feature_rows(limit: int = 3) -> pd.DataFrame:
    return pd.read_csv(DEFAULT_FEATURE_INPUT_PATH, low_memory=False).head(limit)


def mutable_feature_rows(limit: int = 3) -> pd.DataFrame:
    return load_feature_rows(limit).astype(object)


def assert_available_prediction(record: dict) -> None:
    assert record["predictionStatus"] == "available"
    assert record["predictedClassIndex"] is not None
    assert record["predictedAttackType"]
    assert record["modelConfidence"] is not None
    assert record["classProbabilities"]


PREDICTION_INVARIANT_FIELDS = [
    "predictionStatus",
    "predictedClassIndex",
    "predictedAttackType",
    "modelConfidence",
    "classProbabilities",
    "secondBestClass",
    "predictionMargin",
    "modelProvenance",
    "legacyBaseRiskScore",
    "baseRiskScore",
    "baseRiskScoreStatus",
]


def test_committed_model_loads_successfully() -> None:
    artifacts = load_model_artifacts()

    assert artifacts.model.num_features() == 78
    assert artifacts.provenance["modelSha256"] == sha256_file(DEFAULT_MODEL_PATH)


def test_model_feature_count_is_78() -> None:
    artifacts = load_model_artifacts()

    assert len(artifacts.feature_columns) == 78


def test_feature_order_exactly_matches_feature_columns_json() -> None:
    artifacts = load_model_artifacts()
    feature_columns = load_json(DEFAULT_FEATURE_COLUMNS_PATH)

    assert artifacts.feature_columns == feature_columns


def test_input_columns_are_reordered_to_exact_feature_schema() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1)
    shuffled = dataframe[["id", *reversed(artifacts.feature_columns)]]
    predictions = predict_dataframe(shuffled, artifacts)

    assert_available_prediction(predictions[0])


def test_missing_feature_column_returns_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1).drop(columns=[artifacts.feature_columns[0]])
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "missing_required_feature_columns"
    assert artifacts.feature_columns[0] in predictions[0]["missingFeatureColumns"]


def test_missing_id_column_returns_unavailable_prediction_without_synthetic_id() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1).drop(columns=["id"])
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["id"] is None
    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "missing_id_column"


def test_blank_or_nan_row_id_returns_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(2)
    dataframe.loc[dataframe.index[0], "id"] = ""
    dataframe.loc[dataframe.index[1], "id"] = np.nan
    predictions = predict_dataframe(dataframe, artifacts)

    assert [record["id"] for record in predictions] == [None, None]
    assert all(record["predictionStatus"] == "unavailable" for record in predictions)
    assert all(record["failureReason"] == "missing_or_invalid_alert_id" for record in predictions)


def test_duplicate_alert_ids_reject_affected_ambiguous_records_only() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(3)
    dataframe.loc[dataframe.index[0], "id"] = "AL-DUP"
    dataframe.loc[dataframe.index[1], "id"] = "AL-DUP"
    dataframe.loc[dataframe.index[2], "id"] = "AL-UNIQUE"
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "duplicate_alert_id"
    assert predictions[1]["predictionStatus"] == "unavailable"
    assert predictions[1]["failureReason"] == "duplicate_alert_id"
    assert predictions[2]["predictionStatus"] == "available"


def test_legacy_synthetic_ids_require_explicit_compatibility_option() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1).drop(columns=["id"])
    predictions = predict_dataframe(dataframe, artifacts, allow_synthetic_ids=True)

    assert predictions[0]["id"] == "ROW-0001"
    assert predictions[0]["predictionStatus"] == "available"


def test_duplicate_feature_column_returns_safe_rejection() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1)
    duplicate_name = artifacts.feature_columns[0]
    dataframe = pd.concat([dataframe, dataframe[[duplicate_name]]], axis=1)
    dataframe.columns = list(dataframe.columns[:-1]) + [duplicate_name]
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "duplicate_feature_columns"
    assert duplicate_name in predictions[0]["duplicateFeatureColumns"]


def test_numeric_string_coercion_works() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(1)
    for column in artifacts.feature_columns:
        dataframe.loc[dataframe.index[0], column] = str(dataframe.loc[dataframe.index[0], column])
    predictions = predict_dataframe(dataframe, artifacts)

    assert_available_prediction(predictions[0])


def test_invalid_numeric_value_returns_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(1)
    dataframe.loc[dataframe.index[0], artifacts.feature_columns[0]] = "not-a-number"
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "invalid_numeric_feature_values"
    assert artifacts.feature_columns[0] in predictions[0]["invalidFeatureColumns"]


def test_nan_returns_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(1)
    dataframe.loc[dataframe.index[0], artifacts.feature_columns[0]] = np.nan
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "invalid_numeric_feature_values"


def test_positive_and_negative_infinity_return_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(2)
    dataframe.loc[dataframe.index[0], artifacts.feature_columns[0]] = math.inf
    dataframe.loc[dataframe.index[1], artifacts.feature_columns[0]] = -math.inf
    predictions = predict_dataframe(dataframe, artifacts)

    assert [record["predictionStatus"] for record in predictions] == ["unavailable", "unavailable"]
    assert all(record["failureReason"] == "invalid_numeric_feature_values" for record in predictions)


def test_value_too_large_for_float32_returns_unavailable_prediction() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(1)
    dataframe.loc[dataframe.index[0], artifacts.feature_columns[0]] = float(np.finfo(np.float32).max) * 2
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "unavailable"
    assert predictions[0]["failureReason"] == "invalid_numeric_feature_values"


def test_one_bad_row_does_not_prevent_valid_rows_being_predicted() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(3)
    dataframe.loc[dataframe.index[1], artifacts.feature_columns[0]] = "bad"
    predictions = predict_dataframe(dataframe, artifacts)

    assert predictions[0]["predictionStatus"] == "available"
    assert predictions[1]["predictionStatus"] == "unavailable"
    assert predictions[2]["predictionStatus"] == "available"


def test_probabilities_sum_to_one() -> None:
    artifacts = load_model_artifacts()
    predictions = predict_dataframe(load_feature_rows(3), artifacts)

    for record in predictions:
        assert_available_prediction(record)
        assert math.isclose(sum(record["classProbabilities"].values()), 1.0, rel_tol=0, abs_tol=1e-5)


def test_probability_vector_length_must_match_label_mapping() -> None:
    class WrongLengthModel:
        def predict(self, dmatrix, **kwargs):
            return np.array([[0.2, 0.2, 0.2, 0.2, 0.2]])

    artifacts = load_model_artifacts()
    broken_artifacts = replace(artifacts, model=WrongLengthModel())

    try:
        predict_dataframe(load_feature_rows(1), broken_artifacts)
    except InferenceConfigurationError as exc:
        assert "Probability vector length" in str(exc)
    else:
        raise AssertionError("Expected probability vector length mismatch to fail closed.")


def test_predicted_class_index_equals_probability_argmax() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts)[0]
    labels = list(artifacts.label_mapping.values())
    probabilities = [record["classProbabilities"][label] for label in labels]

    assert record["predictedClassIndex"] == int(np.argmax(probabilities))


def test_predicted_attack_type_matches_label_mapping() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts)[0]

    assert record["predictedAttackType"] == artifacts.label_mapping[record["predictedClassIndex"]]


def test_model_confidence_equals_max_probability() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts)[0]

    assert math.isclose(record["modelConfidence"], max(record["classProbabilities"].values()), abs_tol=1e-8)


def test_prediction_margin_is_top_minus_second_probability() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts)[0]
    probabilities = sorted(record["classProbabilities"].values(), reverse=True)

    assert math.isclose(record["predictionMargin"], probabilities[0] - probabilities[1], abs_tol=1e-8)


def test_sha256_provenance_matches_artifact_files() -> None:
    artifacts = load_model_artifacts()

    assert artifacts.provenance["modelSha256"] == sha256_file(DEFAULT_MODEL_PATH)
    assert artifacts.provenance["featureSchemaSha256"] == sha256_file(DEFAULT_FEATURE_COLUMNS_PATH)
    assert artifacts.provenance["preprocessingConfigSha256"] == sha256_file(DEFAULT_PREPROCESSING_CONFIG_PATH)
    assert artifacts.provenance["labelMappingSha256"] == sha256_file(DEFAULT_LABEL_MAPPING_PATH)


def test_prediction_path_does_not_require_ground_truth() -> None:
    artifacts = load_model_artifacts()
    predictions = predict_dataframe(load_feature_rows(2), artifacts)

    assert len(predictions) == 2
    assert all("groundTruth" not in record for record in predictions)
    assert all("rawLabel" not in record for record in predictions)
    assert all("mappedAttackType" not in record for record in predictions)


def test_unsupported_infiltration_is_represented_in_artifacts() -> None:
    artifacts = load_model_artifacts()
    preprocessing_config = artifacts.preprocessing_config

    assert "Infiltration" not in set(artifacts.label_mapping.values())
    assert preprocessing_config["missingExpectedAttackTypes"] == ["Infiltration"]


def test_native_treeshap_returns_expected_multiclass_shapes() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(2)
    feature_matrix = dataframe[artifacts.feature_columns].astype(np.float32).to_numpy()
    import xgboost as xgb

    dmatrix = xgb.DMatrix(feature_matrix, feature_names=artifacts.feature_columns)

    probabilities = artifacts.model.predict(dmatrix, strict_shape=True)
    raw_margins = artifacts.model.predict(dmatrix, output_margin=True, strict_shape=True)
    contributions = artifacts.model.predict(dmatrix, pred_contribs=True, strict_shape=True)

    assert probabilities.shape == (2, len(artifacts.label_mapping))
    assert raw_margins.shape == (2, len(artifacts.label_mapping))
    assert contributions.shape == (2, len(artifacts.label_mapping), len(artifacts.feature_columns) + 1)


def test_treeshap_explains_the_predicted_class_only() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts, include_explanations=True)[0]
    explanation = record["mlExplanation"]

    assert explanation["status"] == "available"
    assert explanation["method"] == TREESHAP_METHOD
    assert explanation["outputSpace"] == TREESHAP_OUTPUT_SPACE
    assert explanation["explainedClassIndex"] == record["predictedClassIndex"]
    assert explanation["explainedClass"] == record["predictedAttackType"]


def test_treeshap_base_value_and_all_feature_contributions_are_additive() -> None:
    artifacts = load_model_artifacts()
    predictions = predict_dataframe(load_feature_rows(1000), artifacts, include_explanations=True)
    available = [record for record in predictions if record["predictionStatus"] == "available"]
    represented_classes = sorted({record["predictedAttackType"] for record in available})

    assert len(represented_classes) > 1
    for class_name in represented_classes:
        record = next(item for item in available if item["predictedAttackType"] == class_name)
        check = record["mlExplanation"]["additivityCheck"]
        assert check["passed"] is True
        assert check["difference"] <= TREESHAP_ADDITIVITY_TOLERANCE
        assert check["tolerance"] == TREESHAP_ADDITIVITY_TOLERANCE


def test_treeshap_supporting_and_opposing_features_are_signed_ordered_and_limited() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts, include_explanations=True)[0]
    explanation = record["mlExplanation"]
    supporting = explanation["topSupportingFeatures"]
    opposing = explanation["topOpposingFeatures"]

    assert len(supporting) <= 5
    assert len(opposing) <= 5
    assert all(item["shapContribution"] > 0 for item in supporting)
    assert all(item["direction"] == "supports_prediction" for item in supporting)
    assert all(item["shapContribution"] < 0 for item in opposing)
    assert all(item["direction"] == "opposes_prediction" for item in opposing)
    assert supporting == sorted(supporting, key=lambda item: (-item["shapContribution"], item["featureName"]))
    assert opposing == sorted(opposing, key=lambda item: (item["shapContribution"], item["featureName"]))


def test_treeshap_feature_values_match_model_input_values() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1)
    record = predict_dataframe(dataframe, artifacts, include_explanations=True)[0]
    explanation = record["mlExplanation"]

    for item in explanation["topSupportingFeatures"] + explanation["topOpposingFeatures"]:
        expected_value = float(np.float32(pd.to_numeric(pd.Series([dataframe.loc[dataframe.index[0], item["featureName"]]])).iloc[0]))
        assert math.isclose(item["featureValue"], expected_value, rel_tol=0, abs_tol=1e-6)


def test_treeshap_failure_leaves_prediction_fields_unchanged() -> None:
    class FailingExplanationModel:
        def __init__(self, wrapped_model):
            self.wrapped_model = wrapped_model

        def predict(self, dmatrix, **kwargs):
            if kwargs.get("output_margin") or kwargs.get("pred_contribs"):
                raise RuntimeError("forced explanation failure")
            return self.wrapped_model.predict(dmatrix, **kwargs)

    artifacts = load_model_artifacts()
    baseline = predict_dataframe(load_feature_rows(3), artifacts, include_explanations=False)
    broken_artifacts = replace(artifacts, model=FailingExplanationModel(artifacts.model))
    with_failure = predict_dataframe(load_feature_rows(3), broken_artifacts, include_explanations=True)

    for old_record, new_record in zip(baseline, with_failure):
        for field in PREDICTION_INVARIANT_FIELDS:
            assert old_record[field] == new_record[field]
        assert new_record["predictionStatus"] == "available"
        assert new_record["mlExplanation"]["status"] == "unavailable"
        assert "treeshap_generation_failed" in new_record["mlExplanation"]["reason"]


def test_additivity_failure_marks_explanation_unavailable_without_changing_prediction() -> None:
    class AdditivityMismatchModel:
        def __init__(self, wrapped_model):
            self.wrapped_model = wrapped_model

        def predict(self, dmatrix, **kwargs):
            if kwargs.get("output_margin"):
                return self.wrapped_model.predict(dmatrix, **kwargs) + 1.0
            return self.wrapped_model.predict(dmatrix, **kwargs)

    artifacts = load_model_artifacts()
    baseline = predict_dataframe(load_feature_rows(3), artifacts, include_explanations=False)
    broken_artifacts = replace(artifacts, model=AdditivityMismatchModel(artifacts.model))
    with_mismatch = predict_dataframe(load_feature_rows(3), broken_artifacts, include_explanations=True)

    for old_record, new_record in zip(baseline, with_mismatch):
        for field in PREDICTION_INVARIANT_FIELDS:
            assert old_record[field] == new_record[field]
        assert new_record["predictionStatus"] == "available"
        assert new_record["mlExplanation"]["status"] == "unavailable"
        assert new_record["mlExplanation"]["reason"] == "additivity_check_failed"
        assert new_record["mlExplanation"]["additivityCheck"]["passed"] is False


def test_invalid_prediction_record_does_not_attempt_treeshap() -> None:
    artifacts = load_model_artifacts()
    dataframe = load_feature_rows(1).drop(columns=["id"])
    record = predict_dataframe(dataframe, artifacts, include_explanations=True)[0]

    assert record["predictionStatus"] == "unavailable"
    assert record["mlExplanation"] == {
        "status": "unavailable",
        "reason": "prediction_unavailable",
        "method": TREESHAP_METHOD,
    }


def test_ml_explanation_contains_no_ground_truth_fields() -> None:
    artifacts = load_model_artifacts()
    record = predict_dataframe(load_feature_rows(1), artifacts, include_explanations=True)[0]
    explanation_text = json.dumps(record["mlExplanation"])

    assert "groundTruth" not in explanation_text
    assert "rawLabel" not in explanation_text
    assert "mappedAttackType" not in explanation_text


def test_explanations_do_not_change_prediction_outputs() -> None:
    artifacts = load_model_artifacts()
    without_explanations = predict_dataframe(load_feature_rows(20), artifacts, include_explanations=False)
    with_explanations = predict_dataframe(load_feature_rows(20), artifacts, include_explanations=True)

    for plain_record, explained_record in zip(without_explanations, with_explanations):
        for field in PREDICTION_INVARIANT_FIELDS:
            assert plain_record[field] == explained_record[field]
        assert explained_record["mlExplanation"]["status"] == "available"


def test_explainability_summary_counts_unavailable_reasons_across_all_rows() -> None:
    artifacts = load_model_artifacts()
    dataframe = mutable_feature_rows(3)
    dataframe.loc[dataframe.index[1], "id"] = ""
    predictions = predict_dataframe(dataframe, artifacts, include_explanations=True)
    summary = summarize_explainability(predictions, artifacts)

    assert summary["inputCount"] == 3
    assert summary["availablePredictionCount"] == 2
    assert summary["unavailablePredictionCount"] == 1
    assert summary["availableExplanationCount"] == 2
    assert summary["unavailableExplanationCount"] == 1
    assert summary["unavailableExplanationReasons"]["predictionUnavailable"] == 1
    assert summary["unavailableExplanationReasons"]["treeShapGenerationFailure"] == 0
    assert summary["unavailableExplanationReasons"]["additivityFailure"] == 0


def test_explainability_summary_counts_additivity_failures_separately() -> None:
    class AdditivityMismatchModel:
        def __init__(self, wrapped_model):
            self.wrapped_model = wrapped_model

        def predict(self, dmatrix, **kwargs):
            if kwargs.get("output_margin"):
                return self.wrapped_model.predict(dmatrix, **kwargs) + 1.0
            return self.wrapped_model.predict(dmatrix, **kwargs)

    artifacts = load_model_artifacts()
    broken_artifacts = replace(artifacts, model=AdditivityMismatchModel(artifacts.model))
    predictions = predict_dataframe(load_feature_rows(2), broken_artifacts, include_explanations=True)
    summary = summarize_explainability(predictions, broken_artifacts)

    assert summary["availablePredictionCount"] == 2
    assert summary["availableExplanationCount"] == 0
    assert summary["unavailableExplanationCount"] == 2
    assert summary["unavailableExplanationReasons"]["predictionUnavailable"] == 0
    assert summary["unavailableExplanationReasons"]["treeShapGenerationFailure"] == 0
    assert summary["unavailableExplanationReasons"]["additivityFailure"] == 2
    assert summary["additivityPassedCount"] == 0
    assert summary["additivityFailedCount"] == 2


def copy_artifacts_to_temp(temp_dir: Path) -> dict[str, Path]:
    paths = {
        "model": temp_dir / "xgboost_ids_model.json",
        "features": temp_dir / "feature-columns.json",
        "labels": temp_dir / "label-mapping.json",
        "config": temp_dir / "preprocessing-config.json",
    }
    shutil.copyfile(DEFAULT_MODEL_PATH, paths["model"])
    shutil.copyfile(DEFAULT_FEATURE_COLUMNS_PATH, paths["features"])
    shutil.copyfile(DEFAULT_LABEL_MAPPING_PATH, paths["labels"])
    shutil.copyfile(DEFAULT_PREPROCESSING_CONFIG_PATH, paths["config"])
    return paths


@contextmanager
def temporary_workspace_directory():
    temp_root = REPO_ROOT / ".tmp-stage-3-tests"
    temp_root.mkdir(exist_ok=True)
    temp_dir = temp_root / f"case-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield str(temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_model_objective_must_be_multiclass_softprob() -> None:
    with temporary_workspace_directory() as temp:
        paths = copy_artifacts_to_temp(Path(temp))
        model_json = load_json(paths["model"])
        model_json["learner"]["objective"]["name"] = "multi:softmax"
        paths["model"].write_text(json.dumps(model_json), encoding="utf-8")

        try:
            load_model_artifacts(paths["model"], paths["features"], paths["labels"], paths["config"])
        except InferenceConfigurationError as exc:
            assert "multi:softprob" in str(exc)
        else:
            raise AssertionError("Expected incompatible objective to fail closed.")


def test_model_class_count_must_match_label_mapping() -> None:
    with temporary_workspace_directory() as temp:
        paths = copy_artifacts_to_temp(Path(temp))
        label_mapping = load_json(paths["labels"])
        label_mapping.pop("5")
        paths["labels"].write_text(json.dumps(label_mapping), encoding="utf-8")

        try:
            load_model_artifacts(paths["model"], paths["features"], paths["labels"], paths["config"])
        except InferenceConfigurationError as exc:
            assert "class count" in str(exc)
        else:
            raise AssertionError("Expected class-count mismatch to fail closed.")


def test_preprocessing_selected_features_must_match_feature_schema() -> None:
    with temporary_workspace_directory() as temp:
        paths = copy_artifacts_to_temp(Path(temp))
        config = load_json(paths["config"])
        selected = list(config["selectedFeatures"])
        selected[0], selected[1] = selected[1], selected[0]
        config["selectedFeatures"] = selected
        paths["config"].write_text(json.dumps(config), encoding="utf-8")

        try:
            load_model_artifacts(paths["model"], paths["features"], paths["labels"], paths["config"])
        except InferenceConfigurationError as exc:
            assert "selectedFeatures" in str(exc)
        else:
            raise AssertionError("Expected preprocessing feature mismatch to fail closed.")


def test_overwrite_sample_is_blocked_until_stage_4_supports_unavailable_predictions() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "stage-3" / "scripts" / "run_ml_prediction_demo.py"),
            "--overwrite-sample",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "blocked" in result.stderr or "blocked" in result.stdout


def test_reproducibility_summary_paths_are_repo_relative() -> None:
    regenerated_path = REPO_ROOT / "stage-3" / "outputs" / "ml-predictions.regenerated.json"
    committed_path = REPO_ROOT / "stage-3" / "outputs" / "ml-predictions.sample.json"

    assert repo_relative_path(DEFAULT_FEATURE_INPUT_PATH) == "stage-1/data/processed/flow-feature-full.csv"
    assert repo_relative_path(regenerated_path) == "stage-3/outputs/ml-predictions.regenerated.json"
    assert repo_relative_path(committed_path) == "stage-3/outputs/ml-predictions.sample.json"


def test_prediction_output_can_be_regenerated_from_committed_artifacts() -> None:
    artifacts = load_model_artifacts()
    predictions = predict_dataframe(load_feature_rows(5), artifacts)
    comparison = compare_predictions(predictions)

    assert len(predictions) == 5
    assert all(record["predictionStatus"] == "available" for record in predictions)
    assert comparison is not None


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
