"""Organisation-local advisory memory. No detector, triage, case or response writes."""
from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid4
from pydantic import AwareDatetime,Field,field_validator
from packages.contracts import db,models as m
from packages.contracts.operational_v2 import V2Contract,OperationalAlertV2
from packages.detection.adapters.operational_v2 import read_projection,read_triage
from packages.detection.routing import state_version

Outcome=Literal['expected_activity','false_positive','confirmed_malicious','suspicious']
Scope=Literal['exact','narrow']
Status=Literal['candidate','eligible_for_activation','active','conflict_review','expired','rejected']


class MemoryConflict(ValueError):
    pass


class MemoryConfig(V2Contract):
    version: str = Field(min_length=1)
    minimum_support: int = Field(strict=True,ge=3)
    minimum_agreement_ratio: float = Field(ge=0.67,le=1)
    maximum_conflicts: Literal[0]
    default_validity_days: int = Field(strict=True,ge=1,le=365)
    exact_required_fields: list[str]
    narrow_required_fields: list[str]


def load_config():
    path=Path(__file__).resolve().parents[2]/'config/triage-memory-v1.json'
    config=MemoryConfig.model_validate_json(path.read_text(encoding='utf-8'))
    # Configuration may strengthen thresholds, never remove the identity anchors.
    for fields,anchors in ((config.exact_required_fields,{'detectorSource','detectionTitle','sourceIp','destinationIp','protocol'}),
                          (config.narrow_required_fields,{'detectorSource','detectionCategory','sourceIp','protocol'})):
        if not anchors.issubset(fields) or not set(fields).issubset(MemoryContext.model_json_schema(by_alias=True)['properties']):
            raise ValueError('memory scope configuration must retain supported identity anchors')
    return config


class MemoryContext(V2Contract):
    detector_source: str
    detection_title: str
    detection_category: str | None
    source_ip: str
    destination_ip: str
    source_port: int | None
    destination_port: int | None
    protocol: str
    asset_criticality: str | None = None
    asset_identifier: str | None = None
    known_scanner_identity: str | None = None
    authorised_activity_type: str | None = None
    schedule_window: str | None = None
    analyst_defined_tag: str | None = None


def context_for(alert):
    fields=('detector_source','detection_title','detection_category','source_ip','destination_ip','source_port','destination_port','protocol')
    return MemoryContext(**{key:getattr(alert,key) for key in fields})


