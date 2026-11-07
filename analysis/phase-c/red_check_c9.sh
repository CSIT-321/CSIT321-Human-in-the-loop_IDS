#!/usr/bin/env bash
# C9 red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
cd "$H"
Q=apps/api/operational_queue.py
S=packages/detection/queue_severity.py
T="tests/test_queue_severity.py tests/test_operational_queue.py tests/test_flow_routing.py::test_a_high_scoring_unflagged_item_still_ranks_below_every_group"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red-c9" $T 2>&1 | grep -E "passed|failed|error" | tail -1; }
mutate() { cp "$1" "$1.orig"; .venv/Scripts/python.exe - "$1" "$2" "$3" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert s.count(old) == 1, old; open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
EOF
}
restore() { mv "$1.orig" "$1"; }

echo "1. severity key removed:"
mutate $Q 'QUEUE_ORDER = (f"{SEVERITY} DESC, ' 'QUEUE_ORDER = (f"'; run; restore $Q
echo "2. severity after the flagged tier:"
mutate $Q '{SEVERITY} DESC, {UNFLAGGED_LAST} ASC' '{UNFLAGGED_LAST} ASC, {SEVERITY} DESC'; run; restore $Q
echo "3. Suricata alerts ignore the chart (priority only):"
mutate $S '    if chart is not None:
        return chart' '    pass'; run; restore $S
echo "4. unknown classtype treated as Critical:"
mutate $S 'PRIORITY_FALLBACK.get(_priority(native_severity), "Informational")' '"Critical"'; run; restore $S
echo "5. priority 1 fallback = Critical:"
mutate $S 'PRIORITY_FALLBACK = {1: "High"' 'PRIORITY_FALLBACK = {1: "Critical"'; run; restore $S
echo "6. flagged tier dropped inside a level:"
mutate $Q '{SEVERITY} DESC, {UNFLAGGED_LAST} ASC, ' '{SEVERITY} DESC, '; run; restore $Q
echo "restored:"; run
