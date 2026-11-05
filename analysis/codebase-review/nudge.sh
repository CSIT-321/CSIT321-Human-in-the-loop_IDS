#!/usr/bin/env bash
# Append a write-now reminder to each worker's own copy of the brief (workers re-read it).
B="C:/Users/Glenn Ang/fyp-review-wt"
for n in 1 2 3 4 5 6 7 8 9; do
  f="$B/slice-$n/analysis/codebase-review/BRIEF.md"
  [ -f "$f" ] || continue
  grep -q "WRITE-NOW REMINDER" "$f" && continue
  cat >> "$f" <<'EOF'

## WRITE-NOW REMINDER (added by the orchestrator during your run)

If your output file does not exist yet, write it NOW with the findings you already have, then keep
reading and update it. A run that ends without the file loses all of its work. Stop tracing new
callers once you have read every listed file; the orchestrator verifies cross-slice links itself.
EOF
  echo "slice $n nudged"
done
