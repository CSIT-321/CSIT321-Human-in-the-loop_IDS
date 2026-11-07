#!/usr/bin/env bash
# Run every test file that touches the operational queue, plus the C9 severity tests.
cd "C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids" || exit 1
F="tests/test_queue_severity.py $(grep -l -E "queue_page|/api/v2/alerts'|/api/v2/alerts\"|operational_queue" tests/test_*.py | tr '\n' ' ')"
echo "files: $F"
rm -rf "$LOCALAPPDATA/Temp/hitl-review/pt-sev4"
.venv/Scripts/python.exe -m pytest -q --tb=line -p no:cacheprovider --basetemp="$LOCALAPPDATA/Temp/hitl-review/pt-sev4" $F 2>&1 \
  | grep -E "^FAILED|passed|failed" | cut -c1-220 | head -8
