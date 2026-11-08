# Browser (Playwright) gate — head vs baseline, 2026-11-08

Runner: `analysis/phase-f/run_e2e_all.sh` (21 self-contained configs, run one at a time).
- Head: `cd2245c` (this branch). Logs: `%LOCALAPPDATA%/Temp/hitl-review/e2e-head/`.
- Baseline: `f91ac78` (2026-11-03, last commit before this branch's work), git worktree in
  `%LOCALAPPDATA%/Temp/hitl-review/base-f91ac78`, `PYTHONPATH` set to that tree (checked: `packages` and
  `apps` load from it). Logs: `%LOCALAPPDATA%/Temp/hitl-review/e2e-base/`.
- Not run: `workspaces`, `presentation`, `persistent-workstation` (need hand-started servers),
  `real-suricata` (needs a real capture folder).

Other layers on head: pytest 1846 passed / 4 skipped / 0 failed; `tsc -b` 0 errors; Vitest 307/307.

| Config | Baseline | Head | Class |
|---|---|---|---|
| verdict-safety, assistance, reclassification (2), f2-boundary, shared-work, current-surface (3) | pass | pass | green |
| verdict | fail | pass | fixed on this branch |
| pre-freeze | pass | fail in batch, **pass alone** | load flake |
| resolution | pass | fail | **this branch (D1)**: case list opens on "Active (open + investigating)"; test expects a resolved row. Approved design; test is stale. |
| final-golden-path | pass | fail | **this branch (C9/D4, `f508dfc`, `3950ed2`)**: queue order is severity-first, unflagged-last; test asserts priority-only order. Approved design; test is stale. |
| default (`demo.spec`) | fail | fail (same) | before this branch: expects `/analyst/v2-triage` |
| suricata, operational-queue, conclusion-memory, verdict-memory | fail | fail (same assertion) | before this branch |
| automatic-learning | no start | no start (same) | before this branch: fixture refused by `VerdictConflict` |
| direct, unified | no start | no start (same) | before this branch: fixtures miss `capture_scope` (`a769079`, 2026-11-01) |
| routing (11), refinement (10), prospective (2) | no start | start; 10 + 10 + 2 fail | fixture broken before this branch (`capture_scope`); E3 made it start. Never ran green on the baseline, so the cause of each failure is not separated. |
