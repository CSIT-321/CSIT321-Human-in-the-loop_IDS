"""The model half of detection (plan step S9), behind one small protocol.

``XgboostPredictor`` runs the committed 8-class model with **native TreeSHAP at detection time**
(D8): an explanation is computed once, with the prediction, and stored on the alert — never on
demand, which would blow the ~2 s budget NFR-04 sets.

``ReplayPredictor`` reads predictions a previous run wrote (``scripts/run_ml_inference.py``). It
exists for two honest reasons: a detection run can be replayed on a machine without xgboost, and a
test can drive the whole pipeline without loading a model. It is not a substitute for D8 — a run
that uses it says so in its summary (``explanations_computed``).

The frame handed to the model is ``id`` plus exactly the 82 feature columns, built from the
release's own values, so these predictions are the ones
``data/processed/demo_ml_predictions_shap.json`` already carries.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from packages.contracts import models as m
from packages.detection.pipeline.source import Flow, feature_frame

HITL = Path(__file__).resolve().parents[3]
#: The version the committed model is registered under (``ml_models.version``).
MODEL_VERSION = "xgb-8class-20260911"
MODEL_FILE = "models/xgboost_ids_model.json"


class Predictor(Protocol):
    """Predicts a batch of flows. Keys of the result are ``Flow.source_record_id``."""

    version: str
    computes_explanations: bool

    def predict(self, flows: Sequence[Flow]) -> dict[str, m.MlPrediction]:
        ...


def _load_inference() -> Any:
    """Import the vendored inference module (it is not a package — see its docstring)."""
    path = HITL / "packages" / "detection" / "ml"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    import inference  # noqa: PLC0415

    return inference


class XgboostPredictor:
    """The committed model plus native TreeSHAP, computed in the run itself (D8)."""

    computes_explanations = True

    def __init__(self, version: str = MODEL_VERSION, artifacts: Any | None = None) -> None:
        self._inference = _load_inference()
        self.artifacts = (artifacts if artifacts is not None
                          else self._inference.load_model_artifacts())
        self.version = version

    @property
    def feature_columns(self) -> list[str]:
        return list(self.artifacts.feature_columns)

    def predict(self, flows: Sequence[Flow]) -> dict[str, m.MlPrediction]:
        if not flows:
            return {}
        frame = feature_frame(flows, self.artifacts.feature_columns)
        records = self._inference.predict_dataframe(frame, self.artifacts,
                                                    include_explanations=True)
        return {str(record["id"]): m.MlPrediction.model_validate(record) for record in records}


class ReplayPredictor:
    """Replays predictions an earlier run wrote. Explanations are whatever that run computed."""

    computes_explanations = False

    def __init__(self, path: str | Path, version: str = MODEL_VERSION) -> None:
        self.path = Path(path)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        records = document.values() if isinstance(document, dict) else document
        self._records = {str(record["id"]): record for record in records}
        self.version = version

    def predict(self, flows: Sequence[Flow]) -> dict[str, m.MlPrediction]:
        missing = [flow.source_record_id for flow in flows
                   if flow.source_record_id not in self._records]
        if missing:
            raise LookupError(f"{self.path.name} has no prediction for {missing[:5]}"
                              f"{'...' if len(missing) > 5 else ''}")
        return {flow.source_record_id:
                m.MlPrediction.model_validate(self._records[flow.source_record_id])
                for flow in flows}
