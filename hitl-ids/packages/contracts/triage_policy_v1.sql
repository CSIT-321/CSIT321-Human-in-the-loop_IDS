ALTER TABLE operational_triage_state_v2 ADD COLUMN priority_band_scheme TEXT NOT NULL
    DEFAULT 'legacy_labels' CHECK (priority_band_scheme IN ('legacy_labels', 'p1_p4'));
CREATE TABLE operational_triage_policy_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    policy_version TEXT NOT NULL,
    policy_snapshot TEXT NOT NULL CHECK (json_valid(policy_snapshot)),
    context_snapshot TEXT NOT NULL CHECK (json_valid(context_snapshot)),
    result_snapshot TEXT NOT NULL CHECK (json_valid(result_snapshot)),
    before_state TEXT NOT NULL CHECK (json_valid(before_state)),
    after_state TEXT NOT NULL CHECK (json_valid(after_state)),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_triage_policy_audit_alert ON operational_triage_policy_audit (operational_alert_id, id);
CREATE TRIGGER trg_triage_policy_audit_no_update BEFORE UPDATE ON operational_triage_policy_audit
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
CREATE TRIGGER trg_triage_policy_audit_no_delete BEFORE DELETE ON operational_triage_policy_audit
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
CREATE TRIGGER trg_triage_policy_audit_no_replace BEFORE INSERT ON operational_triage_policy_audit
WHEN EXISTS (SELECT 1 FROM operational_triage_policy_audit WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'V2 policy audit is append-only'); END;
