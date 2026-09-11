"""
Write the tuned signature rule set (plan step S4b) as a versioned, contract-valid file.

Inputs (read-only):
    tests/fixtures/legacy/flow-signatures.json   the 7 original rules (frozen)
    data/processed/retune_results.json           S4b threshold search (plan-changelog v1.3)
Output:
    rules/rule-set-s4b-1.json

The two rules that reached precision >= 0.90 take their full `retuned_condition` - every clause,
not only the tuned one (changelog v1.3 process note: dropping the other clauses once produced a
false rejection). The five that cannot reach it are kept but disabled: retired, not deleted, so
the rule table still records what was tried.

Conditions use the observable view (packages/detection/signature/observable.py), the view the
thresholds were tuned in.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HITL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HITL))

from packages.contracts.models import SignatureRule  # noqa: E402

VERSION = "s4b-1"
LEGACY_RULES = HITL / "tests" / "fixtures" / "legacy" / "flow-signatures.json"
RETUNE_RESULTS = HITL / "data" / "processed" / "retune_results.json"
OUTPUT = HITL / "rules" / f"rule-set-{VERSION}.json"
EXPECTED_ENABLED = {"SIG-FTP-BRUTE-FORCE", "SIG-SSH-BRUTE-FORCE"}  # changelog v1.3


def build() -> dict:
    legacy = json.loads(LEGACY_RULES.read_text(encoding="utf-8"))
    best = json.loads(RETUNE_RESULTS.read_text(encoding="utf-8"))["best_per_rule"]
    rules = []
    for rule in legacy:
        search = best.get(rule["id"], {})
        tuned = bool(search.get("reached_precision_0.90")) and search.get("retuned_condition")
        rationale = rule.get("rationale")
        contract = SignatureRule(
            rule_id=rule["id"],
            name=rule["name"],
            severity=rule["severity"],
            conditions=search["retuned_condition"] if tuned else rule["condition"],
            enabled=bool(tuned),
            version=VERSION,
            attack_category=rule["predictedAttackType"],
            rationale=" ".join(rationale) if isinstance(rationale, list) else rationale,
        )
        # created_at is set when S9 loads the file, so the file itself stays deterministic.
        rules.append(contract.model_dump(mode="json", exclude={"id", "created_at"}))

    enabled = {rule["rule_id"] for rule in rules if rule["enabled"]}
    if enabled != EXPECTED_ENABLED:
        raise SystemExit(f"retune results disagree with changelog v1.3: enabled {sorted(enabled)}")
    return {
        "version": VERSION,
        "view": "observable (packages/detection/signature/observable.py)",
        "matching": "all clauses ANDed; scalar = equality, oneOf = membership, min/max inclusive",
        "source": {"rules": LEGACY_RULES.relative_to(HITL).as_posix(),
                   "tuning": RETUNE_RESULTS.relative_to(HITL).as_posix()},
        "rules": rules,
    }


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(HITL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
