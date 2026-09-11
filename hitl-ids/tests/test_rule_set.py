"""S4b: the tuned rule set is contract-valid, regenerable, and re-measures as reported."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from packages.detection.signature.rule_set import DEFAULT_RULE_SET, load_rule_set

HITL = Path(__file__).resolve().parents[1]
DEMO_SAMPLE = HITL / "data" / "processed" / "demo_sample.csv"
TRAIN_SAMPLE = HITL / "data" / "processed" / "train_sample.csv"
LEGACY_RULES = HITL / "tests" / "fixtures" / "legacy" / "flow-signatures.json"
LIVE_RULES = {"SIG-FTP-BRUTE-FORCE", "SIG-SSH-BRUTE-FORCE"}


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HITL / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rule_set_is_contract_valid_with_two_live_rules():
    rules = load_rule_set()
    assert len(rules) == 7
    assert {rule.rule_id for rule in rules if rule.enabled} == LIVE_RULES
    assert {rule.version for rule in rules} == {"s4b-1"}


def test_rule_set_file_is_regenerated_exactly():
    assert script("write_rule_set").build() == json.loads(DEFAULT_RULE_SET.read_text("utf-8"))


def test_tuning_kept_every_original_clause():
    # changelog v1.3: tuning replaced one threshold; dropping the other clauses once produced
    # a false rejection, so their survival is asserted.
    legacy = {rule["id"]: rule for rule in json.loads(LEGACY_RULES.read_text("utf-8"))}
    for rule in load_rule_set():
        assert set(rule.conditions) == set(legacy[rule.rule_id]["condition"]), rule.rule_id


@pytest.mark.skipif(not DEMO_SAMPLE.exists(), reason="see data/README.md")
def test_demo_sample_reproduces_changelog_v1_3():
    result = script("validate_rule_set").measure(DEMO_SAMPLE, load_rule_set())
    ftp, ssh = result["per_rule"]["SIG-FTP-BRUTE-FORCE"], result["per_rule"]["SIG-SSH-BRUTE-FORCE"]
    assert (ftp["fired"], ftp["class_correct"]) == (146, 146)
    assert (ssh["fired"], ssh["class_correct"]) == (54, 54)
    assert (result["hits"], result["class_correct"], result["benign_hits"]) == (200, 200, 0)
    assert result["recall_class"] == 0.2


@pytest.mark.skipif(not TRAIN_SAMPLE.exists(),
                    reason="136 MB, not in git; regenerate with scripts/build_samples.py")
def test_held_out_sample_reproduces_handover_figures():
    result = script("validate_rule_set").measure(TRAIN_SAMPLE, load_rule_set())
    assert result["hits"] == 30_025
    # HANDOVER §4's figures score a hit correct when the flow is any attack.
    assert result["benign_hits"] == 2
    assert round(result["precision_malicious"], 4) == 0.9999
    assert round(result["recall_malicious"], 4) == 0.1993
    # Scored against the rule's own class, 23 port scans probing TCP/21 are labelled FTP brute
    # force (changelog v1.6).
    assert result["misattributed"] == [
        {"rule_id": "SIG-FTP-BRUTE-FORCE", "true_class": "Port Scan", "flows": 23},
        {"rule_id": "SIG-SSH-BRUTE-FORCE", "true_class": "Benign", "flows": 2},
    ]
    assert round(result["precision_class"], 4) == 0.9992
    assert round(result["recall_class"], 4) == 0.1991
