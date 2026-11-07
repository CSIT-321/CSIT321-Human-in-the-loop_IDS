#!/usr/bin/env bash
# C1: run every test file that touches verdicts, escalation, the approved engine or the queue.
cd "C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids" || exit 1
F=$(grep -l -E "record_verdict|escalate_case|escalate-case|submit_feedback|/feedback|queue_page|operational_queue|/verdict" tests/test_*.py | sort -u | tr '\n' ' ')
echo "files: $(echo $F | wc -w)"
rm -rf "$LOCALAPPDATA/Temp/hitl-review/pt-c1-wide"
.venv/Scripts/python.exe -m pytest -q --tb=line -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-c1-wide" $F 2>&1 \
  | grep -E "^FAILED|^[A-Z]:.*:[0-9]+: |passed|failed" | sed -E 's#.*hitl-ids[\\/]##' | cut -c1-240 | head -30
