"""Prospective authenticated facts. Server owns actor, recording and availability timestamps."""
from uuid import UUID, uuid4
from pydantic import AwareDatetime, Field, field_validator
from packages.contracts import db, models as m
from packages.contracts.operational_v2 import V2Contract
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.trusted_context import FactValue, TrustedContextFact, load_context_policy, resolve_context


class FactConflict(ValueError): pass


class FactRequest(FactValue):
    request_id: UUID
    expected_revision: int = Field(strict=True,ge=0)
    observed_at: AwareDatetime
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    reason: str = Field(min_length=1,max_length=4000)
    source_reference: str = Field(min_length=1,max_length=500)

    @field_validator('reason','source_reference')
    @classmethod
    def not_blank(cls,value):
        if not value.strip(): raise ValueError('explicit reason and source reference required')
        return value.strip()


class FactPage(V2Contract):
    items: list[TrustedContextFact]
    revision: int
    total: int
    limit: int
    offset: int


class FactMutation(V2Contract):
    fact: TrustedContextFact
    revision: int
    replayed: bool


def read_facts(conn):
    return [TrustedContextFact.model_validate_json(r['snapshot']).model_copy(update={'id':r['id']})
        for r in conn.execute('SELECT id,snapshot FROM trusted_context_facts ORDER BY id')]


def revision(conn):
    return conn.execute('SELECT coalesce(max(id),0) FROM trusted_context_facts').fetchone()[0]


def fact_page(conn,limit=50,offset=0):
    facts=read_facts(conn)
    return FactPage(items=list(reversed(facts))[offset:offset+limit],revision=revision(conn),total=len(facts),limit=limit,offset=offset)


def resolved_for(conn,ref,at=None):
    row=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(ref),)).fetchone()
    if row is None: raise LookupError('Operational alert not found')
    return resolve_context(read_projection(conn,row[0]),read_facts(conn),at or m.utc_now())


def _insert(conn,fact,request_id,payload):
    cursor=conn.execute('INSERT INTO trusted_context_facts (fact_ref,actor_id,request_id,request_payload,snapshot) VALUES (?,?,?,?,?)',
        (str(fact.fact_ref),fact.created_by_actor_id,str(request_id),payload,fact.model_dump_json(by_alias=True)))
    return fact.model_copy(update={'id':cursor.lastrowid})


def collect_fact(conn,*,actor_id,request:FactRequest):
    request=FactRequest.model_validate(request.model_dump())
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]: raise ValueError('foreign keys and no existing transaction required')
    payload=request.model_dump_json(by_alias=True)
    conn.execute('BEGIN IMMEDIATE')
    try:
        actor=db.get(conn,m.User,actor_id)
        if actor is None or actor.status!='active' or actor.role not in ('security_analyst','system_admin'):
            raise PermissionError('active analyst or administrator required')
        retry=conn.execute('SELECT * FROM trusted_context_facts WHERE request_id=?',(str(request.request_id),)).fetchone()
        if retry:
            if retry['actor_id']!=actor_id or retry['request_payload']!=payload: raise FactConflict('requestId belongs to another fact')
            fact=TrustedContextFact.model_validate_json(retry['snapshot']).model_copy(update={'id':retry['id']})
            result=FactMutation(fact=fact,revision=revision(conn),replayed=True)
            conn.commit(); return result
        if revision(conn)!=request.expected_revision: raise FactConflict('fact history changed; refresh its revision')
        now=m.utc_now()
        if request.observed_at>now or request.expires_at<=now or request.expires_at<=request.valid_from:
            raise ValueError('observation cannot be future; validity must be nonempty and unexpired')
        if request.subject_type in ('operational_alert','case'):
            table,column=('operational_alerts_v2','operational_alert_ref') if request.subject_type=='operational_alert' else ('tier2_cases','case_ref')
            if not conn.execute(f'SELECT 1 FROM {table} WHERE {column}=?',(request.subject_value,)).fetchone():
                raise LookupError('fact subject does not exist')
        fact=TrustedContextFact(**request.model_dump(include=set(FactValue.model_fields)),fact_ref=uuid4(),
            source_type='analyst_assessment',source_reference=request.source_reference,observed_at=request.observed_at,
            available_at=now,recorded_at=now,valid_from=request.valid_from,expires_at=request.expires_at,
            created_by_actor_id=actor_id,reason=request.reason,source_snapshot={'structuredAssessment':request.model_dump(mode='json',by_alias=True)},
            freshness_policy=load_context_policy())
        for prior in read_facts(conn):
            if prior.freshness_policy.version==fact.freshness_policy.version and prior.freshness_policy!=fact.freshness_policy:
                raise FactConflict('changed freshness configuration requires a new version')
        fact=_insert(conn,fact,request.request_id,payload)
        result=FactMutation(fact=fact,revision=revision(conn),replayed=False)
        conn.commit(); return result
    except Exception:
        conn.rollback(); raise


def seed_synthetic_facts(conn,alert,context,at):
    """Controlled disposable fixture helper only. No endpoint or production startup calls this."""
    from packages.detection.trusted_context import fixture_facts
    with conn:
        for fact in fixture_facts(alert,context,at):
            _insert(conn,fact,fact.fact_ref,'{"synthetic":true}')
