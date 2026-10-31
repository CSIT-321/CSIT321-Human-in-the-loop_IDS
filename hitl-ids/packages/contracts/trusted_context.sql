CREATE TABLE trusted_context_facts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 fact_ref TEXT NOT NULL UNIQUE,
 actor_id INTEGER REFERENCES users(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload)),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot))
);
CREATE TABLE triage_context_provenance (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 policy_audit_id INTEGER NOT NULL UNIQUE REFERENCES operational_triage_policy_audit(id),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot))
);
CREATE TRIGGER context_fact_update BEFORE UPDATE ON trusted_context_facts BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
CREATE TRIGGER context_fact_delete BEFORE DELETE ON trusted_context_facts BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
CREATE TRIGGER context_fact_replace BEFORE INSERT ON trusted_context_facts WHEN EXISTS(SELECT 1 FROM trusted_context_facts WHERE id=NEW.id OR fact_ref=NEW.fact_ref OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
CREATE TRIGGER context_audit_update BEFORE UPDATE ON triage_context_provenance BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
CREATE TRIGGER context_audit_delete BEFORE DELETE ON triage_context_provenance BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
CREATE TRIGGER context_audit_replace BEFORE INSERT ON triage_context_provenance WHEN EXISTS(SELECT 1 FROM triage_context_provenance WHERE id=NEW.id OR policy_audit_id=NEW.policy_audit_id) BEGIN SELECT RAISE(ABORT,'context history is append-only'); END;
