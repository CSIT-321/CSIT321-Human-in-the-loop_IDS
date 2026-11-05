#!/usr/bin/env bash
# Dispatch one opencode review worker per slice, each in its own detached worktree at the same commit.
# Usage: bash dispatch.sh 1 2 3 ...
set -u
REPO="C:/Users/Glenn Ang/Desktop/SIM Assignments/FYP/CSIT321-Human-in-the-loop_IDS"
BASE="C:/Users/Glenn Ang/fyp-review-wt"   # never under %LOCALAPPDATA%\Temp: opencode remaps it to C:\tmp
mkdir -p "$BASE"
SHA=$(git -C "$REPO" rev-parse HEAD) || { echo "cannot read repo HEAD"; exit 1; }
echo "dispatching at $SHA"
for n in "$@"; do
  W="$BASE/slice-$n"
  if [ ! -d "$W" ]; then
    git -C "$REPO" worktree add --detach "$W" "$SHA" >"$BASE/slice-$n.wt.log" 2>&1 || { echo "worktree $n failed: $(cat "$BASE/slice-$n.wt.log")"; continue; }
  fi
  mkdir -p "$W/analysis/codebase-review"
  cp "$REPO/analysis/codebase-review/BRIEF.md" "$REPO/analysis/codebase-review/slice-$n-brief.md" "$W/analysis/codebase-review/"
  (
    cd "$W" || exit 1
    timeout 2700 opencode run --variant max --title "review-slice-$n" \
      "Read analysis/codebase-review/slice-$n-brief.md and analysis/codebase-review/BRIEF.md and follow them exactly. Write only analysis/codebase-review/slice-$n.md." \
      > "$BASE/slice-$n.log" 2>&1
    echo "exit=$?" >> "$BASE/slice-$n.log"
    cp "$W/analysis/codebase-review/slice-$n.md" "$REPO/analysis/codebase-review/slice-$n.md" 2>/dev/null \
      && echo "slice $n copied" >> "$BASE/slice-$n.log" || echo "slice $n NO OUTPUT" >> "$BASE/slice-$n.log"
  ) &
  sleep 20   # stagger the starts: one opencode store, nine processes
done
wait
for n in "$@"; do echo "== slice $n: $(tail -n 2 "$BASE/slice-$n.log" | tr '\n' ' ')"; done
