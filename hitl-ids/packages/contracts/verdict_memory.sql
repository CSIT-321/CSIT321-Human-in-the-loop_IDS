CREATE TABLE verdict_memory_contributions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 source_verdict_ref TEXT NOT NULL UNIQUE REFERENCES analyst_verdict_events(verdict_ref),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 scope TEXT NOT NULL CHECK(scope IN ('exact','narrow')),
 primary_lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 request_id TEXT NOT NULL UNIQUE,
 request_payload TEXT NOT NULL CHECK(json_valid(request_payload))
);
CREATE TABLE verdict_memory_evidence (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 contribution_id INTEGER NOT NULL REFERENCES verdict_memory_contributions(id),
 lesson_id INTEGER NOT NULL REFERENCES triage_memory_lessons(id),
 evidence_snapshot TEXT NOT NULL CHECK(json_valid(evidence_snapshot)),
 UNIQUE(contribution_id,lesson_id)
);
CREATE INDEX verdict_memory_source ON verdict_memory_contributions(source_alert_id,id);
CREATE INDEX verdict_memory_lesson ON verdict_memory_evidence(lesson_id,id);
CREATE TRIGGER vm_contribution_update BEFORE UPDATE ON verdict_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_contribution_delete BEFORE DELETE ON verdict_memory_contributions BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_contribution_replace BEFORE INSERT ON verdict_memory_contributions WHEN EXISTS(SELECT 1 FROM verdict_memory_contributions WHERE id=NEW.id OR source_verdict_ref=NEW.source_verdict_ref OR request_id=NEW.request_id) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_evidence_update BEFORE UPDATE ON verdict_memory_evidence BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_evidence_delete BEFORE DELETE ON verdict_memory_evidence BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
CREATE TRIGGER vm_evidence_replace BEFORE INSERT ON verdict_memory_evidence WHEN EXISTS(SELECT 1 FROM verdict_memory_evidence WHERE id=NEW.id OR (contribution_id=NEW.contribution_id AND lesson_id=NEW.lesson_id)) BEGIN SELECT RAISE(ABORT,'memory provenance is immutable'); END;
