"""Explicit versioned text mappings, not a verdict or probabilistic inference."""
from pathlib import Path
import re
from typing import Literal
from pydantic import Field, model_validator
from packages.contracts.operational_v2 import V2Contract
from packages.contracts.suricata_bundle import AttackCategory, AttackClassification, ClassificationMatch, SuricataEvidenceBundle

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / 'config/suricata-classification-v2.json'


class ClassificationRule(V2Contract):
    id: str = Field(min_length=1)
    category: AttackCategory
    pattern: str = Field(min_length=1)


class Specificity(V2Contract):
    specific: AttackCategory
    broader: AttackCategory


class InformationalRule(V2Contract):
    id: str = Field(min_length=1)
    signature_pattern: str = Field(min_length=1)
    native_category_pattern: str = Field(min_length=1)


class ClassificationPolicy(V2Contract):
    version: str = Field(min_length=1)
    conflict_policy: Literal['unknown_needs_expert']
    rules: tuple[ClassificationRule, ...] = Field(min_length=1)

    compatibility: tuple[Specificity, ...] = ()
    informational_rules: tuple[InformationalRule, ...] = ()
    informational_attack_veto: str | None = None

    def broader_than(self, category):
        found, pending = set(), [category]
        while pending:
            current = pending.pop()
            for edge in self.compatibility:
                if edge.specific == current and edge.broader not in found:
                    found.add(edge.broader); pending.append(edge.broader)
        return found

    @model_validator(mode='after')
    def valid_rules(self):
        ids = [rule.id for rule in (*self.rules, *self.informational_rules)]
        if len(set(ids)) != len(ids):
            raise ValueError('classification rule ids must be unique')
        for rule in self.rules:
            re.compile(rule.pattern, re.IGNORECASE)
            if rule.category == 'unknown_needs_expert':
                raise ValueError('unknown is a fallback, not a known mapping')
        known = {rule.category for rule in self.rules}
        for edge in self.compatibility:
            if edge.specific not in known or edge.broader not in known or edge.specific in self.broader_than(edge.specific):
                raise ValueError('specificity must be acyclic and reference supported known classes')
        for rule in self.informational_rules:
            re.compile(rule.signature_pattern, re.IGNORECASE)
            re.compile(rule.native_category_pattern, re.IGNORECASE)
        if self.informational_rules and not self.informational_attack_veto:
            raise ValueError('informational rules require an explicit attack-like veto')
        if self.informational_attack_veto:
            re.compile(self.informational_attack_veto, re.IGNORECASE)
        return self


def load_classification_policy(path=DEFAULT_POLICY):
    return ClassificationPolicy.model_validate_json(path.read_text(encoding='utf-8'))


def classify(bundle: SuricataEvidenceBundle, policy: ClassificationPolicy | None = None):
    policy = ClassificationPolicy.model_validate((policy or load_classification_policy()).model_dump())
    categories, reasons, matches, informational = set(), [], [], set()
    for signature in bundle.related_signatures:
        def matched(rule_id, field, value, category):
            matches.append(ClassificationMatch(rule_id=rule_id, source_record_ref=signature.source_record_ref,
                signature_id=signature.signature_id, field=field, value=value, category=category))
            reasons.append(f'Rule {rule_id}: signature {signature.signature_id} {field} maps to {category or "informational/policy signal"}.')
        for rule in policy.rules:
            for field, value in (('signature', signature.signature), ('native category', signature.native_category)):
                if re.search(rule.pattern, value, re.IGNORECASE):
                    categories.add(rule.category); matched(rule.id, field, value, rule.category)
        # The native category must separately full-match an explicit allowlist.
        # Veto attack-like signature text, not the word "Suspicious" inside the
        # explicitly allowed native category "Not Suspicious Traffic".
        veto = policy.informational_attack_veto and re.search(policy.informational_attack_veto,
            signature.signature, re.IGNORECASE)
        for rule in policy.informational_rules:
            if (not veto and re.fullmatch(rule.signature_pattern, signature.signature, re.IGNORECASE)
                    and re.fullmatch(rule.native_category_pattern, signature.native_category, re.IGNORECASE)):
                informational.add(signature.source_record_ref)
                matched(rule.id, 'signature', signature.signature, None)
                matched(rule.id, 'native category', signature.native_category, None)
    winners = [category for category in sorted(categories) if categories - {category} <= policy.broader_than(category)]
    conflicts = ()
    if len(winners) == 1:
        category, status = winners[0], 'mapped'
        if len(categories) > 1:
            reasons.append(f'Configured specificity selects {category} over compatible broader evidence: ' + ', '.join(sorted(categories - {category})) + '. All matches are retained.')
    elif categories:
        category, status = 'unknown_needs_expert', 'conflict'
        conflicts = tuple(sorted(categories))
        reasons.append('Conflicting supported classes: ' + ', '.join(conflicts) + '; expert review required.')
    elif len(informational) == len(bundle.related_signatures):
        category, status = None, 'informational_policy_signal'
        reasons.append('Every alert signature explicitly matches informational/policy rules and passes the attack-like veto. This is not a benign verdict.')
    else:
        category, status = 'unknown_needs_expert', 'unmapped'
        reasons.append('Unresolved evidence: neither a supported attack class nor complete explicit informational/policy identification. Expert review required.')
    return AttackClassification(attack_category=category, status=status, reasons=tuple(reasons),
        policy_version=policy.version, matches=tuple(matches), conflicting_categories=conflicts)
