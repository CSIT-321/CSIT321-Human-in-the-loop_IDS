#!/usr/bin/env bash
# Release button red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
B="$LOCALAPPDATA/Temp/hitl-review"
W=src/features/alert/AnalystWork.tsx
P=packages/detection/analyst_work.py
cp "$H/apps/web/$W" "$B/rel-web.bak"; cp "$H/$P" "$B/rel-py.bak"
restore() { cp "$B/rel-web.bak" "$H/apps/web/$W"; cp "$B/rel-py.bak" "$H/$P"; }
trap restore EXIT
web() { echo "$1:"; (cd "$H/apps/web" && timeout 250 npx vitest run src/features/alert/AnalystWork src/pages/analyst/AutoClaimWorkstation.test.tsx 2>&1 | grep -E "Tests "); restore; }
py() { echo "$1:"; (cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-relred" tests/test_work_release.py 2>&1 | grep -E "passed|failed" | tail -1); restore; }

cd "$H/apps/web"
sed -i 's/const ready = !busy \&\& (!admin || trimmed !== "");/const ready = !busy;/' "$W"
web "1. admin can release without a reason"
sed -i 's/if (!pending.current || pending.current.reason !== sent) pending.current/pending.current/' "$W"
web "2. a retry gets a new request id"
sed -i 's/expectedRevision: work.revision,/expectedRevision: 0,/' "$W"
web "3. revision not sent"
sed -i 's/{!starting \&\& work.canRelease \&\& alertRef/{!starting \&\& alertRef/' "$W"
web "4. button shown without canRelease"
sed -i 's/pending.current = null; setOpen(false); setReason("");/setOpen(false);/; s/      onReleased(result.work);//' "$W"
web "5. caller not told about the release"
sed -i 's/{work.idle \&\& <span/{false \&\& <span/' "$W"
web "6. idle claim not marked"

cd "$H"
sed -i 's/admin_release=bool(permitted and in_review and not owned and actor.role==.system_admin.)/admin_release=bool(permitted and in_review and not owned)/' "$P"
py "7. any analyst may release another's claim (view)"
sed -i 's/release_reason_required=admin_release,/release_reason_required=False,/' "$P"
py "8. admin reason not flagged as required"
sed -i 's/idle=in_review and _idle(work),/idle=False,/' "$P"
py "9. idle never reported"
echo "restored:"; (cd "$H" && .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$B/pt-relred" tests/test_work_release.py 2>&1 | grep -E "passed|failed" | tail -1)
(cd "$H/apps/web" && timeout 250 npx vitest run src/features/alert/AnalystWork src/pages/analyst/AutoClaimWorkstation.test.tsx 2>&1 | grep -E "Tests ")
