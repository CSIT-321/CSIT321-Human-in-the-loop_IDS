-- Canonical SQLite schema for the HITL IDS demo (plan step S2).
--
-- Twelve of the TDM's thirteen tables; `notifications` is deferred with the full backend (S18).
-- One table the TDM lacks, `alert_families` (S7b, similar-alert learning), is marked DEVIATION.
-- Column names are the TDM §7.2 names so the PostgreSQL migration is mechanical.
-- Type mapping: BIGINT/INT AUTO_INCREMENT -> INTEGER PRIMARY KEY AUTOINCREMENT · VARCHAR, UUID
-- -> TEXT · DECIMAL -> NUMERIC · BOOLEAN -> INTEGER 0/1 · TIMESTAMP -> TEXT, fixed-width ISO-8601
-- UTC 'YYYY-MM-DDTHH:MM:SS.ffffffZ' so text order is time order (db.format_timestamp)
-- · JSONB -> TEXT CHECK (json_valid(...)).
-- Departures from the TDM are marked DEVIATION and logged in docs/plan-changelog.md v1.5 (S7b's in
-- v1.14).
-- Foreign keys are enforced only on connections that run PRAGMA foreign_keys = ON; use
-- packages.contracts.db.connect().

CREATE TABLE users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT    NOT NULL UNIQUE,
    password_hash     TEXT    NOT NULL,
    display_name      TEXT    NOT NULL,
    email             TEXT    NOT NULL,
    role              TEXT    NOT NULL CHECK (role IN ('security_analyst', 'system_admin', 'evaluator')),
    status            TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    last_login        TEXT,
    require_pw_change INTEGER NOT NULL DEFAULT 0 CHECK (require_pw_change IN (0, 1)),
    one_time_pw       TEXT
);

CREATE TABLE datasets (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL,
    version            TEXT    NOT NULL,
    source_file        TEXT    NOT NULL,
    preparation_meta   TEXT    CHECK (json_valid(preparation_meta)),
    total_records      INTEGER NOT NULL CHECK (total_records >= 0),
    class_distribution TEXT    NOT NULL CHECK (json_valid(class_distribution)),
    is_held_out        INTEGER NOT NULL DEFAULT 0 CHECK (is_held_out IN (0, 1)),
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    created_by         INTEGER REFERENCES users (id)
);

CREATE TABLE signature_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- DEVIATION: TDM VARCHAR(20) cannot hold the frozen legacy ids (SIG-DOS-HIGH-RATE-FLOW is 22).
    rule_id         TEXT    NOT NULL CHECK (length(rule_id) BETWEEN 1 AND 50),
    name            TEXT    NOT NULL,
    severity        TEXT    NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low')),
    conditions      TEXT    NOT NULL CHECK (json_valid(conditions) AND json_type(conditions) = 'object'),
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    -- DEVIATION: the attack class a match asserts; corroboration compares it with the ML class.
    attack_category TEXT    NOT NULL CHECK (attack_category <> 'Benign'),
    -- DEVIATION: the human-checkable reason for the rule (the signature layer is the trust half).
    rationale       TEXT,
    -- DEVIATION: the TDM has UNIQUE (rule_id). A rule must exist in several versions so a
    -- detection run can be replayed against the rule_set_version it recorded.
    UNIQUE (rule_id, version)
);

CREATE TABLE ml_models (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version    TEXT    NOT NULL UNIQUE,
    model_type TEXT    NOT NULL,
    f1_score   NUMERIC CHECK (f1_score BETWEEN 0 AND 1),
    precision  NUMERIC CHECK (precision BETWEEN 0 AND 1),
    recall     NUMERIC CHECK (recall BETWEEN 0 AND 1),
    model_file TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'available' CHECK (status IN ('active', 'available', 'archived')),
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
);

