"""Read-only, deterministic case assistance. Suggestions confer no decision authority."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from packages.contracts.operational_v2 import V2Contract
from packages.contracts.suricata_bundle import AttackClassification, SystemRoutingDecision, SuricataEvidenceBundle
from packages.detection.adapters.operational_v2 import read_projection, read_triage
from packages.detection.adapters.suricata_bundle import bundle_for
from packages.detection.analyst_verdict import AnalystVerdict
from packages.detection.context_store import resolved_for
from packages.detection.tier2_cases import CaseSnapshot, read_case
from packages.detection.trusted_context import ResolvedTrustedContext


class AssistancePolicy(V2Contract):
    version: str = Field(min_length=1)
    window_hours: int = Field(ge=1, le=168)
    maximum_related: int = Field(ge=1, le=20)
    relationships: tuple[Literal['source', 'destination', 'pair', 'category', 'signature', 'sensor'], ...] = Field(min_length=1)
    templates: dict[str, list[str]]

    @model_validator(mode='after')
    def complete(self):
        required = {'unknown_needs_expert', 'brute_force', 'web_attack', 'reconnaissance_port_scan',
                    'informational', 'generic_known', 'open_case', 'critical_route'}
        if not required <= self.templates.keys() or any(not steps or any(not step.strip() for step in steps)
                                                       for steps in self.templates.values()):
            raise ValueError('explicit nonempty assistance templates required')
        if len(set(self.relationships)) != len(self.relationships):
            raise ValueError('relationship rules must be unique')
        return self


def load_policy():
    return AssistancePolicy.model_validate_json((Path(__file__).resolve().parents[2] /
        'config/tier2-assistance-v1.json').read_text(encoding='utf-8'))


class InvestigationBrief(V2Contract):
    at_case_creation: CaseSnapshot
    classification_at_admission: AttackClassification | None
    system_routing_at_admission: SystemRoutingDecision | None
    suricata_evidence_at_creation: SuricataEvidenceBundle | None
    current_case_status: str
    current_case_revision: int
    current_tier1_verdict: AnalystVerdict | None
    tier1_verdict_explanation: str
    current_trusted_context: ResolvedTrustedContext
    uncertainties: list[str]


class RelatedAlert(V2Contract):
    operational_alert_ref: UUID
    title: str
    occurred_at: str
    source_ip: str
    destination_ip: str
    attack_category: str | None
    operational_priority: float | None
    priority_band: str | None
    handling_route: str
    relationship_reasons: list[str]


class InvestigationAssistance(V2Contract):
    case_ref: UUID
    assistance_policy_version: str
    correlation_window_hours: int
    maximum_related: int
    brief: InvestigationBrief
    related_alerts: list[RelatedAlert]
    suggested_steps: list[str]


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def related_alerts(conn, case, classification, policy):
    primary = case.snapshot.detector
    stamp = _instant(primary.occurred_at)
    if stamp is None:
        return []
    delta = timedelta(hours=policy.window_hours)
    # Bound the database selection by event time, not ingestion time. SQLite julianday
    # normalizes explicit UTC offsets; the precise Python check also retains microseconds.
    rows = conn.execute('''SELECT a.id, s.classification FROM operational_alerts_v2 a
        JOIN operational_system_routing s ON s.operational_alert_id=a.id
        JOIN operational_triage_state_v2 t ON t.operational_alert_id=a.id
        WHERE a.source_kind='external_nids_alert' AND a.id<>?
        AND t.workflow_stage<>'resolved'
        AND julianday(CASE WHEN substr(a.occurred_at,-5,1) IN ('+','-')
            THEN substr(a.occurred_at,1,length(a.occurred_at)-2)||':'||substr(a.occurred_at,-2)
            ELSE a.occurred_at END) BETWEEN julianday(?) AND julianday(?)
        AND NOT EXISTS (SELECT 1 FROM tier2_case_events e JOIN tier2_cases c ON c.id=e.case_id
            WHERE c.case_ref=? AND e.linked_alert_id=a.id)''',
        (primary.id, (stamp-delta).isoformat(), (stamp+delta).isoformat(), str(case.case_ref)))
    bundle = bundle_for(primary.detector_evidence)
    signatures = {s.signature_id for s in bundle.related_signatures} if bundle else set()
    enabled = set(policy.relationships)
    result = []
    for row in rows:
        alert = read_projection(conn, row['id'])
        occurred = _instant(alert.occurred_at)
        if occurred is None or abs(occurred-stamp)>delta:
            continue
        other = bundle_for(alert.detector_evidence)
        category = AttackClassification.model_validate_json(row['classification']).attack_category
        reasons = []
        if 'source' in enabled and alert.source_ip == primary.source_ip: reasons.append('Same source IP')
        if 'destination' in enabled and alert.destination_ip == primary.destination_ip: reasons.append('Same destination IP')
        if 'pair' in enabled and alert.source_ip == primary.source_ip and alert.destination_ip == primary.destination_ip:
            reasons.append('Same source/destination pair')
        # Unknown is uncertainty, not an asserted shared attack pattern.
        if 'category' in enabled and classification and category == classification.attack_category and category not in (None, 'unknown_needs_expert'):
            reasons.append('Same normalized attack category: '+category)
        if 'signature' in enabled and other and signatures.intersection(s.signature_id for s in other.related_signatures):
            reasons.append('Shared Suricata signature ID')
        if 'sensor' in enabled and other and bundle and other.sensor_id == bundle.sensor_id:
            reasons.append('Same sensor: '+bundle.sensor_id)
        if not reasons:
            continue
        state = read_triage(conn, alert.id)
        result.append((occurred, RelatedAlert(operational_alert_ref=alert.operational_alert_ref,
            title=alert.detection_title, occurred_at=alert.occurred_at, source_ip=alert.source_ip,
            destination_ip=alert.destination_ip, attack_category=category,
            operational_priority=state.operational_priority, priority_band=state.priority_band,
            handling_route=state.handling_route,
            relationship_reasons=[*reasons, f'Within ±{policy.window_hours} hours of primary alert'])))
    result.sort(key=lambda item: (-len(item[1].relationship_reasons),
        -(item[1].operational_priority if item[1].operational_priority is not None else -1),
        -item[0].timestamp(), str(item[1].operational_alert_ref)))
    return [item for _, item in result[:policy.maximum_related]]


def read_assistance(conn, case_ref):
    case = read_case(conn, case_ref)
    alert = case.snapshot.detector
    policy = load_policy()
    system = conn.execute('SELECT classification,routing_decision FROM operational_system_routing WHERE operational_alert_id=?',
        (alert.id,)).fetchone()
    classification = AttackClassification.model_validate_json(system['classification']) if system else None
    routing = SystemRoutingDecision.model_validate_json(system['routing_decision']) if system else None
    row = conn.execute('SELECT snapshot FROM analyst_verdict_events WHERE operational_alert_id=? ORDER BY revision DESC LIMIT 1',
        (alert.id,)).fetchone()
    verdict = AnalystVerdict.model_validate_json(row[0]) if row else None
    context = resolved_for(conn, alert.operational_alert_ref)
    bundle = bundle_for(alert.detector_evidence)
    uncertainties = []
    if classification is None:
        uncertainties.append('Normalized classification unavailable for this historical case; no category is inferred.')
    elif classification.status in ('unmapped', 'conflict'):
        uncertainties.extend(['Unknown / Needs Expert. Classification is unresolved; maliciousness is not established.', *classification.reasons])
    if not context.complete:
        uncertainties.append('Current trusted context is incomplete, expired or conflicting. Missing values are unknown, not false.')
    missing = sorted({'http', 'dns', 'tls', 'ssh'} - set(bundle.evidence_types if bundle else ()))
    if missing:
        uncertainties.append('Optional evidence not recorded: '+', '.join(missing)+'. Its absence does not establish benign or malicious activity.')
    if _instant(alert.occurred_at) is None:
        uncertainties.append('Primary event time lacks a usable explicit timezone; related-alert suggestions are unavailable.')
    related = related_alerts(conn, case, classification, policy)
    key = ('informational' if classification and classification.status == 'informational_policy_signal' else
        classification.attack_category if classification else 'unknown_needs_expert')
    steps = list(policy.templates.get(key, policy.templates['generic_known']))
    if case.status == 'open':
        steps = [*policy.templates['open_case'], *steps]
    if routing and routing.route_class == 'CRITICAL_ESCALATION':
        steps.extend(policy.templates['critical_route'])
    if not context.complete:
        steps.append('Verify missing or conflicting asset and trusted-context facts with their recorded sources; do not infer defaults.')
    if missing:
        steps.append('If available and authorized, inspect missing '+', '.join(missing)+' evidence; otherwise document this evidence limitation.')
    if related:
        steps.append('Review the relationship reasons of potential related alerts. Link only after human review and an explicit reason; relationships do not prove a campaign.')
    steps.append('After reviewing evidence, explicitly record an Investigation Finding and rationale. Assistance does not select a Finding or execute a response.')
    explanation = ('Current human Tier 1 Verdict, separate from the immutable case snapshot.' if verdict else
        'Not recorded / not required for automatic Tier 2 routing.' if case.decision_source == 'system_policy' else
        'Not recorded. Manual escalation does not imply a Tier 1 Verdict.')
    return InvestigationAssistance(case_ref=case.case_ref, assistance_policy_version=policy.version,
        correlation_window_hours=policy.window_hours, maximum_related=policy.maximum_related,
        brief=InvestigationBrief(at_case_creation=case.snapshot, classification_at_admission=classification,
            system_routing_at_admission=routing, suricata_evidence_at_creation=bundle,
            current_case_status=case.status, current_case_revision=case.revision,
            current_tier1_verdict=verdict, tier1_verdict_explanation=explanation,
            current_trusted_context=context, uncertainties=uncertainties), related_alerts=related, suggested_steps=steps)
