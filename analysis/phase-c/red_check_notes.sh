#!/usr/bin/env bash
# C6 notes red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
B="$LOCALAPPDATA/Temp/hitl-review"
S=packages/contracts/operational_alert_notes.sql
P=packages/detection/alert_notes.py
W=src/features/alert/AlertNotes.tsx
cp "$H/$S" "$B/n-sql.bak"; cp "$H/$P" "$B/n-py.bak"; cp "$H/apps/web/$W" "$B/n-web.bak"
restore() { cp "$B/n-sql.bak" "$H/$S"; cp "$B/n-py.bak" "$H/$P"; cp "$B/n-web.bak" "$H/apps/web/$W"; }
trap restore EXIT
py() { echo "$1:"; (cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-nred" tests/test_alert_notes_v2.py 2>&1 | grep -E "passed|failed|error" | tail -1); restore; }
web() { echo "$1:"; (cd "$H/apps/web" && timeout 250 npx vitest run src/features/alert/AlertNotes.test.tsx 2>&1 | grep -E "Tests "); restore; }

cd "$H"
sed -i 's/^WHEN NOT EXISTS(SELECT 1 FROM analyst_work w/WHEN 0 AND NOT EXISTS(SELECT 1 FROM analyst_work w/' "$S"; py "1. database owner guard off"
sed -i 's/^BEGIN SELECT RAISE(ABORT,.operational_alert_notes is append-only: add a new note.); END;$/BEGIN SELECT 1; END;/' "$S"; py "2. append-only guards off"
sed -i 's/^        require_owner(conn, alert_id, actor_id)$/        pass/' "$P"; py "3. Python owner check removed"
sed -i "s/            if prior\['actor_id'\] != actor_id or prior\['operational_alert_id'\] != alert_id:/            if False:/" "$P"; py "4. request id reuse across alerts allowed"
sed -i 's/        value = value.strip()/        value = value/' "$P"; py "5. body not trimmed"
sed -i "s/'SELECT \* FROM operational_alert_notes WHERE operational_alert_id=? ORDER BY id'/'SELECT * FROM operational_alert_notes WHERE operational_alert_id=? ORDER BY id DESC'/" "$P"; py "6. newest first"
cd "$H/apps/web"
sed -i 's/const owner = Boolean(work \&\& work.status === "in_review" \&\& work.isOwner);/const owner = Boolean(work);/' "$W"; web "7. add form for non-owners"
sed -i 's/      pending.current = null; setText("");/      setText("");/' "$W"; web "8. request id kept after success"
sed -i 's/    if (!pending.current || pending.current.body !== body) pending.current/    pending.current/' "$W"; web "9. new request id on retry"
sed -i 's/const ready = !busy \&\& body !== "" \&\& body.length <= MAX;/const ready = !busy \&\& body !== "";/' "$W"; web "10. over 2000 characters allowed"
echo "restored:"
(cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-nred" tests/test_alert_notes_v2.py 2>&1 | grep -E "passed|failed" | tail -1)
(cd "$H/apps/web" && timeout 250 npx vitest run src/features/alert/AlertNotes.test.tsx 2>&1 | grep -E "Tests ")
