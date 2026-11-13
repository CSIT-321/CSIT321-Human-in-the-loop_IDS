"""Fixtures shared by the test suite.

The synthetic capture lives here rather than in one test module because two steps need it: S15's
evaluation harness and S10b's API handlers. It is deliberately **not** the demo sample - the suite
must pass on a fresh checkout, where `data/demo.db` is gitignored and absent.

Its shape is chosen to exercise the things that matter: two flagged families large enough to leave
untouched members once three verdicts open the gate, a benign flow the model calls an attack (so a
false positive exists to find), and benign background nobody flags.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.contracts import models as m

T0 = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)

FTP_RULE = m.SignatureRule(
    rule_id="SIG-FTP-BRUTE-FORCE", name="FTP Brute Force Flow Pattern", severity="Medium",
    conditions={"protocol": "TCP", "destinationPort": 21, "totalFwdPackets": {"min": 1}},
    version="test-1", attack_category="Brute Force",
    rationale="Repeated short TCP flows against port 21.")

COLUMNS = ["alert_id", "attack_class", "is_attempted", "Flow ID", "Src IP", "Src Port", "Dst IP",
           "Dst Port", "Protocol", "Timestamp", "Flow Duration", "Total Fwd Packet",
           "Total Bwd packets", "Total Length of Fwd Packet", "Total Length of Bwd Packet",
           "Flow Bytes/s", "Flow Packets/s", "Packet Length Mean", "Fwd Packet Length Mean",
           "SYN Flag Count", "ACK Flag Count", "FIN Flag Count", "RST Flag Count", "Label",
           "Attempted Category"]



def row(alert_id: str, *, minute: int, dst_port: int, protocol: int = 6, truth: str = "Benign",
        predicted: str = "Benign") -> dict[str, object]:
    return {
        "alert_id": alert_id, "attack_class": truth, "is_attempted": 0,
        "Flow ID": f"flow-{alert_id}", "Src IP": "172.31.69.25", "Src Port": 51514,
        "Dst IP": "18.221.219.4", "Dst Port": dst_port, "Protocol": protocol,
        "Timestamp": f"2018-03-01 12:{minute:02d}:42.329367",
        "Flow Duration": 420000, "Total Fwd Packet": 4, "Total Bwd packets": 2,
        "Total Length of Fwd Packet": 3000, "Total Length of Bwd Packet": 190,
        "Flow Bytes/s": "1000.5", "Flow Packets/s": 54.2, "Packet Length Mean": 120.5,
        "Fwd Packet Length Mean": 118.0, "SYN Flag Count": 1, "ACK Flag Count": 1,
        "FIN Flag Count": 0, "RST Flag Count": 0, "Label": truth, "Attempted Category": "-",
        # not a capture column: the test's own note of what the model should say
        "_predicted": predicted,
    }


def capture() -> list[dict[str, object]]:
    """Two flagged families large enough to leave untouched members, plus benign background.

    ``AL-0009`` is the interesting one: a genuinely benign flow the model calls Brute Force, which
    therefore joins the Brute Force family. Whether family learning carries a promotion onto it is
    a *result*, not something these tests require either way.
    """
    rows: list[dict[str, object]] = []
    for i in range(1, 9):  # Brute Force on TCP/21: the rule matches and the model agrees
        rows.append(row(f"AL-{i:04d}", minute=i, dst_port=21, truth="Brute Force",
                        predicted="Brute Force"))
    rows.append(row("AL-0009", minute=9, dst_port=21, truth="Benign", predicted="Brute Force"))
    for i in range(10, 16):  # Botnet on TCP/8080: no rule, the model alone
        rows.append(row(f"AL-{i:04d}", minute=i, dst_port=8080, truth="Botnet",
                        predicted="Botnet"))
    for i in range(16, 22):  # benign background nobody flags
        rows.append(row(f"AL-{i:04d}", minute=i, dst_port=53, protocol=17))
    return rows


ROWS = capture()


@pytest.fixture
def sample(tmp_path) -> Path:
    path = tmp_path / "sample.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ROWS)
    return path


@pytest.fixture
def predictions(tmp_path) -> Path:
    path = tmp_path / "predictions.json"
    records = {}
    for entry in ROWS:
        predicted = str(entry["_predicted"])
        confidence = 0.99 if predicted != "Benign" else 0.97
        index = 0 if predicted == "Benign" else 2
        records[entry["alert_id"]] = {
            "id": entry["alert_id"], "predictionStatus": "available",
            "predictedClassIndex": index,
            "predictedAttackType": predicted, "modelConfidence": confidence,
            "classProbabilities": {predicted: confidence,
                                   "DoS" if predicted == "Benign" else "Benign":
                                       round(1 - confidence, 4)},
            "mlExplanation": {
                "status": "available", "method": "xgboost_native_treeshap_pred_contribs",
                "outputSpace": "raw_margin", "explainedClass": predicted,
                "explainedClassIndex": index, "baseValue": 0.29, "rawModelMargin": 6.1,
                "topSupportingFeatures": [{"featureName": "Dst Port",
                                           "featureValue": float(entry["Dst Port"]),
                                           "shapContribution": 1.2,
                                           "direction": "supports_prediction"}],
                "topOpposingFeatures": [],
                "additivityCheck": {"passed": True, "difference": 1e-6, "tolerance": 1e-4},
            },
        }
    path.write_text(json.dumps(records), encoding="utf-8")
    return path
