"""One severity scale for every queue source (C9, settled decision 8; user decision 2026-11-07).

The Tier 1 queue sorts by severity first, so a severe alert is reached first whatever detector raised it.

- Flow alert: ``alerts.severity``, the detector's label (fusion/cef.py ``severity_for``).
- Suricata alert: the approved severity chart (config/severity-chart.json, decision Q27) gives the band for the
  alert's classtype. EVE carries the classtype *description* in ``alert.category``; config/suricata-classtypes-v1.json
  maps it to the classtype name the chart uses. A classtype the chart does not list falls back to the alert's own
  rule priority: 1 = High, 2 = Medium, 3 = Low, anything else = Informational. Without a chart entry a Suricata alert
  is never Critical: 197,240 of the day's EVE alerts are 'Misc activity', and must not all rank as worst.

Pure. The queue registers ``severity_label`` as an SQLite function, so the read never writes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from packages.detection.fusion.cef import CVSS_TO_SEVERITY
from packages.detection.ranking.severity import band, load_severity_chart

CLASSTYPES = Path(__file__).resolve().parents[2] / "config" / "suricata-classtypes-v1.json"
RANK = {"Informational": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}
PRIORITY_FALLBACK = {1: "High", 2: "Medium", 3: "Low"}


@lru_cache(maxsize=1)
def _chart_band_by_description() -> dict[str, str]:
    by_classtype = {}
    for entry in load_severity_chart().entries:
        for classtype in entry.suricata_classtypes:
            label = CVSS_TO_SEVERITY[band(entry.severity)]
            # A classtype listed twice keeps its worst band.
            if RANK[label] > RANK.get(by_classtype.get(classtype), -1):
                by_classtype[classtype] = label
    table = json.loads(CLASSTYPES.read_text(encoding="utf-8"))
    return {e["description"].casefold(): by_classtype[e["classtype"]]
            for e in table["entries"] if e["classtype"] in by_classtype}


def _priority(native_severity) -> int | None:
    try:
        value = json.loads(native_severity) if isinstance(native_severity, str) else native_severity
        return int(value) if not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def severity_label(source_kind, flow_severity, native_severity, category) -> str:
    if source_kind == "legacy_flow_alert":
        return flow_severity if flow_severity in RANK else "Informational"
    chart = _chart_band_by_description().get((category or "").strip().casefold())
    if chart is not None:
        return chart
    return PRIORITY_FALLBACK.get(_priority(native_severity), "Informational")


def severity_rank(source_kind, flow_severity, native_severity, category) -> int:
    return RANK[severity_label(source_kind, flow_severity, native_severity, category)]
