CREATE TABLE IF NOT EXISTS operational_routing_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    request_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('admit_tier1','approve_tier2','reject_tier2','manual_escalate')),
    event_type TEXT NOT NULL,
    expected_state_version TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
    before_state TEXT NOT NULL CHECK (json_valid(before_state)),
    after_state TEXT NOT NULL CHECK (json_valid(after_state)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routing_alert ON operational_routing_audit(operational_alert_id,id);
CREATE TRIGGER IF NOT EXISTS trg_routing_no_update BEFORE UPDATE ON operational_routing_audit
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_routing_no_delete BEFORE DELETE ON operational_routing_audit
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_routing_no_replace BEFORE INSERT ON operational_routing_audit
WHEN EXISTS (SELECT 1 FROM operational_routing_audit WHERE id=NEW.id OR request_id=NEW.request_id)
BEGIN SELECT RAISE(ABORT, 'routing audit is append-only'); END;
