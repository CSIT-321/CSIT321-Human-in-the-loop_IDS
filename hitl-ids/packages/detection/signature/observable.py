"""The observable view — the only flow fields a signature rule may test (plan step S5).

Rules are written against these camelCase fields, not the corrected release's column names. The S4b
thresholds were tuned and validated in exactly this view (``scripts/build_demo_detection.py``
wrote it as ``demo_detection_input.csv``), so the tuned rules are used verbatim; translating them
to CIC names would re-open figures that are already verified.

The projection is defined once, here, and must stay equivalent to ``build_demo_detection.py``;
``tests/test_observable.py`` pins it to the file S4b was tuned on. Label fields are not part of
the view.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

# corrected-release column -> observable field
OBSERVABLE_FIELDS: dict[str, str] = {
    "Dst Port": "destinationPort",
    "Protocol": "protocol",
    "Flow Duration": "flowDuration",
    "Total Fwd Packet": "totalFwdPackets",
    "Total Bwd packets": "totalBwdPackets",
    "Flow Bytes/s": "flowBytesPerSecond",
    "Flow Packets/s": "flowPacketsPerSecond",
    "Packet Length Mean": "packetLengthMean",
    "Fwd Packet Length Mean": "fwdPacketLengthMean",
    "SYN Flag Count": "synFlagCount",
    "ACK Flag Count": "ackFlagCount",
    "FIN Flag Count": "finFlagCount",
    "RST Flag Count": "rstFlagCount",
    "Src IP": "sourceIp",
    "Dst IP": "destinationIp",
    "Timestamp": "timestamp",
}
PROTOCOL_NAMES = {6: "TCP", 17: "UDP", 1: "ICMP", 0: "HOPOPT"}
UNKNOWN_PROTOCOL = "OTHER"
TEXT_FIELDS = frozenset({"protocol", "sourceIp", "destinationIp", "timestamp"})


def project_frame(frame: pd.DataFrame, id_column: str = "alert_id") -> pd.DataFrame:
    """Project corrected-release rows to the observable view, vectorised. Column ``id`` first."""
    missing = [column for column in OBSERVABLE_FIELDS if column not in frame.columns]
    if missing:
        raise KeyError(f"flow rows lack observable columns {missing}")
    view = pd.DataFrame({"id": frame[id_column]})
    for source, field in OBSERVABLE_FIELDS.items():
        view[field] = frame[source]
    view["protocol"] = (pd.to_numeric(view["protocol"], errors="coerce")
                        .map(PROTOCOL_NAMES).fillna(UNKNOWN_PROTOCOL))
    for field in view.columns:
        if field != "id" and field not in TEXT_FIELDS:
            view[field] = (pd.to_numeric(view[field], errors="coerce")
                           .replace([np.inf, -np.inf], np.nan).fillna(0))
    return view


def project_record(features: Mapping[str, Any]) -> dict[str, Any]:
    """Project one corrected-release flow (e.g. ``FlowRecord.flow_features``) to the view."""
    missing = [column for column in OBSERVABLE_FIELDS if column not in features]
    if missing:
        raise KeyError(f"flow lacks observable columns {missing}")
    view: dict[str, Any] = {}
    for source, field in OBSERVABLE_FIELDS.items():
        value = features[source]
        if field == "protocol":
            view[field] = _protocol_name(value)
        elif field in TEXT_FIELDS:
            view[field] = value
        else:
            view[field] = _finite_number(value)
    return view


def _finite_number(value: Any) -> int | float:
    # Missing, non-numeric and infinite values become 0, exactly as the tuned-on view did.
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return int(number) if number.is_integer() else number


def _protocol_name(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return UNKNOWN_PROTOCOL
    if not number.is_integer():
        return UNKNOWN_PROTOCOL
    return PROTOCOL_NAMES.get(int(number), UNKNOWN_PROTOCOL)
