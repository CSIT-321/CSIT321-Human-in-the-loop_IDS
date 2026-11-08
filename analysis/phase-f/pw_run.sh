#!/usr/bin/env bash
# Run one or more Playwright configs one after another; print a one-line result each.
# Usage: bash pw_run.sh <config-name> [<config-name> ...]   (name = the part between playwright. and .config.ts)
cd "C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/apps/web" || exit 2
export HITL_PYTHON="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS/hitl-ids/.venv/Scripts/python.exe"
OUT="${PW_OUT:-$LOCALAPPDATA/Temp/hitl-review/pw}"; mkdir -p "$OUT"
for c in "$@"; do
  timeout 560 npx playwright test -c "playwright.$c.config.ts" > "$OUT/$c.txt" 2>&1
  code=$?
  echo "$c exit=$code $(grep -E '^ +[0-9]+ (passed|failed|skipped|flaky)' "$OUT/$c.txt" | tr -s ' ' | tr '\n' ' ')"
done
