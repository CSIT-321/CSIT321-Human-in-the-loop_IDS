"""Signature rule matching — a Python port of ``stage-2/core/signature-engine.js``.

The port covers what the signature layer needs: loading the legacy rules and flow records, the
comparison primitives, and the analyst-facing condition strings. ``signature-output.sample.json``
is the golden reference for all three. The alert-decorating and summarising half of the JS module
(``applySignatures``, ``summariseSignatureResults``, the plain explanations) is not ported here —
scoring and evidence classification belong to later plan steps, and those functions read ground
truth, which this module must never touch (see ``packages/contracts/models.py`` LEAKAGE_FIELDS).

Deliberate divergences from the JavaScript engine, each also marked ``DIVERGENCE:`` at the site:

* A numeric comparison whose *actual* value is not a finite number fails the clause. JS coerces
  with ``Number()``, gets ``NaN``, and every ``<``/``>`` test against ``NaN`` is false — so a flow
  whose feature is text silently satisfies a ``min``/``max`` clause instead of failing it.
* ``oneOf`` compares numbers numerically, so the flow feature ``"80"`` matches the rule value
  ``80``. JS uses ``Array.prototype.includes``, which is strict, so it would not.
* ``load_flow_csv`` accepts plain decimal notation only. JS ``Number()`` additionally accepts
  ``0x1f``/``0o17``/``0b101``/``Infinity``; both engines reject ``1_000``. Tokens outside decimal
  notation stay strings here rather than becoming non-finite floats, which the contracts refuse.
* A blank CSV line is skipped instead of being materialised as an all-blank record, which is what
  JS's ``split``/``reduce`` pair would produce.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any

from packages.contracts.models import (
    ConditionValue,
    MatchedCondition,
    OneOfCondition,
    RangeCondition,
    SignatureMatch,
    SignatureRule,
)

__all__ = [
    "FIELD_LABELS",
    "FIELD_UNITS",
    "condition_holds",
    "format_number",
    "load_flow_csv",
    "load_legacy_rules",
    "match_all",
    "match_rule",
    "readable_condition",
    "readable_conditions",
    "readable_field_name",
]

# JS ``loadCsvFile`` treats a token as a number whenever ``Number(token)`` is not NaN. Plain
# decimal notation keeps that behaviour without importing float()'s extra spellings.
_DECIMAL_TEXT = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_CAMEL_BOUNDARY = re.compile(r"([A-Z])")
_CONDITION_QUANTUM = Decimal("0.001")

# ``getValueByPath`` returns undefined for a missing key, which ``matchCondition`` then fails on. A
# present-but-null field is *not* missing in JS, so the sentinel must not be None.
_MISSING = object()


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def load_legacy_rules(path: str | Path) -> list[SignatureRule]:
    """Convert the frozen legacy rule fixture into ``SignatureRule`` contracts, in file order."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rules: list[SignatureRule] = []
    for entry in raw:
        rationale = entry.get("rationale")
        rules.append(
            SignatureRule(
                rule_id=entry["id"],
                name=entry["name"],
                severity=entry["severity"],
                attack_category=entry["predictedAttackType"],
                conditions=entry["condition"],
                rationale=" ".join(rationale) if isinstance(rationale, list) else rationale,
                version="legacy",
                enabled=True,
            )
        )
    return rules


def _coerce_csv_value(value: str) -> Any:
    """JS ``Number(token)``: a numeric token stays a number, everything else stays text."""
    if value == "" or not _DECIMAL_TEXT.match(value):
        return value
    number = float(value)
    return int(number) if number.is_integer() else number


def load_flow_csv(path: str | Path) -> list[dict[str, Any]]:
    """Port of ``loadCsvFile``: header-driven records with numerically-parsed values."""
    records: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            return records
        for row in reader:
            if not row:
                continue
            records.append({
                header: _coerce_csv_value(row[index] if index < len(row) else "")
                for index, header in enumerate(headers)
            })
    return records


