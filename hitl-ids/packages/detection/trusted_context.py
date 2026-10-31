"""Typed, scoped safety facts and a pure historical resolver. No external enrichment."""
from datetime import timedelta
from ipaddress import ip_address
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import AwareDatetime, Field, model_validator, field_validator
from packages.contracts.operational_v2 import V2Contract
from packages.detection.triage_policy import TriageContext

ContextKey = Literal['assetCriticality','knownMaliciousIndicator','responseRequired','confirmedMalicious',
    'evidenceConflict','repeatedCampaign','correlatedAlertCount','analystEscalated','unresolvedByTier1']
SubjectType = Literal['asset','ip','operational_alert','case']
SourceType = Literal['asset_inventory','threat_intelligence','analyst_assessment','detector_context',
    'case_context','approved_registry','synthetic_fixture']
KEYS = tuple(TriageContext.model_json_schema(by_alias=True)['properties'])


class ContextPolicy(V2Contract):
    version: str = Field(min_length=1)
    maximum_age_hours: dict[str, int]

    @model_validator(mode='after')
    def complete(self):
        if set(self.maximum_age_hours)!=set(KEYS) or any(type(v) is not int or not 1<=v<=8760 for v in self.maximum_age_hours.values()):
            raise ValueError('each supported context key requires an explicit bounded freshness limit')
        return self


def load_context_policy():
    return ContextPolicy.model_validate_json((Path(__file__).resolve().parents[2]/'config/context-provenance-v1.json').read_text(encoding='utf-8'))


class FactValue(V2Contract):
    subject_type: SubjectType
    subject_value: str = Field(min_length=1, max_length=200)
    context_key: ContextKey
    value: bool | int | str | None

    @field_validator('value',mode='before')
    @classmethod
    def no_coercion(cls,value):
        if value is not None and type(value) not in (bool,int,str): raise ValueError('explicit typed value required')
        return value

    @field_validator('subject_value')
    @classmethod
    def canonical_subject(cls,value,info):
        if not value.strip(): raise ValueError('explicit subject required')
        if info.data.get('subject_type') in ('operational_alert','case'): return str(UUID(value))
        if info.data.get('subject_type')=='ip': return str(ip_address(value))
        return value

    @model_validator(mode='after')
    def typed_value(self):
        if not self.subject_value.strip(): raise ValueError('explicit subject required')
        if self.value is not None:
            valid=(self.value in ('low','medium','high','critical') and type(self.value) is str) if self.context_key=='assetCriticality' else (
                type(self.value) is int and self.value>=0 if self.context_key=='correlatedAlertCount' else type(self.value) is bool)
            if not valid: raise ValueError('structured value does not match context key; unknown is null, never false')
        return self


class TrustedContextFact(FactValue):
    id: int | None = None
    fact_ref: UUID
    source_type: SourceType
    source_reference: str = Field(min_length=1, max_length=500)
    observed_at: AwareDatetime
    available_at: AwareDatetime
    valid_from: AwareDatetime
    expires_at: AwareDatetime | None
    recorded_at: AwareDatetime
    confidence_basis: str | None = None
    created_by_actor_id: int | None
    reason: str = Field(min_length=1, max_length=4000)
    source_snapshot: dict[str, Any]
    status: Literal['active','withdrawn'] = 'active'
    freshness_policy: ContextPolicy

    @model_validator(mode='after')
    def temporal_provenance(self):
        if not self.source_reference.strip() or not self.reason.strip() or not self.source_snapshot:
            raise ValueError('source reference, source snapshot and reason are required')
        if not self.observed_at<=self.available_at or self.recorded_at>self.available_at:
            raise ValueError('availability cannot precede observation or system recording')
        if self.expires_at is not None and self.expires_at<=self.valid_from:
            raise ValueError('expiry must follow validity start')
        if self.source_type=='analyst_assessment' and (self.created_by_actor_id is None or self.expires_at is None):
            raise ValueError('analyst assessment requires actor and explicit validity window')
        return self


class ResolvedField(V2Contract):
    context_key: ContextKey
    value: bool | int | str | None
    status: Literal['trusted','unknown','expired','conflict','not_applicable']
    facts: list[TrustedContextFact]
    available_at: AwareDatetime | None
    expires_at: AwareDatetime | None
    explanation: str


