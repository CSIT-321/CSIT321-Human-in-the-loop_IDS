-- Migration 25 (C6, decision Q7 option A, approved 2026-11-08): Tier 1 investigation notes on the V2 operational
-- alert. One table for flow and Suricata alerts alike.
--
-- Append-only: no update, no delete, no replace. Owner-guarded in the database: a note is accepted only from the
-- analyst who holds the claim (analyst_work In Review) at insert time, so a write that bypasses
-- `alert_notes.add_note` still fails. The notes stay after the claim ends. request_id makes a retry a no-op.
CREATE TABLE operational_alert_notes (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 operational_alert_id INTEGER NOT NULL REFERENCES operational_alerts_v2(id),
 actor_id INTEGER NOT NULL REFERENCES users(id),
 actor_name TEXT NOT NULL,
 body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 2000),
 request_id TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL
);
CREATE INDEX idx_operational_alert_notes_alert ON operational_alert_notes(operational_alert_id, id);
CREATE TRIGGER operational_note_owner BEFORE INSERT ON operational_alert_notes
WHEN NOT EXISTS(SELECT 1 FROM analyst_work w WHERE w.operational_alert_id=NEW.operational_alert_id
 AND w.status='in_review' AND w.owner_actor_id=NEW.actor_id)
BEGIN SELECT RAISE(ABORT,'only the claim owner can add a note'); END;
CREATE TRIGGER operational_note_no_update BEFORE UPDATE ON operational_alert_notes
BEGIN SELECT RAISE(ABORT,'operational_alert_notes is append-only: add a new note'); END;
CREATE TRIGGER operational_note_no_delete BEFORE DELETE ON operational_alert_notes
BEGIN SELECT RAISE(ABORT,'operational_alert_notes is append-only: add a new note'); END;
CREATE TRIGGER operational_note_no_replace BEFORE INSERT ON operational_alert_notes
WHEN NEW.id IS NOT NULL AND EXISTS(SELECT 1 FROM operational_alert_notes WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT,'operational_alert_notes is append-only: add a new note'); END;
