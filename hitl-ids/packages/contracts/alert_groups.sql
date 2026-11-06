-- Migration 22: grouped Tier 1 queue items (method B, analysis/phase-b/GROUPING-METHOD-REVIEW.md).
-- Every flagged flow alert joins exactly one group (same source IP, next alert within the configured window).
-- Each group is one operational alert - its first member, the representative. Append-only, like every ledger here.
CREATE TABLE alert_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_ref TEXT NOT NULL UNIQUE,
    grouping_key TEXT NOT NULL CHECK (length(trim(grouping_key)) BETWEEN 1 AND 100),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    member_count INTEGER NOT NULL CHECK (member_count >= 1),
    representative_operational_alert_id INTEGER REFERENCES operational_alerts_v2(id),
    qualifying_member_alert_id INTEGER REFERENCES alerts(id),
    case_ref TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_groups_key ON alert_groups(grouping_key, last_seen_at);
CREATE TRIGGER trg_groups_no_update BEFORE UPDATE ON alert_groups
WHEN OLD.id != NEW.id OR OLD.group_ref != NEW.group_ref OR OLD.grouping_key != NEW.grouping_key
  OR OLD.first_seen_at != NEW.first_seen_at
  OR (OLD.representative_operational_alert_id IS NOT NULL
      AND OLD.representative_operational_alert_id != NEW.representative_operational_alert_id)
  OR (OLD.qualifying_member_alert_id IS NOT NULL
      AND OLD.qualifying_member_alert_id != NEW.qualifying_member_alert_id)
  OR (OLD.case_ref IS NOT NULL AND OLD.case_ref != NEW.case_ref)
  OR OLD.created_at != NEW.created_at
BEGIN SELECT RAISE(ABORT, 'alert_groups is immutable except growing last_seen_at/member_count and one-time links'); END;
CREATE TRIGGER trg_groups_no_delete BEFORE DELETE ON alert_groups
BEGIN SELECT RAISE(ABORT, 'alert_groups is append-only'); END;
CREATE TRIGGER trg_groups_no_replace BEFORE INSERT ON alert_groups
WHEN EXISTS (SELECT 1 FROM alert_groups WHERE id=NEW.id OR group_ref=NEW.group_ref)
BEGIN SELECT RAISE(ABORT, 'alert_groups is append-only'); END;
CREATE TABLE alert_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES alert_groups(id),
    legacy_alert_id INTEGER NOT NULL UNIQUE REFERENCES alerts(id),
    source_ip TEXT NOT NULL CHECK (length(trim(source_ip)) BETWEEN 1 AND 100),
    occurred_at TEXT NOT NULL,
    joined_at TEXT NOT NULL
);
CREATE INDEX idx_group_members ON alert_group_members(group_id, occurred_at);
CREATE TRIGGER trg_group_members_no_update BEFORE UPDATE ON alert_group_members
BEGIN SELECT RAISE(ABORT, 'alert_group_members is append-only'); END;
CREATE TRIGGER trg_group_members_no_delete BEFORE DELETE ON alert_group_members
BEGIN SELECT RAISE(ABORT, 'alert_group_members is append-only'); END;
CREATE TRIGGER trg_group_members_no_replace BEFORE INSERT ON alert_group_members
WHEN EXISTS (SELECT 1 FROM alert_group_members WHERE id=NEW.id OR legacy_alert_id=NEW.legacy_alert_id)
BEGIN SELECT RAISE(ABORT, 'alert_group_members is append-only'); END;
