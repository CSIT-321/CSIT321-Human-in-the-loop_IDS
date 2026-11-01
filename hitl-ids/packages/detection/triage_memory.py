"""Organisation-local advisory memory. No detector, triage, case or response writes."""
from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid4
from pydantic import AwareDatetime,Field,field_validator,model_validator
from packages.detection.tier2_cases import InvestigationConclusion
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
    source_kind: Literal['analyst_verdict','tier2_conclusion','legacy_memory_review'] = 'legacy_memory_review'
    source_conclusion: InvestigationConclusion | None = None
    conclusion_author_name: str | None = None
    contribution_actor_name: str | None = None
    contribution_scope: Scope | None = None
    source_verdict_ref: UUID | None = None
    source_verdict_revision: int | None = None
    verdict_author_id: int | None = None
    verdict_author_name: str | None = None
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

    @model_validator(mode='before')
    @classmethod
    def historical_source_kind(cls,value):
        if isinstance(value,dict) and 'sourceKind' not in value and 'source_kind' not in value:
            value={**value,'source_kind':'analyst_verdict' if value.get('sourceVerdictRef',value.get('source_verdict_ref')) else 'legacy_memory_review'}
        return value


class MemoryAudit(V2Contract):
    evidence_current: bool | None = None
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


class VerdictMemoryRequest(V2Contract):
    request_id: UUID
    verdict_ref: UUID
    expected_state_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope: Scope = 'exact'


class VerdictMemoryState(V2Contract):
    latest_verdict_ref: UUID | None
    latest_verdict_revision: int | None
    contribution_status: Literal['not_contributed','contributed','superseded']
    scope: Scope | None
    lesson_ref: UUID | None


class ConclusionMemoryRequest(V2Contract):
    request_id: UUID
    expected_case_revision: int = Field(strict=True,ge=1)
    conclusion_event_id: int = Field(strict=True,ge=1)
    scope: Scope = 'exact'


class ConclusionMemoryState(V2Contract):
    latest_conclusion: InvestigationConclusion | None
    eligible: bool
    contribution_status: Literal['not_contributed','contributed','superseded']
    scope: Scope | None
    lesson_ref: UUID | None
    memory: MemoryView | None
    previous_expert_evidence_superseded: bool
    tier1_evidence_superseded: bool


def expert_authority(conn,alert_ref):
    # A Finding is authoritative only for its Case's primary alert, never linked alerts.
    return conn.execute("SELECT e.id,e.finding FROM tier2_case_events e JOIN tier2_cases c ON c.id=e.case_id "
        "JOIN operational_alerts_v2 a ON a.id=c.primary_operational_alert_id "
        "WHERE a.operational_alert_ref=? AND e.action='finding' ORDER BY e.id DESC LIMIT 1",(str(alert_ref),)).fetchone()


def conclusion_memory_state(conn,case_ref):
    from packages.detection.tier2_cases import read_case
    case=read_case(conn,case_ref);latest=case.latest_conclusion
    contributions=conn.execute('SELECT c.*,l.lesson_ref FROM conclusion_memory_contributions c '
        'JOIN tier2_cases t ON t.id=c.source_case_id JOIN triage_memory_lessons l ON l.id=c.primary_lesson_id '
        'WHERE t.case_ref=? ORDER BY c.id DESC',(str(case_ref),)).fetchall()
    prior=contributions[0] if contributions else None
    current=bool(prior and latest and prior['conclusion_event_id']==latest.event_id)
    tier1=conn.execute('SELECT 1 FROM verdict_memory_contributions c JOIN operational_alerts_v2 a ON a.id=c.source_alert_id '
        'WHERE a.operational_alert_ref=?',(str(case.primary_operational_alert_ref),)).fetchone()
    return ConclusionMemoryState(latest_conclusion=latest,
        eligible=bool(latest and latest.record_kind=='investigation_conclusion' and latest.finding!='inconclusive'),
        contribution_status='contributed' if current else 'superseded' if prior else 'not_contributed',
        scope=prior['scope'] if prior else None,lesson_ref=prior['lesson_ref'] if prior else None,
        memory=read_memory(conn,prior['lesson_ref']) if prior else None,
        previous_expert_evidence_superseded=any(not latest or r['conclusion_event_id']!=latest.event_id for r in contributions),
        tier1_evidence_superseded=bool(latest and tier1))


