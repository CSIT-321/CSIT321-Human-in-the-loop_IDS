#!/usr/bin/env bash
# Admin claimed-alerts list red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
B="$LOCALAPPDATA/Temp/hitl-review"
W=src/pages/admin/ClaimedAlerts.tsx
Q=apps/api/operational_queue.py
cp "$H/apps/web/$W" "$B/ca-web.bak"; cp "$H/$Q" "$B/ca-q.bak"
restore() { cp "$B/ca-web.bak" "$H/apps/web/$W"; cp "$B/ca-q.bak" "$H/$Q"; }
trap restore EXIT
web() { echo "$1:"; (cd "$H/apps/web" && timeout 250 npx vitest run src/pages/admin/ClaimedAlerts.test.tsx src/pages/admin/CurrentAdmin.test.tsx 2>&1 | grep -E "Tests "); restore; }
py() { echo "$1:"; (cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-cared" tests/test_work_release.py 2>&1 | grep -E "passed|failed" | tail -1); restore; }

cd "$H/apps/web"
sed -i 's/workScope: "in_review"/workScope: "active"/' "$W"; web "1. asks for all active alerts"
sed -i 's/{work?.canRelease \&\& <div/{work \&\& <div/' "$W"; web "2. button shown without canRelease"
sed -i 's/onReleased={() => { resource.reload(); onReleased?.(); }}/onReleased={() => {}}/' "$W"; web "3. list not reloaded after a release"
sed -i 's/{work?.idle \&\& <span/{false \&\& <span/' "$W"; web "4. idle not shown"
sed -i 's/resource.data.page.total > resource.data.items.length \&\&/false \&\&/' "$W"; web "5. partial list not stated"
cd "$H"
sed -i "s/elif work_scope in ('completed','escalated','in_review'):/elif work_scope in ('completed','escalated'):/" "$Q"; py "6. in_review scope not filtered"
echo "restored:"; (cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-cared" tests/test_work_release.py 2>&1 | grep -E "passed|failed" | tail -1)
(cd "$H/apps/web" && timeout 250 npx vitest run src/pages/admin/ClaimedAlerts.test.tsx src/pages/admin/CurrentAdmin.test.tsx 2>&1 | grep -E "Tests ")