class MemoryCommand(V2Contract):
    request_id: UUID
    reason: str = Field(min_length=1,max_length=4000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():
            raise ValueError('human-authored reason is required')
        return value.strip()


class MemoryReviewRequest(MemoryCommand):
    outcome: Outcome
    scope: Scope = 'exact'
    expected_state_version: str = Field(pattern=r'^[a-f0-9]{64}$')


class MemoryDecisionRequest(MemoryCommand):
    expected_revision: int = Field(strict=True,ge=1)


class MemoryLesson(V2Contract):
    lesson_ref: UUID
    outcome: Outcome
    human_reason: str
    context_snapshot: MemoryContext
    scope: Scope
    scope_fields: list[str]
    source_operational_alert_ref: UUID
    source_case_ref: UUID | None
    created_by_actor_id: int
    created_at: str
    configuration: MemoryConfig


class MemoryDecision(V2Contract):
    action: Literal['activate','reject']
    actor_id: int
    reason: str
    created_at: str


class MemoryView(V2Contract):
    lesson: MemoryLesson
    status: Status
    revision: int
    support_count: int
    conflict_count: int
    agreement_ratio: float
    valid_from: AwareDatetime | None
    expires_at: AwareDatetime | None
    last_supported_at: str
    last_conflict_at: str | None
    decision: MemoryDecision | None


class MemoryEvidence(V2Contract):
    source_operational_alert_ref: UUID
    source_case_ref: UUID | None
    actor_id: int
    outcome: Outcome
    human_reason: str
    context_snapshot: MemoryContext
    detector_snapshot: OperationalAlertV2
    source_state_version: str
    relation: Literal['support','conflict']
    created_at: str


class MemoryAudit(V2Contract):
    id: int
    lesson_ref: UUID
    actor_id: int
    event_type: str
    evidence: MemoryEvidence | None
    lesson_snapshot: MemoryView
    reason: str
    created_at: str


class MemoryMutation(V2Contract):
    memory: MemoryView
    replayed: bool


class MemoryMatch(V2Contract):
    memory: MemoryView
    strength: Literal['high','partial']
    matched_fields: list[str]
    mismatched_fields: list[str]
    unavailable_fields: list[str]
    guidance_active: bool
    review_required: Literal[True] = True


def _json(value):
    return json.dumps(value,sort_keys=True,allow_nan=False)


def _begin(conn,actor):
    if conn.in_transaction or not conn.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise ValueError('memory mutations require foreign keys and no transaction')
    conn.execute('BEGIN IMMEDIATE')
    user=db.get(conn,m.User,actor)
    if user is None or user.status!='active' or user.role not in ('security_analyst','system_admin'):
        conn.rollback()
        raise PermissionError('active operational analyst or administrator required')


def _row(conn,ref):
    row=conn.execute('SELECT * FROM triage_memory_lessons WHERE lesson_ref=?',(str(ref),)).fetchone()
    if row is None:
        raise LookupError('Triage memory lesson not found')
    return row


def read_memory(conn,ref,*,now=None):
    row=_row(conn,ref)
    lesson=MemoryLesson.model_validate_json(row['snapshot'])
    counts={r['relation']:(r['n'],r['last_at']) for r in conn.execute(
        'SELECT relation,count(*) n,max(created_at) last_at FROM triage_memory_support_events WHERE lesson_id=? GROUP BY relation',(row['id'],))}
    supports,last_support=counts.get('support',(0,lesson.created_at))
    conflicts,last_conflict=counts.get('conflict',(0,None))
    ratio=supports/(supports+conflicts) if supports+conflicts else 0
    decision=conn.execute('SELECT * FROM triage_memory_decisions WHERE lesson_id=?',(row['id'],)).fetchone()
    config=lesson.configuration
    status='eligible_for_activation' if supports>=config.minimum_support and ratio>=config.minimum_agreement_ratio and conflicts<=config.maximum_conflicts else 'candidate'
    valid=None
    expires=datetime.fromisoformat(lesson.created_at.replace('Z','+00:00'))+timedelta(days=config.default_validity_days)
    if (now or m.utc_now())>=expires:
        status='expired'
    if decision:
        if decision['action']=='reject':
            status='rejected'
        else:
            valid=datetime.fromisoformat(decision['valid_from'].replace('Z','+00:00'))
            expires=datetime.fromisoformat(decision['expires_at'].replace('Z','+00:00'))
            status='conflict_review' if conflicts else 'expired' if (now or m.utc_now())>=expires else 'active'
    return MemoryView(lesson=lesson,status=status,revision=supports+conflicts+bool(decision),support_count=supports,
        conflict_count=conflicts,agreement_ratio=ratio,valid_from=valid,expires_at=expires,last_supported_at=last_support,
        last_conflict_at=last_conflict,decision=MemoryDecision(action=decision['action'],actor_id=decision['actor_id'],
        reason=decision['reason'],created_at=decision['created_at']) if decision else None)


def _audit(conn,row,actor,kind,reason,evidence=None):
    current=read_memory(conn,row['lesson_ref'])
    payload=dict(lessonSnapshot=current.model_dump(mode='json',by_alias=True),
                 evidence=evidence.model_dump(mode='json',by_alias=True) if evidence else None,reason=reason)
    conn.execute('INSERT INTO triage_memory_audit (lesson_id,actor_id,event_type,payload,created_at) VALUES (?,?,?,?,?)',
        (row['id'],actor,kind,_json(payload),db.format_timestamp(m.utc_now())))


def record_review(conn,alert_ref,*,actor_id,request:MemoryReviewRequest):
    request=MemoryReviewRequest.model_validate(request.model_dump())
    payload=_json(dict(alertRef=str(alert_ref),request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        retry=conn.execute('SELECT * FROM triage_memory_support_events WHERE request_id=? AND is_primary=1',(str(request.request_id),)).fetchone()
        if retry:
            if retry['actor_id']!=actor_id or retry['request_payload']!=payload:
                raise MemoryConflict('requestId belongs to another human review')
            row=conn.execute('SELECT lesson_ref FROM triage_memory_lessons WHERE id=?',(retry['lesson_id'],)).fetchone()
            result=MemoryMutation(memory=read_memory(conn,row[0]),replayed=True)
            conn.commit()
            return result
        source=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(alert_ref),)).fetchone()
        if source is None:
            raise LookupError('Operational alert not found')
        alert=read_projection(conn,source[0])
        state=read_triage(conn,source[0])
        if state_version(state)!=request.expected_state_version:
            raise MemoryConflict('alert state changed; refresh before recording human review')
        if state.handling_route not in ('tier1_review','tier2_candidate','tier2_case'):
            raise MemoryConflict('alert must be admitted to human review before memory review')
        if conn.execute('SELECT 1 FROM triage_memory_support_events WHERE source_alert_id=?',(source[0],)).fetchone():
            raise MemoryConflict('this alert already contributed a human memory review; distinct alerts are required')
        context=context_for(alert)
        values=context.model_dump(by_alias=True)
        config=load_config()
        required=config.exact_required_fields if request.scope=='exact' else config.narrow_required_fields
        if any(values.get(key) is None or values[key]=='' for key in required):
            raise MemoryConflict('required scope context is unavailable')
        fields=sorted(key for key,value in values.items() if value is not None) if request.scope=='exact' else sorted(required)
        key=sha256(_json(dict(scope=request.scope,values={key:values[key] for key in fields},configuration=config.model_dump())).encode()).hexdigest()
        row=conn.execute('SELECT * FROM triage_memory_lessons WHERE context_key=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
        previous=read_memory(conn,row['lesson_ref']) if row else None
        case=conn.execute('SELECT id,case_ref FROM tier2_cases WHERE primary_operational_alert_id=?',(source[0],)).fetchone()
        stamp=db.format_timestamp(m.utc_now())
        new=row is None or previous.status in ('expired','rejected')
        if new:
            lesson=MemoryLesson(lesson_ref=uuid4(),outcome=request.outcome,human_reason=request.reason,context_snapshot=context,
                scope=request.scope,scope_fields=fields,source_operational_alert_ref=alert_ref,
                source_case_ref=case['case_ref'] if case else None,created_by_actor_id=actor_id,created_at=stamp,configuration=config)
            conn.execute('INSERT INTO triage_memory_lessons (lesson_ref,context_key,detector_source,source_alert_id,source_case_id,actor_id,snapshot,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (str(lesson.lesson_ref),key,alert.detector_source,source[0],case['id'] if case else None,actor_id,lesson.model_dump_json(by_alias=True),stamp))
            row=_row(conn,lesson.lesson_ref)
        else:
            lesson=previous.lesson
        targets=[(row,previous,new,1)]
        # Evidence must also reach compatible lessons with a different scope/configuration.
        # Otherwise an exact-scope contradiction could leave a narrow active lesson trusted.
        others=conn.execute('SELECT * FROM triage_memory_lessons WHERE detector_source=? AND id!=?',(alert.detector_source,row['id'])).fetchall()
        for other in others:
            old=read_memory(conn,other['lesson_ref'])
            if old.status not in ('expired','rejected') and explain_match(old,context).strength=='high':
                targets.append((other,old,False,0))
        for target,old,is_new,is_primary in targets:
            outcome=lesson.outcome if is_primary else old.lesson.outcome
            relation='support' if request.outcome==outcome else 'conflict'
            evidence=MemoryEvidence(source_operational_alert_ref=alert_ref,source_case_ref=case['case_ref'] if case else None,
                actor_id=actor_id,outcome=request.outcome,human_reason=request.reason,context_snapshot=context,detector_snapshot=alert,
                source_state_version=request.expected_state_version,relation=relation,created_at=stamp)
            conn.execute('INSERT INTO triage_memory_support_events (lesson_id,source_alert_id,source_case_id,actor_id,outcome,relation,reason,evidence_snapshot,is_primary,request_id,request_payload,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (target['id'],source[0],case['id'] if case else None,actor_id,request.outcome,relation,request.reason,evidence.model_dump_json(by_alias=True),is_primary,str(request.request_id),payload,stamp))
            kind='CANDIDATE_CREATED' if is_new else 'SUPPORT_ADDED' if relation=='support' else 'CONFLICT_ADDED'
            _audit(conn,target,actor_id,'V2_TRIAGE_MEMORY_'+kind,request.reason,evidence)
            if old and old.status=='active' and relation=='conflict':
                _audit(conn,target,actor_id,'V2_TRIAGE_MEMORY_CONFLICT_REVIEW_REQUIRED',request.reason,evidence)
        result=MemoryMutation(memory=read_memory(conn,row['lesson_ref']),replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def decide_memory(conn,lesson_ref,*,actor_id,action,request:MemoryDecisionRequest):
    request=MemoryDecisionRequest.model_validate(request.model_dump())
    if action not in ('activate','reject'):
        raise ValueError('unknown memory decision')
    payload=_json(dict(lessonRef=str(lesson_ref),action=action,request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        row=_row(conn,lesson_ref)
        retry=conn.execute('SELECT * FROM triage_memory_decisions WHERE request_id=?',(str(request.request_id),)).fetchone()
        current=read_memory(conn,lesson_ref)
        if retry:
            if retry['actor_id']!=actor_id or retry['request_payload']!=payload:
                raise MemoryConflict('requestId belongs to another activation decision')
            conn.commit()
            return MemoryMutation(memory=current,replayed=True)
        if current.revision!=request.expected_revision:
            raise MemoryConflict('lesson changed; refresh before deciding')
        if current.decision is not None:
            raise MemoryConflict('lesson already decided; historical decisions are immutable')
        if current.status=='expired':
            raise MemoryConflict('lesson expired; a new human review is required')
        if action=='activate' and current.status!='eligible_for_activation':
            raise MemoryConflict('activation requires support threshold, agreement and zero conflicts')
        now=m.utc_now()
        stamp=db.format_timestamp(now)
        expiry=db.format_timestamp(now+timedelta(days=current.lesson.configuration.default_validity_days)) if action=='activate' else None
        conn.execute('INSERT INTO triage_memory_decisions (lesson_id,actor_id,action,reason,lesson_snapshot,valid_from,expires_at,request_id,request_payload,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (row['id'],actor_id,action,request.reason,current.model_dump_json(by_alias=True),stamp if expiry else None,expiry,str(request.request_id),payload,stamp))
        _audit(conn,row,actor_id,'V2_TRIAGE_MEMORY_'+('ACTIVATED' if action=='activate' else 'ACTIVATION_REJECTED'),request.reason)
        result=MemoryMutation(memory=read_memory(conn,lesson_ref),replayed=False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def explain_match(memory,context):
    learned=memory.lesson.context_snapshot.model_dump(by_alias=True)
    incoming=context.model_dump(by_alias=True)
    matched=[]; mismatched=[]; unavailable=[]
    for key,value in learned.items():
        if value is None or incoming[key] is None:
            unavailable.append(key)
        elif value==incoming[key]:
            matched.append(key)
        else:
            mismatched.append(key)
    high=set(memory.lesson.scope_fields).issubset(matched)
    return MemoryMatch(memory=memory,strength='high' if high else 'partial',matched_fields=matched,
        mismatched_fields=mismatched,unavailable_fields=unavailable,guidance_active=high and memory.status=='active')


def list_memory(conn,limit,offset):
    total=conn.execute('SELECT count(*) FROM triage_memory_lessons').fetchone()[0]
    rows=conn.execute('SELECT lesson_ref FROM triage_memory_lessons ORDER BY id DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
    return [read_memory(conn,row[0]) for row in rows],total


def memory_history(conn,ref,limit,offset):
    row=_row(conn,ref)
    total=conn.execute('SELECT count(*) FROM triage_memory_audit WHERE lesson_id=?',(row['id'],)).fetchone()[0]
    rows=conn.execute('SELECT * FROM triage_memory_audit WHERE lesson_id=? ORDER BY id DESC LIMIT ? OFFSET ?',(row['id'],limit,offset)).fetchall()
    return [MemoryAudit(id=r['id'],lesson_ref=ref,actor_id=r['actor_id'],event_type=r['event_type'],created_at=r['created_at'],**json.loads(r['payload'])) for r in rows],total


def lookup_memory(conn,alert_ref,limit,offset):
    row=conn.execute('SELECT id FROM operational_alerts_v2 WHERE operational_alert_ref=?',(str(alert_ref),)).fetchone()
    if row is None:
        raise LookupError('Operational alert not found')
    context=context_for(read_projection(conn,row[0]))
    # Read-only, paginated related lessons; partial/conflicted/expired records are never active guidance.
    where="detector_source=? AND (json_extract(snapshot,'$.contextSnapshot.detectionTitle')=? OR json_extract(snapshot,'$.contextSnapshot.detectionCategory')=?)"
    args=(context.detector_source,context.detection_title,context.detection_category)
    total=conn.execute('SELECT count(*) FROM triage_memory_lessons WHERE '+where,args).fetchone()[0]
    rows=conn.execute('SELECT lesson_ref FROM triage_memory_lessons WHERE '+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
    return [explain_match(read_memory(conn,r[0]),context) for r in rows],total