CREATE TABLE detection_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id       INTEGER NOT NULL REFERENCES datasets (id),
    -- DEVIATION: FK added (TDM has a bare VARCHAR); ml_models.version is UNIQUE.
    model_version    TEXT    NOT NULL REFERENCES ml_models (version),
    rule_set_version TEXT    NOT NULL,
    -- Holds the fusion configuration snapshot. Weighted-sum fusion was rejected; the TDM column
    -- name is kept for the migration.
    fusion_weights   TEXT    NOT NULL CHECK (json_valid(fusion_weights) AND json_type(fusion_weights) = 'object'),
    guardrail_config TEXT    NOT NULL CHECK (json_valid(guardrail_config) AND json_type(guardrail_config) = 'object'),
    status           TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'aborted')),
    alert_count      INTEGER NOT NULL DEFAULT 0 CHECK (alert_count >= 0),
    started_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    completed_at     TEXT,
    -- DEVIATION: S9's run_detection(..., seed) must be reproducible from this row alone.
    seed             INTEGER
);

CREATE TABLE alerts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_ref          TEXT    NOT NULL UNIQUE CHECK (length(alert_ref) = 36),
    dataset_id         INTEGER NOT NULL REFERENCES datasets (id),
    run_id             INTEGER NOT NULL REFERENCES detection_runs (id),
    combined_score     NUMERIC NOT NULL CHECK (combined_score BETWEEN 0 AND 100),
    severity           TEXT    NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low', 'Informational')),
    confidence         NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    signature_severity NUMERIC CHECK (signature_severity BETWEEN 0 AND 1),
    ml_probability     NUMERIC CHECK (ml_probability BETWEEN 0 AND 1),
    signature_rules    TEXT    CHECK (json_valid(signature_rules) AND json_type(signature_rules) = 'array'),
    ml_predicted_class TEXT,
    attack_category    TEXT,
    shap_attributions  TEXT    CHECK (json_valid(shap_attributions) AND json_type(shap_attributions) = 'object'),
    explanation        TEXT    NOT NULL CHECK (length(explanation) > 0),
    status             TEXT    NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'claimed', 'in_progress', 'resolved', 'dismissed')),
    owner_id           INTEGER REFERENCES users (id),
    is_duplicate_of    INTEGER REFERENCES alerts (id) CHECK (is_duplicate_of <> id),
    is_critical        INTEGER NOT NULL DEFAULT 0 CHECK (is_critical IN (0, 1)),
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    updated_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    -- DEVIATION: immutable detection score; combined_score is the operational score feedback moves.
    detection_score    NUMERIC NOT NULL CHECK (detection_score BETWEEN 0 AND 100),
    -- DEVIATION (plan v1.0): load-bearing — the queue orders by these.
    evidence_class     TEXT    NOT NULL CHECK (evidence_class IN ('corroborated', 'signature_override', 'ml_only', 'none')),
    evidence_priority  INTEGER NOT NULL CHECK (evidence_priority >= 0),
    -- DEVIATION: raised by fusion (S6) or by feedback and guardrails (S7).
    requires_review    INTEGER NOT NULL DEFAULT 0 CHECK (requires_review IN (0, 1)),
    -- DEVIATION (S7b): the queue band the alert sits in now; the queue orders by queue_priority.
    -- Detection places the alert in its evidence class's band or the Tier 2 band, and analyst
    -- feedback moves it (Q24). evidence_class never changes.
    queue_class        TEXT    NOT NULL CHECK (queue_class IN ('tier2_candidate', 'corroborated', 'signature_override', 'ml_only', 'none')),
    queue_priority     INTEGER NOT NULL,
    -- DEVIATION (S7b): the similar-alert family; NULL keeps the alert out of similar-alert learning.
    family_key         TEXT    CHECK (json_valid(family_key) AND json_type(family_key) = 'array'),
    -- Evidence class must agree with which detectors fired. Repeated from the Pydantic model so
    -- raw-SQL writers cannot bypass it.
    CHECK ((evidence_class IN ('corroborated', 'signature_override'))
           = (COALESCE(json_array_length(signature_rules), 0) > 0)),
    CHECK (evidence_class NOT IN ('corroborated', 'ml_only')
           OR (ml_predicted_class IS NOT NULL AND ml_predicted_class <> 'Benign')),
    -- The priority is the band's; repeated from the Pydantic model, like the checks above.
    CHECK (queue_priority = CASE queue_class WHEN 'tier2_candidate' THEN 0 WHEN 'corroborated' THEN 1
                                             WHEN 'signature_override' THEN 2 WHEN 'ml_only' THEN 3
                                             ELSE 4 END),
    -- I3: a rule the model disputes never leaves its band.
    CHECK (evidence_class <> 'signature_override' OR queue_class = 'signature_override')
);

