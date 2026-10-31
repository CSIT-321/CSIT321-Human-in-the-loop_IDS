CREATE TABLE external_eligibility_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_inbox_id INTEGER NOT NULL REFERENCES external_alert_inbox(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    request_id TEXT NOT NULL UNIQUE,
    expected_review_id INTEGER REFERENCES external_eligibility_review(id),
    decision TEXT NOT NULL CHECK (decision IN ('accepted','held')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
    evidence_digest TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_external_review ON external_eligibility_review(external_inbox_id,id);
CREATE TRIGGER trg_external_review_update BEFORE UPDATE ON external_eligibility_review
BEGIN SELECT RAISE(ABORT, 'eligibility review is append-only'); END;
CREATE TRIGGER trg_external_review_delete BEFORE DELETE ON external_eligibility_review
BEGIN SELECT RAISE(ABORT, 'eligibility review is append-only'); END;
CREATE TRIGGER trg_external_review_replace BEFORE INSERT ON external_eligibility_review
WHEN EXISTS (SELECT 1 FROM external_eligibility_review WHERE id=NEW.id OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'eligibility review is append-only'); END;

CREATE TABLE external_operational_admission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_inbox_id INTEGER NOT NULL UNIQUE REFERENCES external_alert_inbox(id),
    operational_alert_id INTEGER NOT NULL UNIQUE REFERENCES operational_alerts_v2(id),
    canonical_alert_id TEXT NOT NULL,
    actor_id INTEGER NOT NULL REFERENCES users(id),
    review_id INTEGER NOT NULL REFERENCES external_eligibility_review(id),
    request_id TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
    event_type TEXT NOT NULL CHECK (event_type='V2_EXTERNAL_ALERT_ADMITTED'),
    policy_audit_id INTEGER NOT NULL REFERENCES operational_triage_policy_audit(id),
    routing_audit_id INTEGER NOT NULL REFERENCES operational_routing_audit(id),
    context_snapshot TEXT NOT NULL CHECK (json_valid(context_snapshot)),
    resulting_state TEXT NOT NULL CHECK (json_valid(resulting_state)),
    created_at TEXT NOT NULL
);
CREATE TRIGGER trg_external_admission_update BEFORE UPDATE ON external_operational_admission
BEGIN SELECT RAISE(ABORT, 'external admission is append-only'); END;
CREATE TRIGGER trg_external_admission_delete BEFORE DELETE ON external_operational_admission
BEGIN SELECT RAISE(ABORT, 'external admission is append-only'); END;
CREATE TRIGGER trg_external_admission_replace BEFORE INSERT ON external_operational_admission
WHEN EXISTS (SELECT 1 FROM external_operational_admission
             WHERE id=NEW.id OR external_inbox_id=NEW.external_inbox_id
             OR operational_alert_id=NEW.operational_alert_id OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'external admission is append-only'); END;
