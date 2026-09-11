"""The attack-type severity chart (decision Q27) — configuration, not code.

The values live in ``config/severity-chart.json`` so they can be changed without touching code. The
chart is versioned, validated on every load, and its version is recorded with every experiment run.
Bands are derived from the number on the CVSS v3.1 qualitative scale (FIRST specification, §5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from pydantic import Field, model_validator

from packages.contracts import models as m

DEFAULT_CHART = Path(__file__).resolve().parents[3] / "config" / "severity-chart.json"
CVSS_BANDS = ((0.0, "None"), (0.1, "Low"), (4.0, "Medium"), (7.0, "High"), (9.0, "Critical"))


def band(severity: float) -> str:
    """The CVSS v3.1 qualitative band for a 0-10 severity."""
    label = "None"
    for lower, name in CVSS_BANDS:
        if severity >= lower:
            label = name
    return label


class SeverityEntry(m.Contract):
    attack_type: str = Field(min_length=1)
    model_class: m.AttackClass | None = None
    attack_tactic: str | None = None
    suricata_classtypes: list[str] = Field(default_factory=list)
    severity: float = Field(ge=0, le=10)

    @property
    def weight(self) -> float:
        return self.severity / 10

    @property
    def band(self) -> str:
        return band(self.severity)


class SeverityChart(m.Contract):
    version: str = Field(min_length=1)
    scale: str | None = None
    approved: str | None = None
    sources: dict[str, str] = Field(default_factory=dict)
    entries: list[SeverityEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _covers_every_model_class_once(self) -> SeverityChart:
        classes = [entry.model_class for entry in self.entries if entry.model_class is not None]
        missing = set(get_args(m.AttackClass)) - set(classes)
        repeated = sorted({c for c in classes if classes.count(c) > 1})
        if missing:
            raise ValueError(f"severity chart lacks the model classes {sorted(missing)}")
        if repeated:
            raise ValueError(f"severity chart lists model classes more than once: {repeated}")
        return self

    def entry(self, attack_class: str) -> SeverityEntry:
        for entry in self.entries:
            if entry.model_class == attack_class:
                return entry
        raise KeyError(attack_class)

    def severity(self, attack_class: str | None) -> float:
        return 0.0 if attack_class is None else self.entry(attack_class).severity

    def weight(self, attack_class: str | None) -> float:
        """w = severity / 10 for one of the model's classes; 0 when there is no class."""
        return self.severity(attack_class) / 10


def load_severity_chart(path: Path = DEFAULT_CHART) -> SeverityChart:
    return SeverityChart.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