CREATE TABLE flow_data (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id         INTEGER NOT NULL UNIQUE REFERENCES alerts (id),
    src_ip           TEXT    NOT NULL,
    dst_ip           TEXT    NOT NULL,
    src_port         INTEGER NOT NULL CHECK (src_port BETWEEN 0 AND 65535),
    dst_port         INTEGER NOT NULL CHECK (dst_port BETWEEN 0 AND 65535),
    protocol         TEXT    NOT NULL,
    duration         NUMERIC NOT NULL CHECK (duration >= 0),
    packets          INTEGER NOT NULL CHECK (packets >= 0),
    bytes            INTEGER NOT NULL CHECK (bytes >= 0),
    flow_features    TEXT    NOT NULL CHECK (json_valid(flow_features) AND json_type(flow_features) = 'object'),
    -- DEVIATION: the flow's id in its source dataset — the only join key to ground truth, which
    -- is kept out of this schema entirely (label leakage).
    source_record_id TEXT    NOT NULL
);

CREATE TABLE feedback_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id         INTEGER NOT NULL REFERENCES alerts (id),
    user_id          INTEGER NOT NULL REFERENCES users (id),
    -- DEVIATION: the engine's five categories (stage-5/core/feedback-engine.js), not the TDM's
    -- six. `duplicate` is a queue action recorded in alerts.is_duplicate_of.
    category         TEXT    NOT NULL CHECK (category IN ('confirm_true_positive', 'mark_false_positive',
                                                         'mark_expected_activity', 'needs_investigation',
                                                         'escalate')),
    note             TEXT,
    original_score   NUMERIC NOT NULL CHECK (original_score BETWEEN 0 AND 100),
    requested_delta  NUMERIC NOT NULL,
    actual_delta     NUMERIC NOT NULL,
    guardrail_action TEXT    NOT NULL CHECK (guardrail_action IN ('applied', 'capped', 'rejected')),
    guardrail_reason TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    amended_from_id  INTEGER REFERENCES feedback_events (id),
    CHECK (guardrail_action <> 'applied'  OR actual_delta = requested_delta),
    CHECK (guardrail_action <> 'capped'   OR actual_delta <> requested_delta),
    CHECK (guardrail_action <> 'rejected' OR actual_delta = 0),
    CHECK (guardrail_action = 'applied'   OR guardrail_reason IS NOT NULL)
);

-- DEVIATION (S7b): similar-alert learning, one row per family (docs/plan-changelog.md v1.14); the
-- TDM has no such table. Derived state: packages/detection/feedback/service.py recomputes a row
-- from the family's effective verdicts after every verdict, so rows are updated in place, and each
-- change is also written to audit_log as SIMILAR_ALERT_LEARNING.
CREATE TABLE alert_families (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    family_key         TEXT    NOT NULL UNIQUE CHECK (json_valid(family_key) AND json_type(family_key) = 'array'),
    attack_category    TEXT,
    scheme             TEXT    NOT NULL,
    severity_version   TEXT    NOT NULL,
    weight             NUMERIC NOT NULL CHECK (weight BETWEEN 0 AND 1),
    feedback_counts    TEXT    NOT NULL CHECK (json_valid(feedback_counts) AND json_type(feedback_counts) = 'object'),
    dominant_category  TEXT    CHECK (dominant_category IN ('confirm_true_positive', 'mark_false_positive', 'mark_expected_activity')),
    agreement_ratio    NUMERIC NOT NULL CHECK (agreement_ratio BETWEEN 0 AND 1),
    gate_open          INTEGER NOT NULL CHECK (gate_open IN (0, 1)),
    gate_reason        TEXT    NOT NULL,
    learned_adjustment NUMERIC NOT NULL,
    learned_offset     INTEGER NOT NULL,
    applied_adjustment NUMERIC NOT NULL,
    applied_offset     INTEGER NOT NULL,
    updated_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    CHECK (gate_open = 1 OR (applied_adjustment = 0 AND applied_offset = 0))
);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    actor_id    INTEGER REFERENCES users (id),
    alert_id    INTEGER REFERENCES alerts (id),
    feedback_id INTEGER REFERENCES feedback_events (id),
    details     TEXT    NOT NULL CHECK (json_valid(details) AND json_type(details) = 'object'),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
);

