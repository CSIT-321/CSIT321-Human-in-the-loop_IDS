"""Load a versioned signature rule set written by ``scripts/write_rule_set.py``."""

from __future__ import annotations

import json
from pathlib import Path

from packages.contracts.models import SignatureRule

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"
DEFAULT_RULE_SET = RULES_DIR / "rule-set-s4b-1.json"


def load_rule_set(path: Path = DEFAULT_RULE_SET) -> list[SignatureRule]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [SignatureRule.model_validate(rule) for rule in document["rules"]]
    versions = {rule.version for rule in rules}
    if versions != {document["version"]}:
        raise ValueError(f"{path}: rule versions {sorted(versions)} differ from the set's "
                         f"{document['version']!r}")
    return rules
