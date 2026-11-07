#!/usr/bin/env bash
# Queue order (D4 condition 2) red check: each planted defect must fail at least one test.
set -u
H="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids"
cd "$H"
Q=apps/api/operational_queue.py
T="tests/test_flow_routing.py::test_a_high_scoring_unflagged_item_still_ranks_below_every_group tests/test_flow_routing.py::test_unflagged_items_rank_below_every_group tests/test_operational_queue.py"
run() { .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-red-q" $T 2>&1 | grep -E "passed|failed|error" | tail -1; }
mutate() { cp "$1" "$1.orig"; .venv/Scripts/python.exe - "$1" "$2" "$3" <<'EOF'
import sys; p, old, new = sys.argv[1:]; s = open(p, encoding="utf-8").read()
assert s.count(old) == 1, old; open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
EOF
}
restore() { mv "$1.orig" "$1"; }

echo "1. tier key removed (score only, the old order):"
mutate $Q 'QUEUE_ORDER = f"{UNFLAGGED_LAST} ASC, ' 'QUEUE_ORDER = f"'; run; restore $Q
echo "2. tier key reversed (unflagged first):"
mutate $Q 'QUEUE_ORDER = f"{UNFLAGGED_LAST} ASC' 'QUEUE_ORDER = f"{UNFLAGGED_LAST} DESC'; run; restore $Q
echo "3. only the unfiltered path uses the rule:"
mutate $Q "            ORDER BY {QUEUE_ORDER}''', params).fetchall()" "            ORDER BY {VALID_PRIORITY} DESC''', params).fetchall()"; run; restore $Q
echo "4. tier key after the score:"
mutate $Q 'QUEUE_ORDER = f"{UNFLAGGED_LAST} ASC, {VALID_PRIORITY} DESC, ' 'QUEUE_ORDER = f"{VALID_PRIORITY} DESC, {UNFLAGGED_LAST} ASC, '; run; restore $Q
echo "restored:"; run
git status -s apps | grep -v -E "^ M apps/api/operational_queue\.py$" || true
