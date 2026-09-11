"""Where flows come from — the ingest seam (plan step S3, built with S9; changelog v1.9).

``FlowSource`` is the only way a flow enters detection. Its one implementation replays a CSV of the
corrected release **in timestamp order**, which is the order a sensor would deliver: the demo
therefore behaves like a live feed without pretending to be one (D7). The post-demo flow exporter
(S17, the GintsEngelen CICFlowMeter fork) becomes a second implementation of this same protocol.

Two rules this module enforces, both learned the hard way:

* **Ground truth never enters a flow.** ``attack_class``, ``is_attempted``, ``Label`` and
  ``Attempted Category`` are dropped here, so no detector can reach them even by accident. The
  contracts refuse them again (``models.LEAKAGE_FIELDS``).
* **Timestamps are parsed as ISO 8601, never day-first.** pandas 3 applies ``dayfirst`` even to ISO
  text and read 1 March as 3 January, which silently reordered a whole experiment (changelog v1.12).

``Flow.features`` holds the release's own values exactly as read, including the ``Infinity`` that
CIC rate features sometimes carry, because the model was trained on those values. ``flow_record``
is where a non-finite number becomes an explicit ``None``, since the stored contract refuses
non-finite floats; the observable view reads such a field as 0, as it always has.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from packages.contracts import models as m
from packages.detection.signature.observable import OBSERVABLE_FIELDS, project_record

#: Ground truth and row identifiers: never part of a flow's features.
NON_FEATURE_COLUMNS = frozenset({
    "alert_id", "id", "attack_class", "is_attempted", "Label", "Attempted Category",
})
#: Columns ``flow_record`` needs on top of the observable view.
FLOW_COLUMNS = ("Src IP", "Dst IP", "Src Port", "Dst Port", "Flow Duration", "Total Fwd Packet",
                "Total Bwd packets", "Total Length of Fwd Packet", "Total Length of Bwd Packet")
MICROSECONDS = 1_000_000


@dataclass(frozen=True)
class Flow:
    """One flow as it arrives: its id in the source dataset, and the release's own columns."""

    source_record_id: str
    features: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FlowSource(Protocol):
    """A source of flows in the order a sensor would deliver them."""

    name: str

    def flows(self) -> Iterator[Flow]:
        ...


def parse_timestamps(values: pd.Series) -> pd.Series:
    """The corrected release writes ISO 8601 (``2018-03-01 12:15:42.329367``): parse it as ISO,
    never day-first (changelog v1.12). Unparseable text raises rather than being guessed at."""
    return pd.to_datetime(values, format="ISO8601")


class CsvReplaySource:
    """Replays a corrected-release CSV in timestamp order.

    The file is read once and sorted, because sensor order is a property of the whole capture, not
    of a chunk. ``limit`` takes the first *n* flows in that order, for a short demo or a test.
    """

    def __init__(self, path: str | Path, *, id_column: str = "alert_id",
                 limit: int | None = None) -> None:
        self.path = Path(path)
        self.id_column = id_column
        self.limit = limit
        self.name = f"csv-replay:{self.path.name}"

    def flows(self) -> Iterator[Flow]:
        frame = pd.read_csv(self.path, low_memory=False)
        missing = [column for column in (self.id_column, "Timestamp", *OBSERVABLE_FIELDS,
                                         *FLOW_COLUMNS) if column not in frame.columns]
        if missing:
            raise KeyError(f"{self.path.name} lacks the columns detection needs: {missing}")
        frame = frame.assign(_when=parse_timestamps(frame["Timestamp"]))
        frame = frame.sort_values(["_when", self.id_column], kind="stable")
        columns = [column for column in frame.columns
                   if column not in NON_FEATURE_COLUMNS and column != "_when"]
        if self.limit is not None:
            frame = frame.head(self.limit)
        for record in frame.to_dict("records"):
            yield Flow(source_record_id=str(record[self.id_column]),
                       features={column: _python(record[column]) for column in columns})


def flow_record(flow: Flow) -> m.FlowRecord:
    """The stored ``flow_data`` row for one flow. Non-finite numbers become an explicit None."""
    features = flow.features
    view = project_record(features)
    return m.FlowRecord(
        src_ip=str(features["Src IP"]),
        dst_ip=str(features["Dst IP"]),
        src_port=_port(features["Src Port"]),
        dst_port=_port(features["Dst Port"]),
        protocol=view["protocol"],
        duration=max(0.0, _number(features["Flow Duration"]) / MICROSECONDS),
        packets=_count(features["Total Fwd Packet"]) + _count(features["Total Bwd packets"]),
        bytes=_count(features["Total Length of Fwd Packet"])
        + _count(features["Total Length of Bwd Packet"]),
        flow_features={name: _finite(value) for name, value in features.items()},
        source_record_id=flow.source_record_id,
    )


def feature_frame(flows: Sequence[Flow], columns: Sequence[str],
                  id_column: str = "id") -> pd.DataFrame:
    """``id`` plus exactly ``columns``, the shape ``ml/inference.py`` validates. Values are the
    release's own, so the model sees what it was trained on."""
    return pd.DataFrame(
        [{id_column: flow.source_record_id,
          **{column: flow.features.get(column) for column in columns}} for flow in flows],
        columns=[id_column, *columns])


def _python(value: Any) -> Any:
    """A pandas/numpy scalar as a plain Python value; NaN and inf are kept as floats."""
    return value.item() if hasattr(value, "item") else value


def _finite(value: Any) -> float | int | str | None:
    if isinstance(value, str) or value is None:
        return value
    number = _number(value)
    if not math.isfinite(number):
        return None
    return int(number) if float(number).is_integer() else number


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _count(value: Any) -> int:
    number = _number(value)
    return 0 if not math.isfinite(number) else max(0, int(number))


def _port(value: Any) -> int:
    number = _number(value)
    return 0 if not math.isfinite(number) else min(65535, max(0, int(number)))
