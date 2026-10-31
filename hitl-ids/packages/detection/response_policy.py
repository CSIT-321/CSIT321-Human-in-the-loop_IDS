"""Deterministic response suggestions only. No execution, networking or external integrations."""
from ipaddress import ip_address
from typing import Literal
from uuid import UUID
from packages.contracts.operational_v2 import V2Contract
from packages.detection.tier2_cases import Finding

ResponseType = Literal['block_source_ip','isolate_host','disable_account','notify_security_team','monitor','further_investigation']
TargetType = Literal['ip','host','account','case','operational_alert']
POLICY_VERSION = 'response-policy-v1'


class ResponseFinding(V2Contract):
    event_id: int
    finding: Finding
    actor_id: int
    reason: str
    created_at: str


class PolicySuggestion(V2Contract):
    recommendation_type: ResponseType
    target_type: TargetType
    target_value: str
    rationale: str
    policy_version: str = POLICY_VERSION


def recommend_response(finding: ResponseFinding | None, case_ref: UUID, primary_source_ip: str | None) -> PolicySuggestion:
    """Only an explicit investigation finding can suggest containment; scores are not inputs."""
    category = finding.finding if finding else None
    if category == 'confirmed_malicious' and primary_source_ip:
        try:
            target = str(ip_address(primary_source_ip))
        except ValueError:
            target = None
        if target:
            return PolicySuggestion(recommendation_type='block_source_ip',target_type='ip',target_value=target,
                rationale='Latest Tier 2 finding is confirmed_malicious and the primary case evidence identifies this source IP. '
                          'Human approval is required; no action is executed.')
    if category in ('suspicious','expected_activity'):
        return PolicySuggestion(recommendation_type='monitor',target_type='case',target_value=str(case_ref),
            rationale=f'Latest Tier 2 finding is {category}; monitor this case without recommending containment.')
    reason = ('Confirmed malicious finding lacks a valid source-IP target; further investigation is required.'
              if category == 'confirmed_malicious' else
              'The finding is inconclusive or absent; further investigation is required before a containment proposal.')
    return PolicySuggestion(recommendation_type='further_investigation',target_type='case',
                            target_value=str(case_ref),rationale=reason)