# --------------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------------


def _normalize(value: Any) -> Any:
    """Port of ``normalizeValue``: strings fold to trimmed lower case, everything else is as-is."""
    return value.strip().lower() if isinstance(value, str) else value


def _finite_float(value: Any) -> float | None:
    """``Number(value)`` restricted to finite results; None stands in for JS's ``NaN``."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _get_by_path(source: Any, field_path: str) -> Any:
    """Port of ``getValueByPath``; ``_MISSING`` stands in for JS's ``undefined``."""
    value = source
    for key in field_path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return _MISSING
        value = value[key]
    return value


def _condition_dict(expected: Any) -> Mapping[str, Any] | None:
    """View a contract condition as the object literal ``compareValue``/``formatCondition`` see."""
    if isinstance(expected, OneOfCondition):
        return {"oneOf": list(expected.one_of)}
    if isinstance(expected, RangeCondition):
        return {
            key: value
            for key, value in (("min", expected.min), ("max", expected.max))
            if value is not None
        }
    if isinstance(expected, Mapping):
        return expected
    return None


def _membership_holds(actual: Any, options: Iterable[Any]) -> bool:
    """Normalised ``oneOf`` membership. Numbers compare numerically, text case-insensitively."""
    actual_number = _finite_float(actual)
    for option in options:
        option_number = _finite_float(option)
        if actual_number is not None and option_number is not None:
            if actual_number == option_number:
                return True
            continue
        if _normalize(actual) == _normalize(option):
            return True
    return False


def _boxed_holds(actual: Any, expected: Mapping[str, Any]) -> bool:
    """The ``{equals, min, max, oneOf}`` branch of ``compareValue``."""
    if "equals" in expected and _normalize(actual) != _normalize(expected["equals"]):
        return False

    # DIVERGENCE: JS tests ``NaN < min`` / ``NaN > max``, both of which are false, so a non-numeric
    # actual passes a range clause. Non-convertible actuals fail the clause here instead.
    if "min" in expected:
        actual_number = _finite_float(actual)
        minimum = _finite_float(expected["min"])
        if actual_number is None or minimum is None or actual_number < minimum:
            return False

    if "max" in expected:
        actual_number = _finite_float(actual)
        maximum = _finite_float(expected["max"])
        if actual_number is None or maximum is None or actual_number > maximum:
            return False

    if "oneOf" in expected:
        return _membership_holds(actual, expected["oneOf"])

    return True


def condition_holds(actual: Any, expected: ConditionValue) -> bool:
    """Port of ``compareValue``: does one observed flow feature satisfy one rule clause?"""
    boxed = _condition_dict(expected)
    if boxed is not None:
        return _boxed_holds(actual, boxed)

    if isinstance(expected, str):
        return _normalize(actual) == _normalize(expected)

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        actual_number = _finite_float(actual)
        return actual_number is not None and actual_number == float(expected)

    return actual == expected


# --------------------------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------------------------


def match_rule(record: Mapping[str, Any], rule: SignatureRule) -> SignatureMatch | None:
    """Port of ``matchCondition``: every clause must hold; None means it did not fire."""
    matched: list[MatchedCondition] = []
    for field, clause in rule.conditions.items():
        observed = _get_by_path(record, field)
        if observed is _MISSING:
            # JS: ``actualValue === undefined`` fails the whole condition.
            return None
        if not condition_holds(observed, clause):
            return None
        matched.append(MatchedCondition(feature=field, expected=clause, observed=observed))

    return SignatureMatch(
        rule_id=rule.rule_id,
        version=rule.version,
        name=rule.name,
        attack_category=rule.attack_category,
        severity=rule.severity,
        matched_conditions=matched,
    )


