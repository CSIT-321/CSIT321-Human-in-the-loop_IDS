#!/usr/bin/env bash
# C7 red check: each planted defect must fail at least one test in test_work_release.py.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
cd "$H"
W=packages/detection/analyst_work.py
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red-c7" tests/test_work_release.py tests/test_api_contract.py 2>&1 | grep -E "passed|failed|error" | tail -1; }
mutate() { cp "$1" "$1.orig"; .venv/Scripts/python.exe - "$1" "$2" "$3" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert old in s, old; open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
EOF
}
restore() { mv "$1.orig" "$1"; }

echo "1. any analyst may release another's claim:"
mutate $W "else: raise WorkConflict(f\"This alert is currently being reviewed by {work['owner_name']}.\")" "else: released_by='owner'"; run; restore $W
echo "2. administrator release without a reason:"
mutate $W "if reason is None: raise ValueError('An administrator release needs a reason.')" "pass"; run; restore $W
echo "3. release writes no audit event (the trigger must stop it):"
mutate $W "    _event(conn,alert_id,'WORK_RELEASED'" "    (lambda *a, **k: None)(conn,alert_id,'WORK_RELEASED'"; run; restore $W
echo "4. a read expires the claim (side effect on GET):"
mutate $W "    idle_other=bool(tier1 and not owned and _idle(work))" "    idle_other=bool(tier1 and not owned and _idle(work)) and _expire_if_idle(conn,alert_id)"; run; restore $W
echo "5. expiry after 1 minute instead of the policy:"
mutate $W "timedelta(minutes=expiry_policy()['claimIdleExpiryMinutes'])" "timedelta(minutes=1)"; run; restore $W
echo "6. no idempotency (a retry writes a second event):"
mutate $W "        if prior:" "        if False:"; run; restore $W
echo "7. stale revision accepted:"
mutate $W "if work['revision']!=request.expected_revision: raise WorkConflict('Work changed; refresh before releasing.')" "pass"; run; restore $W
echo "restored:"; run
git status -s packages | grep -v -E "^ M packages/(detection/analyst_work|contracts/db)\.py$|^\?\? packages/contracts/work_release\.sql$" || true
