"""The observable view must equal the view the S4b thresholds were tuned on."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from packages.contracts.models import LEAKAGE_FIELDS
from packages.detection.signature.observable import (
    OBSERVABLE_FIELDS,
    project_frame,
    project_record,
)

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
DEMO_SAMPLE = PROCESSED / "demo_sample.csv"
TUNED_ON = PROCESSED / "demo_detection_input.csv"


def flow(**overrides) -> dict:
    row = {column: 0 for column in OBSERVABLE_FIELDS}
    row.update({"Protocol": 6, "Src IP": "10.0.0.1", "Dst IP": "10.0.0.2",
                "Timestamp": "14/02/2018 10:00:00"})
    row.update(overrides)
    return row


def same_view(left: dict, right: dict) -> bool:
    if left.keys() != right.keys():
        return False
    for key, value in left.items():
        other = right[key]
        if isinstance(value, str) or isinstance(other, str):
            if str(value) != str(other):
                return False
        elif float(value) != float(other):
            return False
    return True


@pytest.mark.skipif(not (DEMO_SAMPLE.exists() and TUNED_ON.exists()),
                    reason="regenerate with scripts/build_samples.py and build_demo_detection.py")
def test_frame_projection_reproduces_the_tuned_on_view():
    demo = pd.read_csv(DEMO_SAMPLE, low_memory=False)
    expected = pd.read_csv(TUNED_ON, low_memory=False)
    pd.testing.assert_frame_equal(project_frame(demo), expected, check_dtype=False)


@pytest.mark.skipif(not DEMO_SAMPLE.exists(), reason="regenerate with scripts/build_samples.py")
def test_record_projection_agrees_with_frame_projection():
    demo = pd.read_csv(DEMO_SAMPLE, low_memory=False)
    frame = project_frame(demo).drop(columns="id")
    mismatches = [index for index, row in enumerate(demo.to_dict("records"))
                  if not same_view(project_record(row), frame.iloc[index].to_dict())]
    assert mismatches == []


def test_view_carries_no_label_fields():
    folded = {field.casefold() for field in LEAKAGE_FIELDS}
    assert not {column.casefold() for column in OBSERVABLE_FIELDS} & folded
    assert not {field.casefold() for field in OBSERVABLE_FIELDS.values()} & folded


@pytest.mark.parametrize(("raw", "expected"), [
    (float("inf"), 0), (float("-inf"), 0), (float("nan"), 0), (None, 0), ("", 0),
    ("Infinity", 0), ("12.5", 12.5), (3.0, 3),
])
def test_non_finite_and_missing_numbers_become_zero(raw, expected):
    assert project_record(flow(**{"Flow Packets/s": raw}))["flowPacketsPerSecond"] == expected


@pytest.mark.parametrize(("raw", "expected"), [
    (6, "TCP"), (17, "UDP"), (1, "ICMP"), (0, "HOPOPT"), (6.0, "TCP"), (47, "OTHER"),
    ("x", "OTHER"),
])
def test_protocol_numbers_map_to_names(raw, expected):
    assert project_record(flow(Protocol=raw))["protocol"] == expected


def test_missing_observable_column_is_an_error():
    row = flow()
    del row["Dst Port"]
    with pytest.raises(KeyError, match="Dst Port"):
        project_record(row)