def contribute_conclusion(conn,case_ref,*,actor_id,request:ConclusionMemoryRequest):
    from packages.detection.tier2_cases import read_case
    request=ConclusionMemoryRequest.model_validate(request.model_dump())
    payload=_json(dict(caseRef=str(case_ref),request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        prior=conn.execute('SELECT * FROM conclusion_memory_contributions WHERE request_id=?',(str(request.request_id),)).fetchone()
        if prior:
            if prior['actor_id']!=actor_id or prior['request_payload']!=payload:
                raise MemoryConflict('requestId belongs to another expert contribution')
            lesson=conn.execute('SELECT lesson_ref FROM triage_memory_lessons WHERE id=?',(prior['primary_lesson_id'],)).fetchone()
            result=MemoryMutation(memory=read_memory(conn,lesson[0]),replayed=True);conn.commit();return result
        for table in ('verdict_memory_contributions','triage_memory_support_events'):
            if conn.execute(f'SELECT 1 FROM {table} WHERE request_id=?',(str(request.request_id),)).fetchone():
                raise MemoryConflict('requestId already belongs to another human learning contribution')
        case=read_case(conn,case_ref);latest=case.latest_conclusion
        if case.revision!=request.expected_case_revision:
            raise MemoryConflict('Case changed; refresh before contributing expert evidence')
        if (not latest or latest.event_id!=request.conclusion_event_id or
                latest.record_kind!='investigation_conclusion' or latest.finding=='inconclusive'):
            raise MemoryConflict('only the latest eligible expert conclusion can be contributed; Inconclusive is not reusable')
        if conn.execute('SELECT 1 FROM conclusion_memory_contributions WHERE conclusion_event_id=?',(latest.event_id,)).fetchone():
            raise MemoryConflict('this conclusion already contributed; distinct alerts are required for support')
        state=read_triage(conn,case.snapshot.detector.id)
        return record_review(conn,case.primary_operational_alert_ref,actor_id=actor_id,request=MemoryReviewRequest(
            request_id=request.request_id,outcome=latest.finding,reason=latest.reason,scope=request.scope,
            expected_state_version=state_version(state)),_expert=latest,_linked_payload=payload)
    except Exception:
        conn.rollback();raise


def current_source_evidence(conn,alert_ref):
    result=[]
    for table in ('triage_memory_support_events','verdict_memory_evidence','conclusion_memory_evidence'):
        for row in conn.execute(f"SELECT lesson_id,evidence_snapshot FROM {table} WHERE json_extract(evidence_snapshot,'$.sourceOperationalAlertRef')=?",(str(alert_ref),)):
            evidence=json.loads(row['evidence_snapshot'])
            if evidence_is_current(conn,evidence): result.append((row['lesson_id'],MemoryEvidence.model_validate(evidence)))
    return result


def audit_expert_supersession(conn,previous,actor_id,event_id):
    # Called inside the Case command's transaction after its immutable conclusion event.
    for lesson_id,evidence in previous:
        row=conn.execute('SELECT * FROM triage_memory_lessons WHERE id=?',(lesson_id,)).fetchone()
        _audit(conn,row,actor_id,'V2_TRIAGE_MEMORY_EXPERT_SUPERSEDED',
            f'Tier 2 investigation conclusion event #{event_id} superseded earlier learning evidence from the same alert. History is preserved.',evidence)


def _has_verdict_memory(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='verdict_memory_contributions'").fetchone() is not None


def evidence_is_current(conn,evidence):
    if evidence is None: return None
    expert=expert_authority(conn,evidence['sourceOperationalAlertRef'])
    if expert:
        linked=evidence.get('sourceConclusion')
        return bool(linked and linked['eventId']==expert['id'] and expert['finding']!='inconclusive')
    if evidence.get('sourceConclusion'): return False
    ref=evidence.get('sourceVerdictRef')
    if ref:
        return conn.execute('SELECT 1 FROM analyst_verdict_events v WHERE verdict_ref=? AND NOT EXISTS (SELECT 1 FROM analyst_verdict_events newer WHERE newer.operational_alert_id=v.operational_alert_id AND newer.revision>v.revision)',(ref,)).fetchone() is not None
    # A linked contribution replaces this alert's old compatibility contribution too.
    if _has_verdict_memory(conn):
        return conn.execute('SELECT 1 FROM verdict_memory_contributions c JOIN operational_alerts_v2 a ON a.id=c.source_alert_id WHERE a.operational_alert_ref=?',(evidence['sourceOperationalAlertRef'],)).fetchone() is None
    return True


def effective_evidence(conn,lesson_id):
    legacy=conn.execute('SELECT evidence_snapshot FROM triage_memory_support_events WHERE lesson_id=?',(lesson_id,)).fetchall()
    linked=[];invalidation_revision=0
    if _has_verdict_memory(conn):
        linked=conn.execute('SELECT e.evidence_snapshot FROM verdict_memory_evidence e WHERE lesson_id=?',(lesson_id,)).fetchall()
        invalidation_revision=conn.execute('SELECT coalesce(sum((SELECT max(revision) FROM analyst_verdict_events WHERE operational_alert_id=c.source_alert_id)-v.revision),0) FROM verdict_memory_evidence e JOIN verdict_memory_contributions c ON c.id=e.contribution_id JOIN analyst_verdict_events v ON v.verdict_ref=c.source_verdict_ref WHERE e.lesson_id=?',(lesson_id,)).fetchone()[0]
    expert=conn.execute('SELECT evidence_snapshot FROM conclusion_memory_evidence WHERE lesson_id=?',(lesson_id,)).fetchall()
    rows=[*legacy,*linked,*expert]
    current={}
    for row in rows:
        evidence=json.loads(row[0]); authority=expert_authority(conn,evidence['sourceOperationalAlertRef'])
        if authority and not evidence_is_current(conn,evidence): invalidation_revision+=authority['id']
        if evidence_is_current(conn,evidence):
            current[evidence['sourceOperationalAlertRef']]=MemoryEvidence.model_validate(evidence)
    return list(current.values()),len(rows)+invalidation_revision


def verdict_memory_state(conn,alert_ref):
    from packages.detection.analyst_verdict import _alert
    alert=_alert(conn,alert_ref)
    latest=conn.execute('SELECT verdict_ref,revision FROM analyst_verdict_events WHERE operational_alert_id=? ORDER BY revision DESC LIMIT 1',(alert.id,)).fetchone()
    contribution=conn.execute('SELECT c.*,l.lesson_ref FROM verdict_memory_contributions c JOIN triage_memory_lessons l ON l.id=c.primary_lesson_id WHERE c.source_alert_id=? ORDER BY c.id DESC LIMIT 1',(alert.id,)).fetchone()
    status='not_contributed' if contribution is None else 'contributed' if latest and contribution['source_verdict_ref']==latest['verdict_ref'] and not expert_authority(conn,alert_ref) else 'superseded'
    return VerdictMemoryState(latest_verdict_ref=latest['verdict_ref'] if latest else None,latest_verdict_revision=latest['revision'] if latest else None,
        contribution_status=status,scope=contribution['scope'] if contribution else None,lesson_ref=contribution['lesson_ref'] if contribution else None)


def contribute_verdict(conn,alert_ref,*,actor_id,request:VerdictMemoryRequest):
    from packages.detection.analyst_verdict import read_verdict
    request=VerdictMemoryRequest.model_validate(request.model_dump())
    payload=_json(dict(alertRef=str(alert_ref),request=request.model_dump(mode='json')))
    _begin(conn,actor_id)
    try:
        prior=conn.execute('SELECT * FROM verdict_memory_contributions WHERE request_id=?',(str(request.request_id),)).fetchone()
        if prior:
            if prior['actor_id']!=actor_id or prior['request_payload']!=payload: raise MemoryConflict('requestId belongs to another contribution')
            lesson=conn.execute('SELECT lesson_ref FROM triage_memory_lessons WHERE id=?',(prior['primary_lesson_id'],)).fetchone()
            result=MemoryMutation(memory=read_memory(conn,lesson[0]),replayed=True);conn.commit();return result
        if conn.execute('SELECT 1 FROM triage_memory_support_events WHERE request_id=?',(str(request.request_id),)).fetchone():
            raise MemoryConflict('requestId already belongs to a historical memory review')
        if conn.execute('SELECT 1 FROM conclusion_memory_contributions WHERE request_id=?',(str(request.request_id),)).fetchone():
            raise MemoryConflict('requestId already belongs to expert memory evidence')
        view=read_verdict(conn,alert_ref,actor_id)
        if expert_authority(conn,alert_ref):
            raise MemoryConflict('Tier 2 investigation supersedes Tier 1 evidence; use the latest eligible expert conclusion')
        if view.latest is None or view.latest.verdict_ref!=request.verdict_ref:
            raise MemoryConflict('record or refresh the latest Analyst Verdict before contributing')
        if not view.can_record or view.source_state_version!=request.expected_state_version:
            raise MemoryConflict('contribution requires the current Tier 1 review workflow and state')
        if conn.execute('SELECT 1 FROM verdict_memory_contributions WHERE source_verdict_ref=?',(str(request.verdict_ref),)).fetchone():
            raise MemoryConflict('this Verdict already contributed; distinct alerts are required for independent support')
        # The existing scope, fan-out, support/conflict and candidate machinery is reused.
        return record_review(conn,alert_ref,actor_id=actor_id,request=MemoryReviewRequest(request_id=request.request_id,
            outcome=view.latest.outcome,reason=view.latest.reason,scope=request.scope,expected_state_version=request.expected_state_version),
            _verdict=view.latest,_linked_payload=payload)
    except Exception:
        conn.rollback();raise


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
    effective,historical_revision=effective_evidence(conn,row['id'])
    support=[e for e in effective if e.relation=='support']; conflict=[e for e in effective if e.relation=='conflict']
    supports=len(support);conflicts=len(conflict)
    last_support=max((e.created_at for e in support),default=lesson.created_at)
    last_conflict=max((e.created_at for e in conflict),default=None)
    ratio=supports/(supports+conflicts) if supports+conflicts else 0
    decision=conn.execute('SELECT * FROM triage_memory_decisions WHERE lesson_id=?',(row['id'],)).fetchone()
    config=lesson.configuration
    status='eligible_for_activation' if supports>=config.minimum_support and ratio>=config.minimum_agreement_ratio and conflicts<=config.maximum_conflicts else 'candidate'
    evidence_safe=status=='eligible_for_activation'
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
            status='conflict_review' if conflicts else 'expired' if (now or m.utc_now())>=expires else 'active' if evidence_safe else 'candidate'
    return MemoryView(lesson=lesson,status=status,revision=historical_revision+bool(decision),support_count=supports,
        conflict_count=conflicts,agreement_ratio=ratio,valid_from=valid,expires_at=expires,last_supported_at=last_support,
        last_conflict_at=last_conflict,decision=MemoryDecision(action=decision['action'],actor_id=decision['actor_id'],
        reason=decision['reason'],created_at=decision['created_at']) if decision else None)


def _audit(conn,row,actor,kind,reason,evidence=None):
    current=read_memory(conn,row['lesson_ref'])
    payload=dict(lessonSnapshot=current.model_dump(mode='json',by_alias=True),
                 evidence=evidence.model_dump(mode='json',by_alias=True) if evidence else None,reason=reason)
    conn.execute('INSERT INTO triage_memory_audit (lesson_id,actor_id,event_type,payload,created_at) VALUES (?,?,?,?,?)',
        (row['id'],actor,kind,_json(payload),db.format_timestamp(m.utc_now())))


def record_review(conn,alert_ref,*,actor_id,request:MemoryReviewRequest,_verdict=None,_expert=None,_linked_payload=None):
    request=MemoryReviewRequest.model_validate(request.model_dump())
    payload=_json(dict(alertRef=str(alert_ref),request=request.model_dump(mode='json')))
    if _verdict is None and _expert is None:
        _begin(conn,actor_id)
    elif not conn.in_transaction:
        raise ValueError('verdict evidence requires the authorized contribution transaction')
    try:
        if _expert is not None:
            from packages.detection.tier2_cases import read_case
            canonical=read_case(conn,_expert.case_ref)
            if (canonical.latest_conclusion!=_expert or _expert.record_kind!='investigation_conclusion' or
                _expert.finding=='inconclusive' or canonical.primary_operational_alert_ref!=alert_ref or
                request.outcome!=_expert.finding or request.reason!=_expert.reason):
                raise MemoryConflict('expert evidence must match the latest eligible canonical conclusion')
        if _expert is None and _verdict is None:
            for table in ('verdict_memory_contributions','conclusion_memory_contributions'):
                if conn.execute(f'SELECT 1 FROM {table} WHERE request_id=?',(str(request.request_id),)).fetchone():
                    raise MemoryConflict('requestId already belongs to canonical human learning evidence')
        if _verdict is not None:
            from packages.detection.analyst_verdict import read_verdict
            canonical=read_verdict(conn,alert_ref,actor_id)
            if (not canonical.can_record or canonical.latest!=_verdict or
                    request.outcome!=_verdict.outcome or request.reason!=_verdict.reason):
                raise MemoryConflict('linked human evidence must match the authorized latest canonical Verdict')
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
        if _verdict is None and _expert is None and conn.execute('SELECT 1 FROM triage_memory_support_events WHERE source_alert_id=?',(source[0],)).fetchone():
            raise MemoryConflict('this alert already contributed a human memory review; distinct alerts are required')
        if _verdict is None and _expert is None and (expert_authority(conn,alert_ref) or conn.execute('SELECT 1 FROM operational_system_routing WHERE operational_alert_id=?',(source[0],)).fetchone()):
            raise MemoryConflict('current operational memory requires a canonical Analyst Verdict; use from-verdict')
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
                # Linked positive evidence must not generalize beyond the chosen scope.
                # Contradictions still reach every compatible lesson for safety.
                if ((_verdict is not None or _expert is not None) and request.outcome==old.lesson.outcome
                        and not set(fields).issubset(old.lesson.scope_fields)):
                    continue
                targets.append((other,old,False,0))
        contribution_id=None
        if _verdict is not None:
            contribution_id=conn.execute('INSERT INTO verdict_memory_contributions(source_alert_id,source_verdict_ref,actor_id,scope,primary_lesson_id,request_id,request_payload) VALUES (?,?,?,?,?,?,?)',
                (source[0],str(_verdict.verdict_ref),actor_id,request.scope,row['id'],str(request.request_id),_linked_payload)).lastrowid
        elif _expert is not None:
            contribution_id=conn.execute('INSERT INTO conclusion_memory_contributions(source_alert_id,source_case_id,conclusion_event_id,actor_id,scope,primary_lesson_id,request_id,request_payload) VALUES (?,?,?,?,?,?,?,?)',
                (source[0],case['id'],_expert.event_id,actor_id,request.scope,row['id'],str(request.request_id),_linked_payload)).lastrowid
        for target,old,is_new,is_primary in targets:
            outcome=lesson.outcome if is_primary else old.lesson.outcome
            relation='support' if request.outcome==outcome else 'conflict'
            evidence=MemoryEvidence(source_kind='tier2_conclusion' if _expert else 'analyst_verdict' if _verdict else 'legacy_memory_review',
                source_conclusion=_expert,conclusion_author_name=db.get(conn,m.User,_expert.actor_id).display_name if _expert else None,
                contribution_actor_name=db.get(conn,m.User,actor_id).display_name,contribution_scope=request.scope,
                source_verdict_ref=_verdict.verdict_ref if _verdict else None,
                source_verdict_revision=_verdict.revision if _verdict else None,
                verdict_author_id=_verdict.actor_id if _verdict else None,verdict_author_name=_verdict.actor_name if _verdict else None,
                source_operational_alert_ref=alert_ref,source_case_ref=case['case_ref'] if case else None,
                actor_id=actor_id,outcome=request.outcome,human_reason=request.reason,context_snapshot=context,detector_snapshot=alert,
                source_state_version=_verdict.source_state_version if _verdict else request.expected_state_version,relation=relation,created_at=stamp)
            if contribution_id is not None:
                table='conclusion_memory_evidence' if _expert else 'verdict_memory_evidence'
                conn.execute(f'INSERT INTO {table}(contribution_id,lesson_id,evidence_snapshot) VALUES (?,?,?)',
                    (contribution_id,target['id'],evidence.model_dump_json(by_alias=True)))
            else:
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
    return [MemoryAudit(evidence_current=evidence_is_current(conn,json.loads(r['payload']).get('evidence')),id=r['id'],lesson_ref=ref,actor_id=r['actor_id'],event_type=r['event_type'],created_at=r['created_at'],**json.loads(r['payload'])) for r in rows],total


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