def match_all(record: Mapping[str, Any], rules: Iterable[SignatureRule]) -> list[SignatureMatch]:
    """Every enabled rule that fires, in the order given.

    The JS engine stops at the first hit (``signatureRules.find``); ``match_all(record, rules)[0]``
    is that same match.
    """
    return [
        match
        for match in (match_rule(record, rule) for rule in rules if rule.enabled)
        if match is not None
    ]


# --------------------------------------------------------------------------------------------
# Readable formatting
# --------------------------------------------------------------------------------------------

FIELD_LABELS: dict[str, str] = {
    "protocol": "Protocol",
    "destinationPort": "Destination port",
    "sourcePort": "Source port",
    "flowPacketsPerSecond": "Flow packets per second",
    "flowBytesPerSecond": "Flow bytes per second",
    "totalFwdPackets": "Total forward packets",
    "totalBwdPackets": "Total backward packets",
    "packetLengthMean": "Mean packet length",
    "fwdPacketLengthMean": "Forward packet mean length",
    "flowDuration": "Flow duration",
}

FIELD_UNITS: dict[str, str] = {
    "packetLengthMean": "bytes",
    "fwdPacketLengthMean": "bytes",
    "flowDuration": "microseconds",
}


def format_number(value: Any) -> str:
    """``Number(value).toLocaleString('en-US')``: comma groups, at most 3 fraction digits.

    ``Intl.NumberFormat`` rounds half away from zero, so this quantises with ``ROUND_HALF_UP``
    rather than Python's round-half-even (0.0625 renders as "0.063", as in JS, not "0.062").
    """
    number = _finite_float(value)
    if number is None:
        return "NaN"
    if math.isinf(number):
        return "∞" if number > 0 else "-∞"
    with localcontext() as context:
        # A double needs at most 309 integer digits plus the three fraction digits.
        context.prec = 400
        rounded = Decimal(number).quantize(_CONDITION_QUANTUM, rounding=ROUND_HALF_UP)
        if rounded == rounded.to_integral_value():
            return f"{int(rounded):,}"
        sign = "-" if rounded < 0 else ""
        whole, _, fraction = format(abs(rounded), "f").partition(".")
        return f"{sign}{int(whole):,}.{fraction.rstrip('0')}"


def readable_field_name(field: str) -> str:
    """Port of ``readableFieldName``: a label, else camelCase split with the first letter raised."""
    label = FIELD_LABELS.get(field)
    if label:
        return label
    text = _CAMEL_BOUNDARY.sub(r" \1", field)
    return text[:1].upper() + text[1:]


def _js_scalar_text(value: Any) -> str:
    """JS template interpolation of a scalar: ``${5000000.0}`` renders as ``5000000``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        text = repr(value)
        return text[:-2] if text.endswith(".0") else text
    return str(value)


def readable_condition(field: str, expected: ConditionValue) -> str:
    """Port of ``formatCondition`` — byte-for-byte equal to the JS strings."""
    label = readable_field_name(field)
    unit = f" {FIELD_UNITS[field]}" if field in FIELD_UNITS else ""

    boxed = _condition_dict(expected)
    if boxed is not None:
        parts: list[str] = []
        if "equals" in boxed:
            parts.append(f"{label} is {_js_scalar_text(boxed['equals'])}")
        if "oneOf" in boxed:
            joined = " or ".join(_js_scalar_text(option) for option in boxed["oneOf"])
            parts.append(f"{label} is {joined}")
        if "min" in boxed:
            parts.append(f"{label} is at least {format_number(boxed['min'])}{unit}")
        if "max" in boxed:
            parts.append(f"{label} is at most {format_number(boxed['max'])}{unit}")
        return "; ".join(parts)

    return f"{label} is {_js_scalar_text(expected)}"


def readable_conditions(rule: SignatureRule) -> list[str]:
    """Port of ``buildMatchedConditionsReadable``: one string per clause, in rule order."""
    return [readable_condition(field, clause) for field, clause in rule.conditions.items()]
