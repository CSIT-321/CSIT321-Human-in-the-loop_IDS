const reasons: Record<string,string> = {
 UNKNOWN_REQUIRED_CONTEXT:"Required safety context is incomplete",
 MISSING_TRUSTED_CONTEXT:"Trusted safety context has not been recorded",
 UNSUPPORTED_WORKFLOW:"This workflow stage requires human review",
 NO_QUALIFIED_ACTIVE_EXACT_MEMORY:"No active memory lesson meets the exact-match safety requirements",
 HUMAN_REVIEW_OVERRIDE:"An analyst requires human review", EXISTING_HUMAN_VERDICT:"A human verdict is already recorded",
 TIER2_RECOMMENDED:"Tier 2 escalation is recommended", DETECTOR_DISAGREEMENT:"Detector evidence disagrees",
 STALE_OR_FUTURE_CONTEXT:"Safety context is outside its valid time window", HIGH_RISK_ASSET:"The asset is high risk",
 KNOWN_MALICIOUS_INDICATOR:"A known malicious indicator is present", EVIDENCE_CONFLICT:"Evidence conflicts",
 CONFIRMED_MALICIOUS_CONTEXT:"Safety context records confirmed malicious activity", RESPONSE_REQUIRED:"A response is required",
 HUMAN_ESCALATION_CONTEXT:"Human escalation or unresolved Tier 1 work requires attention", CAMPAIGN_RISK:"Campaign activity requires review",
 MEMORY_CONFLICT:"Related memory contains conflicting evidence", UNSAFE_MEMORY_OUTCOME:"Related memory records suspicious or malicious activity",
 DETERMINISTIC_AUDIT_SAMPLE:"Selected for human audit sampling", VALIDATED_MEMORY_AND_CONTEXT:"Memory and safety context passed the review policy",
};
/** Translate only supplied codes; retain original facts and wording in technical evidence. */
export function reviewLanguage(text:string) { return text.replace(/\b[A-Z][A-Z_]{3,}\b/g, code => reasons[code] ?? code.toLowerCase().replaceAll("_"," ")); }