CREATE TABLE guardrail_config (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key   TEXT    NOT NULL UNIQUE,
    config_value NUMERIC NOT NULL,
    description  TEXT,
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
);

CREATE TABLE evaluation_scenarios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    dataset_id        INTEGER NOT NULL REFERENCES datasets (id),
    -- DEVIATION: FK added, as on detection_runs.
    model_version     TEXT    NOT NULL REFERENCES ml_models (version),
    rule_set_version  TEXT    NOT NULL,
    feedback_sequence TEXT    NOT NULL CHECK (json_valid(feedback_sequence) AND json_type(feedback_sequence) = 'array'),
    metrics_config    TEXT    NOT NULL CHECK (json_valid(metrics_config) AND json_type(metrics_config) = 'object'),
    guardrails_active INTEGER NOT NULL DEFAULT 1 CHECK (guardrails_active IN (0, 1)),
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z')
);

CREATE TABLE evaluation_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id      INTEGER NOT NULL REFERENCES evaluation_scenarios (id),
    status           TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    metrics          TEXT    CHECK (json_valid(metrics)),
    fpr_reduction    NUMERIC,
    rank_improvement NUMERIC,
    guardrail_pass   INTEGER CHECK (guardrail_pass IN (0, 1)),
    usability_data   TEXT    CHECK (json_valid(usability_data)),
    started_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z'),
    completed_at     TEXT
);

-- Indexes (TDM §7.3, plus the queue index).
CREATE INDEX idx_alerts_score      ON alerts (combined_score DESC);
CREATE INDEX idx_alerts_status     ON alerts (status);
CREATE INDEX idx_alerts_severity   ON alerts (severity);
CREATE INDEX idx_alerts_created    ON alerts (created_at);
CREATE INDEX idx_alerts_owner      ON alerts (owner_id);
CREATE INDEX idx_alerts_run        ON alerts (run_id);
-- DEVIATION: serves QUEUE_ORDER_BY in packages/contracts/db.py (queue_priority since S7b).
CREATE INDEX idx_alerts_queue      ON alerts (queue_priority, combined_score DESC);
-- DEVIATION (S7b): a verdict re-places its family's members.
CREATE INDEX idx_alerts_family     ON alerts (family_key);
CREATE INDEX idx_feedback_alert    ON feedback_events (alert_id);
CREATE INDEX idx_feedback_user     ON feedback_events (user_id);
CREATE INDEX idx_audit_created     ON audit_log (created_at DESC);
CREATE INDEX idx_audit_event_type  ON audit_log (event_type);
CREATE INDEX idx_audit_actor       ON audit_log (actor_id);

-- Append-only enforcement (TDM §7.2.8, NFR-02/03).
-- The no_replace triggers close a gap the TDM's UPDATE/DELETE pair leaves open in SQLite:
-- INSERT OR REPLACE deletes the conflicting row without firing DELETE triggers unless
-- recursive_triggers is on, so the insert itself is refused on every connection.
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: modifications are not permitted'); END;

CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: modifications are not permitted'); END;

CREATE TRIGGER trg_audit_no_replace BEFORE INSERT ON audit_log
WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM audit_log WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: modifications are not permitted'); END;

-- DEVIATION: feedback is append-only too. The TDM's amended_from_id already models amendment
-- as a new row; enforcing it keeps every guardrail decision reconstructable.
CREATE TRIGGER trg_feedback_no_update BEFORE UPDATE ON feedback_events
BEGIN SELECT RAISE(ABORT, 'feedback_events is append-only: amend with a new row'); END;

CREATE TRIGGER trg_feedback_no_delete BEFORE DELETE ON feedback_events
BEGIN SELECT RAISE(ABORT, 'feedback_events is append-only: amend with a new row'); END;

CREATE TRIGGER trg_feedback_no_replace BEFORE INSERT ON feedback_events
WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM feedback_events WHERE id = NEW.id)
BEGIN SELECT RAISE(ABORT, 'feedback_events is append-only: amend with a new row'); END;
