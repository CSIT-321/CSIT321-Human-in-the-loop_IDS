"""Golden and unit tests for the ported signature engine (plan step S5).

The golden test replays ``signature-output.sample.json`` — the frozen JavaScript engine's verdict on
the 1,000-record legacy sample — through ``packages/detection/signature/engine.py``. The unit tests
pin the operator semantics and the readable strings the golden fixture never exercises: it contains
no ``oneOf`` miss, no non-numeric actual, no disabled rule and no multi-rule hit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from packages.contracts import models as m
from packages.detection.signature.engine import (
    condition_holds,
    format_number,
    load_flow_csv,
    load_legacy_rules,
    match_all,
    match_rule,
    readable_condition,
    readable_conditions,
    readable_field_name,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "legacy"
RULES_PATH = FIXTURES / "flow-signatures.json"
RECORDS_PATH = FIXTURES / "flow-feature-sample.csv"
GOLDEN_PATH = FIXTURES / "signature-output.sample.json"

LEGACY_RULE_COUNT = 7
LEGACY_RECORD_COUNT = 1000


def make_rule(
    conditions: dict[str, Any],
    *,
    rule_id: str = "SIG-TEST",
    enabled: bool = True,
    version: str = "test",
) -> m.SignatureRule:
    return m.SignatureRule(
        rule_id=rule_id,
        name=f"{rule_id} rule",
        severity="High",
        attack_category="DoS",
        conditions=conditions,
        enabled=enabled,
        version=version,
    )


# --------------------------------------------------------------------------------------------
# 1. Golden: the port must reproduce the JavaScript engine's output record for record.
# --------------------------------------------------------------------------------------------


def test_golden_engine_output_matches_the_legacy_javascript():
    rules = load_legacy_rules(RULES_PATH)
    records = load_flow_csv(RECORDS_PATH)
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert len(rules) == LEGACY_RULE_COUNT
    assert len(records) == LEGACY_RECORD_COUNT
    assert len(golden) == LEGACY_RECORD_COUNT

    records_by_id = {record["id"]: record for record in records}
    rules_by_id = {rule.rule_id: rule for rule in rules}

    compared = 0
    mismatches: list[tuple[str, str, Any, Any]] = []

    for expected in golden:
        record = records_by_id.get(expected["id"])
        assert record is not None, f"no flow record for golden id {expected['id']}"

        compared += 1
        matches = match_all(record, rules)
        first = matches[0] if matches else None

        # signatureHit == bool(match_all(...)); the JS engine keeps only the first match.
        if bool(matches) != expected["signatureHit"]:
            mismatches.append(
                (expected["id"], "signatureHit", expected["signatureHit"], bool(matches))
            )

        if first is None:
            if expected["matchedConditionsReadable"] != []:
                mismatches.append((
                    expected["id"],
                    "matchedConditionsReadable",
                    expected["matchedConditionsReadable"],
                    [],
                ))
            continue

        if first.rule_id != expected["signatureId"]:
            mismatches.append(
                (expected["id"], "signatureId", expected["signatureId"], first.rule_id)
            )

        readable = readable_conditions(rules_by_id[first.rule_id])
        if readable != expected["matchedConditionsReadable"]:
            mismatches.append((
                expected["id"],
                "matchedConditionsReadable",
                expected["matchedConditionsReadable"],
                readable,
            ))

    assert compared == LEGACY_RECORD_COUNT, (
        f"compared {compared} of {LEGACY_RECORD_COUNT} golden entries — none may be skipped"
    )

    detail = "\n".join(
        f"  {record_id}: {field} expected {expected!r}, got {got!r}"
        for record_id, field, expected, got in mismatches[:5]
    )
    assert not mismatches, (
        f"{len(mismatches)} mismatching fields across {compared} records; "
        f"first mismatching ids: {[mismatch[0] for mismatch in mismatches[:5]]}\n{detail}"
    )


def test_golden_fixture_actually_exercises_hits_and_misses():
    # Guards the test above: a fixture in which no rule ever fired would pass it trivially.
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    hits = [entry for entry in golden if entry["signatureHit"]]

    assert hits, "the golden fixture contains no signature hits"
    assert len(hits) < len(golden), "the golden fixture contains no misses"
    assert all(entry["matchedConditionsReadable"] for entry in hits)
    misses = [entry for entry in golden if not entry["signatureHit"]]
    assert all(entry["matchedConditionsReadable"] == [] for entry in misses)


def test_loaded_legacy_rules_carry_the_contract_mapping():
    rules = load_legacy_rules(RULES_PATH)
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    assert [rule.rule_id for rule in rules] == [entry["id"] for entry in raw]
    for rule, entry in zip(rules, raw, strict=True):
        assert rule.version == "legacy"
        assert rule.enabled is True
        assert rule.attack_category == entry["predictedAttackType"]
        assert rule.severity == entry["severity"]
        assert rule.rationale == " ".join(entry["rationale"])
        assert list(rule.conditions) == list(entry["condition"])


def test_loaded_records_match_the_golden_flow_values():
    records = load_flow_csv(RECORDS_PATH)
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in records}

    for expected in golden:
        record = by_id[expected["id"]]
        for field, value in record.items():
            assert value == expected[field], (expected["id"], field)
        assert isinstance(record["flowDuration"], int)
        assert isinstance(record["protocol"], str)
        assert isinstance(record["timestamp"], str)


# --------------------------------------------------------------------------------------------
# 2. Operators.
# --------------------------------------------------------------------------------------------


def test_string_equality_ignores_case_and_surrounding_space():
    assert condition_holds("TCP", "TCP")
    assert condition_holds("tcp", "TCP")
    assert condition_holds("  Tcp  ", "tcp")
    assert not condition_holds("udp", "TCP")


def test_number_equality():
    assert condition_holds(21, 21)
    assert condition_holds(21.0, 21)
    assert condition_holds("21", 21)  # JS: Number("21") === 21
    assert not condition_holds(22, 21)
    assert not condition_holds("tcp", 21)


@pytest.mark.parametrize(
    ("actual", "holds"),
    [(10, True), (10.5, True), (10_000_000, True), (9.999, False), (0, False)],
)
def test_range_with_min_only(actual, holds):
    assert condition_holds(actual, m.RangeCondition(min=10)) is holds  # min is inclusive


@pytest.mark.parametrize(
    ("actual", "holds"),
    [(5_000_000, True), (0, True), (5_000_001, False), (5_000_000.5, False)],
)
def test_range_with_max_only(actual, holds):
    assert condition_holds(actual, m.RangeCondition(max=5_000_000)) is holds  # max is inclusive


@pytest.mark.parametrize(
    ("actual", "holds"),
    [(650, True), (899, True), (700.5, True), (649, False), (900, False), (0, False)],
)
def test_range_with_min_and_max(actual, holds):
    assert condition_holds(actual, m.RangeCondition(min=650, max=899)) is holds


def test_one_of_with_numbers():
    condition = m.OneOfCondition(oneOf=[80, 443])

    assert condition_holds(80, condition)
    assert condition_holds(443, condition)
    assert condition_holds(443.0, condition)
    assert not condition_holds(8080, condition)
    # DIVERGENCE: JS ``includes`` is strict, so the text "80" would not match the number 80.
    assert condition_holds("80", condition)


def test_one_of_with_strings():
    condition = m.OneOfCondition(oneOf=["TCP", "UDP"])

    assert condition_holds("TCP", condition)
    assert condition_holds("tcp", condition)
    assert condition_holds("  Udp ", condition)
    assert not condition_holds("ICMP", condition)
    assert not condition_holds(6, condition)


def test_rule_with_several_clauses_ands_them():
    rule = make_rule({"protocol": "TCP", "destinationPort": {"oneOf": [80, 443]}})

    assert match_rule({"protocol": "TCP", "destinationPort": 443}, rule) is not None
    assert match_rule({"protocol": "TCP", "destinationPort": 22}, rule) is None
    assert match_rule({"protocol": "UDP", "destinationPort": 443}, rule) is None


def test_missing_field_fails_the_rule():
    rule = make_rule({"protocol": "TCP", "totalFwdPackets": {"min": 10}})

    assert match_rule({"protocol": "TCP"}, rule) is None
    assert match_rule({"protocol": "TCP", "totalFwdPackets": 12}, rule) is not None


def test_non_numeric_actual_fails_a_range():
    # DIVERGENCE from the JS engine: ``Number("unknown") < 10`` is false for NaN, so JS satisfies
    # the clause and fires the rule. The port fails it rather than let text pass a threshold.
    rule = make_rule({"totalFwdPackets": {"min": 10}, "flowDuration": {"max": 5_000_000}})
    record = {"totalFwdPackets": "unknown", "flowDuration": "unknown"}

    assert condition_holds("unknown", m.RangeCondition(min=10)) is False
    assert condition_holds(float("nan"), m.RangeCondition(min=10)) is False
    assert condition_holds(float("inf"), m.RangeCondition(max=5_000_000)) is False
    assert match_rule(record, rule) is None


def test_matched_conditions_carry_the_observed_record_value():
    rule = make_rule({"protocol": "TCP", "flowDuration": {"max": 5_000_000}})
    record = {"protocol": "tcp", "flowDuration": 1_234_567}

    match = match_rule(record, rule)

    assert match is not None
    assert [condition.feature for condition in match.matched_conditions] == [
        "protocol",
        "flowDuration",
    ]
    assert match.matched_conditions[0].observed == "tcp"
    assert isinstance(match.matched_conditions[0].observed, str)
    assert match.matched_conditions[1].observed == 1_234_567
    assert isinstance(match.matched_conditions[1].observed, int)
    assert match.matched_conditions[1].expected == m.RangeCondition(max=5_000_000)


def test_match_carries_the_rule_identity():
    rule = make_rule({"protocol": "TCP"}, rule_id="SIG-IDENTITY", version="legacy")

    match = match_rule({"protocol": "TCP"}, rule)

    assert match is not None
    assert (match.rule_id, match.version, match.name) == (rule.rule_id, "legacy", rule.name)
    assert match.attack_category == rule.attack_category
    assert match.severity == rule.severity


def test_disabled_rules_are_skipped():
    enabled = make_rule({"protocol": "TCP"}, rule_id="SIG-ENABLED")
    disabled = make_rule({"protocol": "TCP"}, rule_id="SIG-DISABLED", enabled=False)

    assert [match.rule_id for match in match_all({"protocol": "TCP"}, [disabled, enabled])] == [
        "SIG-ENABLED"
    ]
    assert match_all({"protocol": "TCP"}, [disabled]) == []


def test_match_all_returns_every_match_in_rule_order():
    first = make_rule({"protocol": "TCP"}, rule_id="SIG-FIRST")
    second = make_rule({"protocol": "TCP", "destinationPort": 22}, rule_id="SIG-SECOND")
    unrelated = make_rule({"protocol": "UDP"}, rule_id="SIG-UNRELATED")
    record = {"protocol": "TCP", "destinationPort": 22}

    matches = match_all(record, [first, second, unrelated])

    assert [match.rule_id for match in matches] == ["SIG-FIRST", "SIG-SECOND"]
    # The JS engine's find() keeps only the first; the port must agree on which one that is.
    assert matches[0] == match_rule(record, first)
    assert match_all(record, []) == []


# --------------------------------------------------------------------------------------------
# 3. Readable conditions.
# --------------------------------------------------------------------------------------------


def test_readable_condition_for_a_bounded_duration():
    assert readable_condition("flowDuration", m.RangeCondition(max=5_000_000)) == (
        "Flow duration is at most 5,000,000 microseconds"
    )
    assert readable_condition("flowDuration", {"max": 5_000_000}) == (
        "Flow duration is at most 5,000,000 microseconds"
    )


def test_readable_condition_with_a_float_threshold():
    assert readable_condition("flowDuration", {"min": 10.67}) == (
        "Flow duration is at least 10.67 microseconds"
    )
    assert readable_condition("flowPacketsPerSecond", {"min": 0.5, "max": 12.345}) == (
        "Flow packets per second is at least 0.5; Flow packets per second is at most 12.345"
    )


def test_readable_condition_with_an_integer_valued_float_threshold():
    # Range bounds are contract floats; both spellings must render without a ".0".
    assert readable_condition("flowDuration", m.RangeCondition(max=5_000_000.0)) == (
        "Flow duration is at most 5,000,000 microseconds"
    )
    assert readable_condition("flowPacketsPerSecond", {"min": 10.0}) == (
        "Flow packets per second is at least 10"
    )


def test_readable_condition_falls_back_to_camel_case_for_an_unlabelled_field():
    assert readable_field_name("synFlagCount") == "Syn Flag Count"
    assert readable_condition("synFlagCount", 1) == "Syn Flag Count is 1"
    assert readable_condition("totalFwdPackets", {"min": 10}) == (
        "Total forward packets is at least 10"
    )


def test_readable_condition_for_scalars_and_one_of():
    assert readable_condition("destinationPort", 21) == "Destination port is 21"
    assert readable_condition("protocol", "TCP") == "Protocol is TCP"
    assert readable_condition("destinationPort", m.OneOfCondition(oneOf=[80, 443])) == (
        "Destination port is 80 or 443"
    )
    assert readable_condition("packetLengthMean", {"min": 300}) == (
        "Mean packet length is at least 300 bytes"
    )


def test_readable_conditions_returns_one_string_per_clause_in_order():
    rule = make_rule({
        "protocol": "TCP",
        "destinationPort": {"oneOf": [80, 443]},
        "flowDuration": {"max": 5_000_000},
    })

    assert readable_conditions(rule) == [
        "Protocol is TCP",
        "Destination port is 80 or 443",
        "Flow duration is at most 5,000,000 microseconds",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5_000_000, "5,000,000"),
        (10.67, "10.67"),
        (1.0, "1"),
        (0, "0"),
        (0.0625, "0.063"),
        (1_234_567.8919, "1,234,567.892"),
        (-5_000_000, "-5,000,000"),
    ],
)
def test_format_number_matches_javascript_to_locale_string(value, expected):
    # ``.toLocaleString('en-US')``: comma groups, at most 3 fraction digits, half away from zero.
    assert format_number(value) == expected
