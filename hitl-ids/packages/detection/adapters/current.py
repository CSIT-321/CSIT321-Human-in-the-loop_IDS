"""Compatibility adapter for Signature + XGBoost/TreeSHAP."""
from dataclasses import dataclass

from packages.contracts import models as m
from packages.contracts.canonical import CanonicalAlert


@dataclass(frozen=True)
class CurrentDetectorOutput:
    alert: m.Alert
    flow: m.FlowRecord
    model_version: str | None
    rule_set_version: str | None
    prediction: m.MlPrediction | None = None
    legacy_projection: bool = False


class CurrentDetectorAdapter:
    def adapt(self, output: CurrentDetectorOutput) -> CanonicalAlert:
        alert, flow = output.alert, output.flow
        capture = flow.flow_features.get("Timestamp")
        occurred = str(capture) if capture is not None else alert.created_at.isoformat()
        prediction = output.prediction
        confidence = (prediction.model_confidence if prediction is not None
                      and prediction.prediction_status == "available" else None)
        confidence_basis = "model-prediction" if confidence is not None else "not-available"
        # In these CEF branches the legacy confidence was copied directly from the model.
        # Corroboration and overrides mix in rule severity, so cannot be recovered this way.
        if (output.legacy_projection and alert.evidence_class in ("ml_only", "none")
                and alert.ml_predicted_class is not None):
            confidence = alert.confidence
            confidence_basis = "legacy-model-confidence"
        evidence = {
            "detectionScore": alert.detection_score,
            "signatureSeverity": alert.signature_severity,
            "signatureRules": [match.model_dump(mode="json") for match in alert.signature_rules or []],
            "mlPredictedClass": alert.ml_predicted_class,
            "mlProbability": alert.ml_probability,
            "treeShap": alert.shap_attributions.model_dump(mode="json") if alert.shap_attributions else None,
            "explanation": alert.explanation,
        }
        return CanonicalAlert(
            canonical_alert_id=alert.alert_ref, occurred_at=occurred,
            detector_source="current_flow", detector_name="Signature + XGBoost",
            detector_version=output.model_version,
            detection_title="; ".join(match.name for match in alert.signature_rules or [])
                            or ("XGBoost: " + (alert.ml_predicted_class or "Prediction unavailable")),
            detection_category=alert.attack_category, detector_severity=alert.severity,
            confidence=confidence, source_ip=flow.src_ip, destination_ip=flow.dst_ip,
            source_port=flow.src_port, destination_port=flow.dst_port, protocol=flow.protocol,
            evidence_class=alert.evidence_class, structured_evidence=evidence,
            provenance={
                "adapterVersion": "current-flow-v1", "modelVersion": output.model_version,
                "ruleSetVersion": output.rule_set_version,
                "timestampBasis": "capture-local" if capture is not None else "detection-time",
                "legacyProjection": output.legacy_projection,
                "confidenceBasis": confidence_basis,
            },
            source_record_reference=flow.source_record_id,
            original_detector_fields={
                **evidence, "severity": alert.severity, "legacyFusionConfidence": alert.confidence,
                "evidenceClass": alert.evidence_class,
                "prediction": prediction.model_dump(mode="json") if prediction else None,
            },
        )
