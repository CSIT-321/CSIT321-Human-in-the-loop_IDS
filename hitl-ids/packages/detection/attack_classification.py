"""Explicit versioned text mappings, not a verdict or probabilistic inference."""
from pathlib import Path
import re
from typing import Literal
from pydantic import Field, model_validator
from packages.contracts.operational_v2 import V2Contract
from packages.contracts.suricata_bundle import AttackCategory, AttackClassification, SuricataEvidenceBundle

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / 'config/suricata-classification-v1.json'


class ClassificationRule(V2Contract):
    id: str = Field(min_length=1)
    category: AttackCategory
    pattern: str = Field(min_length=1)


class ClassificationPolicy(V2Contract):
    version: str = Field(min_length=1)
    conflict_policy: Literal['unknown_needs_expert']
    rules: tuple[ClassificationRule, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def valid_rules(self):
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError('classification rule ids must be unique')
        for rule in self.rules:
            re.compile(rule.pattern, re.IGNORECASE)
            if rule.category == 'unknown_needs_expert':
                raise ValueError('unknown is a fallback, not a known mapping')
        return self


def load_classification_policy(path=DEFAULT_POLICY):
    return ClassificationPolicy.model_validate_json(path.read_text(encoding='utf-8'))


def classify(bundle: SuricataEvidenceBundle, policy: ClassificationPolicy | None = None):
    policy = ClassificationPolicy.model_validate((policy or load_classification_policy()).model_dump())
    categories, reasons = set(), []
    for signature in bundle.related_signatures:
        for rule in policy.rules:
            for field, value in (('signature', signature.signature), ('native category', signature.native_category)):
                if re.search(rule.pattern, value, re.IGNORECASE):
                    categories.add(rule.category)
                    reasons.append(f'Rule {rule.id}: signature {signature.signature_id} {field} maps to {rule.category}.')
    if len(categories) == 1:
        category, status = next(iter(categories)), 'mapped'
    elif categories:
        category, status = 'unknown_needs_expert', 'conflict'
        reasons.append('Conflicting supported classes: ' + ', '.join(sorted(categories)) + '; expert review required.')
    else:
        category, status = 'unknown_needs_expert', 'unmapped'
        reasons.append('No explicit mapping resolves the attack class from the supplied signatures and native categories.')
    return AttackClassification(attack_category=category, status=status, reasons=tuple(reasons), policy_version=policy.version)
