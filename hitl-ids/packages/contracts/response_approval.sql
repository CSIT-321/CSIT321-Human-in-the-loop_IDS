CREATE TABLE response_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_ref TEXT NOT NULL UNIQUE,
    case_id INTEGER NOT NULL REFERENCES tier2_cases(id),
    proposed_by_actor_id INTEGER NOT NULL REFERENCES users(id),
    proposal_source TEXT NOT NULL CHECK (proposal_source IN ('system_policy','analyst')),
    recommendation_type TEXT NOT NULL CHECK (recommendation_type IN
        ('block_source_ip','isolate_host','disable_account','notify_security_team','monitor','further_investigation')),
    target_type TEXT NOT NULL CHECK (target_type IN ('ip','host','account','case','operational_alert')),
    target_value TEXT NOT NULL,
    rationale TEXT NOT NULL CHECK (length(trim(rationale))>0),
    proposal_reason TEXT NOT NULL CHECK (length(trim(proposal_reason)) BETWEEN 1 AND 4000),
    case_revision INTEGER NOT NULL CHECK (case_revision>=1),
    policy_version TEXT,
    evidence_snapshot TEXT NOT NULL CHECK (json_valid(evidence_snapshot)),
    request_id TEXT NOT NULL UNIQUE,
    request_payload TEXT NOT NULL CHECK (json_valid(request_payload)),
    event_type TEXT NOT NULL CHECK (event_type IN ('V2_RESPONSE_RECOMMENDED','V2_RESPONSE_MANUAL_RECOMMENDATION')),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_response_case ON response_recommendations(case_id,id);
CREATE TABLE response_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL UNIQUE REFERENCES response_recommendations(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 4000),
    request_id TEXT NOT NULL UNIQUE,
    request_payload TEXT NOT NULL CHECK (json_valid(request_payload)),
    proposal_snapshot TEXT NOT NULL CHECK (json_valid(proposal_snapshot)),
    event_type TEXT NOT NULL CHECK (event_type IN ('V2_RESPONSE_APPROVED','V2_RESPONSE_REJECTED')),
    created_at TEXT NOT NULL
);
CREATE TRIGGER trg_response_proposal_update BEFORE UPDATE ON response_recommendations
BEGIN SELECT RAISE(ABORT, 'response proposals are append-only'); END;
CREATE TRIGGER trg_response_proposal_delete BEFORE DELETE ON response_recommendations
BEGIN SELECT RAISE(ABORT, 'response proposals are append-only'); END;
CREATE TRIGGER trg_response_proposal_replace BEFORE INSERT ON response_recommendations
WHEN EXISTS (SELECT 1 FROM response_recommendations WHERE id=NEW.id OR recommendation_ref=NEW.recommendation_ref OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'response proposals are append-only'); END;
CREATE TRIGGER trg_response_decision_update BEFORE UPDATE ON response_decisions
BEGIN SELECT RAISE(ABORT, 'response decisions are append-only'); END;
CREATE TRIGGER trg_response_decision_delete BEFORE DELETE ON response_decisions
BEGIN SELECT RAISE(ABORT, 'response decisions are append-only'); END;
CREATE TRIGGER trg_response_decision_replace BEFORE INSERT ON response_decisions
WHEN EXISTS (SELECT 1 FROM response_decisions WHERE id=NEW.id OR recommendation_id=NEW.recommendation_id OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'response decisions are append-only'); END;