class ResolvedTrustedContext(V2Contract):
    operational_alert_ref: UUID
    evaluated_at: AwareDatetime
    resolver_version: Literal['context-resolver-v1'] = 'context-resolver-v1'
    fields: list[ResolvedField]
    context: TriageContext
    complete: bool


def effective_expiry(fact):
    maximum=fact.observed_at+timedelta(hours=fact.freshness_policy.maximum_age_hours[fact.context_key])
    return min(maximum,fact.expires_at) if fact.expires_at is not None else maximum


def resolve_context(alert, facts, at):
    if at.tzinfo is None: raise ValueError('aware evaluation time required')
    fields=[]; values={}
    history=[TrustedContextFact.model_validate(f.model_dump()) for f in facts]
    if len({f.fact_ref for f in history})!=len(history): raise ValueError('duplicate fact reference')
    for key in KEYS:
        known=[f for f in history if f.context_key==key and f.available_at<=at and f.recorded_at<=at and f.valid_from<=at]
        applicable=[f for f in known if (f.subject_type=='operational_alert' and f.subject_value==str(alert.operational_alert_ref)) or
            (f.subject_type=='ip' and key=='assetCriticality' and f.subject_value==alert.destination_ip)]
        # New versions replace only their own source stream. Expiry/withdrawal never revives old versions.
        streams={}
        for fact in applicable:
            stream=(fact.subject_type,fact.subject_value,fact.source_type,fact.source_reference,fact.created_by_actor_id)
            streams.setdefault(stream,[]).append(fact)
        latest=[]
        for versions in streams.values():
            newest=max(f.available_at for f in versions)
            latest.extend(f for f in versions if f.available_at==newest)
        latest.sort(key=lambda f:str(f.fact_ref))
        active=[f for f in latest if f.status=='active']
        usable=[f for f in active if at<effective_expiry(f)]
        typed={(type(f.value).__name__,json.dumps(f.value)) for f in usable}
        status='unknown'; value=None
        if len(typed)>1:
            status='conflict'; explanation='Sources disagree; no precedence or safe default is inferred.'
        elif usable and usable[0].value is not None:
            status='trusted'; value=usable[0].value; explanation='Explicit scoped fact(s), historically available and fresh.'
        elif usable:
            explanation='Source explicitly reports unknown; null is not a negative fact.'
        elif active:
            status='expired'; explanation='Latest applicable fact(s) expired; earlier versions are not revived.'
        elif latest:
            explanation='Applicable source stream withdrawn; no safe value is inferred.'
        elif known:
            status='not_applicable'; explanation='No matching subject binding. Asset/case identities and broad IP safety claims are not inferred.'
        else:
            explanation='No fact was available and applicable at this decision time.'
        values[key]=value if status=='trusted' else None
        fields.append(ResolvedField(context_key=key,value=values[key],status=status,facts=latest,
            available_at=min((f.available_at for f in (usable or latest)),default=None),
            expires_at=min((effective_expiry(f) for f in (usable or active)),default=None),explanation=explanation))
    return ResolvedTrustedContext(operational_alert_ref=alert.operational_alert_ref,evaluated_at=at,
        fields=fields,context=TriageContext.model_validate(values),complete=all(f.status=='trusted' for f in fields))


def fixture_facts(alert, context, at):
    """Explicit synthetic producer for disposable tests/evaluation; never called by admission."""
    policy=load_context_policy()
    return [TrustedContextFact(fact_ref=uuid5(NAMESPACE_URL,f'synthetic-context:{alert.operational_alert_ref}:{key}:{at.isoformat()}'),
        subject_type='operational_alert',subject_value=str(alert.operational_alert_ref),context_key=key,value=value,
        source_type='synthetic_fixture',source_reference='disposable-demo:'+str(alert.operational_alert_ref),
        observed_at=at,available_at=at,valid_from=at,expires_at=at+timedelta(hours=4),recorded_at=at,
        created_by_actor_id=None,reason='SYNTHETIC fixture, not production evidence',source_snapshot={'synthetic':True},freshness_policy=policy)
        for key,value in context.model_dump(by_alias=True).items()]
