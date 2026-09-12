"""Ground truth, and the one join that reaches it (plan step S15).

Ground truth is deliberately **not** in the schema: a label column beside the features is a leakage
vector, and the S3 seam drops ``Label``/``attack_class`` before a flow can reach a detector
(``pipeline/source.py``). The evaluation is the only component allowed to know the answers, and it
reaches them by one join and one join only:

    alerts.id -> flow_data.alert_id -> flow_data.source_record_id -> demo_ground_truth.json

Never through a detector's own output. ``attack_category`` is what the system *believes*; the
record here is what the capture *was*. Confusing the two turns recall into a tautology.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

HITL = Path(__file__).resolve().parents[2]
DEFAULT_TRUTH = HITL / "data" / "processed" / "demo_ground_truth.json"

#: The ground-truth file's word for "this flow was an attack".
MALICIOUS = "malicious"


@dataclass(frozen=True)
class TruthRecord:
    """What one source flow actually was."""

    source_record_id: str
    attack_type: str
    is_attempted: bool

    @property
    def malicious(self) -> bool:
        return self.attack_type != "Benign"


class GroundTruth:
    """The capture's answers, keyed by ``flow_data.source_record_id``."""

    def __init__(self, records: dict[str, TruthRecord], *, source: str) -> None:
        self.records = records
        self.source = source

    @classmethod
    def load(cls, path: str | Path = DEFAULT_TRUTH) -> GroundTruth:
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = {
            key: TruthRecord(source_record_id=key, attack_type=str(value["attackType"]),
                             is_attempted=bool(value.get("isAttempted", False)))
            for key, value in raw.items()
        }
        # The file's own `groundTruth` word must agree with the attack type, or one of the two is
        # stale and every metric below would be quietly wrong.
        for key, value in raw.items():
            if (str(value.get("groundTruth")) == MALICIOUS) != records[key].malicious:
                raise ValueError(f"ground truth disagrees with itself for {key}: {value}")
        return cls(records, source=str(path.name))

    def __len__(self) -> int:
        return len(self.records)

    def of(self, source_record_id: str) -> TruthRecord:
        try:
            return self.records[source_record_id]
        except KeyError:
            raise LookupError(
                f"no ground truth for source record {source_record_id!r}; the evaluation refuses "
                f"to score a flow it cannot check") from None

    def malicious(self, source_record_id: str) -> bool:
        return self.of(source_record_id).malicious

    @property
    def classes(self) -> list[str]:
        """Every attack type present, Benign last — the report's row order."""
        found = {record.attack_type for record in self.records.values()}
        return sorted(found - {"Benign"}) + (["Benign"] if "Benign" in found else [])
