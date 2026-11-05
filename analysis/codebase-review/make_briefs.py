"""Generate the per-slice briefs from the real file tree, so every listed path exists."""
from pathlib import Path

REPO = Path(r"C:\Users\Glenn Ang\Desktop\SIM Assignments\FYP\CSIT321-Human-in-the-loop_IDS")
H = REPO / "hitl-ids"
OUT = REPO / "analysis/codebase-review"


def files(*globs, exclude=()):
    found = []
    for pattern in globs:
        for p in sorted(H.glob(pattern)):
            rel = p.relative_to(REPO).as_posix()
            if p.is_file() and "__pycache__" not in rel and ".test." not in p.name \
                    and p.name != "schema.d.ts" and not any(x in rel for x in exclude):
                found.append(rel)
    return list(dict.fromkeys(found))


SLICES = {
    1: ("Contracts, schema and migrations", files(
        "packages/contracts/*.py", "packages/contracts/*.sql"),
        "The data dictionary. Check every migration in db.py, the append-only triggers, CHECK constraints, "
        "and whether legacy and V2 tables model the same concept twice."),
    2: ("Detection core: fusion, signature, ML, pipeline, ranking, feedback, guardrail, audit", files(
        "packages/detection/fusion/*.py", "packages/detection/signature/*.py", "packages/detection/ml/*.py",
        "packages/detection/pipeline/*.py", "packages/detection/ranking/*.py", "packages/detection/feedback/*.py",
        "packages/detection/guardrail/*.py", "packages/detection/audit/*.py", "packages/detection/triage.py"),
        "The approved engine. The feedback/guardrail logic must be reachable from the final Tier 1 view for "
        "flow alerts. Find what the V2 changes broke or bypassed here (runner.py, store.py were modified)."),
    3: ("V2 intake, routing and escalation", files(
        "packages/detection/adapters/*.py", "packages/detection/external_admission.py",
        "packages/detection/system_routing.py", "packages/detection/routing.py",
        "packages/detection/triage_policy.py", "packages/detection/triage_policy_service.py",
        "packages/detection/attack_classification.py", "packages/detection/tier2_escalation.py",
        "packages/detection/context_store.py", "packages/detection/trusted_context.py",
        "config/system-routing-v1.json", "config/operational-triage-v1.json",
        "config/suricata-classification-v3.json", "config/external-admission.json"),
        "This is where automatic Tier 1 -> Tier 2 escalation lives. Judge exactly how a flow alert could be "
        "routed through the same path, and what a foolproof auto-escalation (fact 7) must change here."),
    4: ("V2 human workflow: work claim, verdict, Tier 2 cases, memory, selective review, response", files(
        "packages/detection/analyst_work.py", "packages/detection/analyst_verdict.py",
        "packages/detection/tier2_cases.py", "packages/detection/investigation_assistance.py",
        "packages/detection/triage_memory.py", "packages/detection/selective_review.py",
        "packages/detection/selective_review_policy.py", "packages/detection/response_approval.py",
        "packages/detection/response_policy.py", "packages/detection/prospective_collection.py",
        "config/analyst-work-claim-v1.json", "config/triage-memory-v1.json",
        "config/selective-review-v1.json", "config/safe-memory-auto-activation-v1.json",
        "config/tier2-assistance-v1.json"),
        "Check claim arbitration (it sleeps inside claim()), transaction ownership, and whether two verdict "
        "systems (legacy 5-category feedback vs V2 4-outcome verdict) can be unified for the Tier 1 view."),
    5: ("API: legacy routes, auth, deps, mappers, main, workspaces", files(
        "apps/api/routes.py", "apps/api/auth.py", "apps/api/deps.py", "apps/api/mappers.py",
        "apps/api/main.py", "apps/api/read_only.py", "apps/api/workspaces.py",
        "apps/api/workspace_routes.py", "apps/api/presentation_replay.py", "apps/api/alert_stream_routes.py",
        "apps/api/admin_current_routes.py"),
        "Security focus: RBAC on every route, the JWT secret default, workspace switching (one global "
        "database selection for every user), the SSE stream, path handling in workspaces."),
    6: ("API: V2 routes and the published contract", files(
        "apps/api/routing_routes.py", "apps/api/verdict_routes.py", "apps/api/work_routes.py",
        "apps/api/tier2_case_routes.py", "apps/api/memory_routes.py", "apps/api/selective_review_routes.py",
        "apps/api/context_routes.py", "apps/api/external_admission_routes.py", "apps/api/response_routes.py",
        "apps/api/collection_routes.py", "apps/api/operational_queue.py", "apps/api/current_audit.py",
        "apps/api/final_v3_routes.py", "apps/api/final_v3_records.py", "apps/api/contract/*.py"),
        "Check that handlers and the hand-authored contract (contract/openapi.py) agree, N+1 query paths "
        "(operational_queue.summary computes effective_review per alert), and which endpoints the final "
        "Tier 1 / Tier 2 views need versus which are research-only."),
    7: ("Web: analyst console", files(
        "apps/web/src/pages/analyst/*.tsx", "apps/web/src/features/alert/*.tsx", "apps/web/src/features/alert/*.ts",
        "apps/web/src/features/workstation/*.tsx", "apps/web/src/features/workstation/*.ts",
        "apps/web/src/App.tsx", "apps/web/src/components/layout/*.tsx"),
        "The Tier 1 / Tier 2 views will be built here. Map what exists, what each component shows, and what "
        "must be added to restore the 13 lost items (fact 5). The deleted legacy components are in git at "
        "commit f1b74b6 (`git show f1b74b6:hitl-ids/apps/web/src/features/feedback/FeedbackPanel.tsx`) - "
        "judge whether restoring them is simpler than rebuilding."),
    8: ("Web: admin, evaluator, shared client and session", files(
        "apps/web/src/pages/admin/*.tsx", "apps/web/src/pages/evaluator/*.tsx",
        "apps/web/src/features/admin/*.tsx", "apps/web/src/features/evaluation/*.tsx",
        "apps/web/src/api/*.ts", "apps/web/src/session/*.ts", "apps/web/src/session/*.tsx",
        "apps/web/src/components/*.tsx", "apps/web/src/main.tsx"),
        "Check role gating on the client (never the only guard), token handling, error states, and which "
        "admin/evaluator pages a final product should keep versus label as research."),
    9: ("Evaluation package and scripts", files(
        "packages/evaluation/*.py", "scripts/*.py", "scripts/*.ps1",
        exclude=("make_wireframes.py",)),
        "Separate (a) scripts a final-product operator needs, (b) research/one-off scripts to archive, "
        "(c) dead scripts. Check the frozen-protocol checks that fail on every commit (fact 6) and propose "
        "the fix that keeps the frozen evidence verifiable without blocking development."),
}

for n, (name, paths, focus) in SLICES.items():
    missing = [p for p in paths if not (REPO / p).exists()]
    assert not missing, missing
    text = [f"# Slice {n} — {name}", "",
            "Read `analysis/codebase-review/BRIEF.md` first and follow it exactly.", "",
            f"OUTPUT FILE: `analysis/codebase-review/slice-{n}.md` (the only file you may write).", "",
            f"FOCUS: {focus}", "",
            f"FILES ({len(paths)}). Read every one of these. Do not search the tree for other files to review; "
            "you may open another file only to trace a caller or a symbol, and you must say so.", ""]
    text += [f"- `{p}`" for p in paths]
    (OUT / f"slice-{n}-brief.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(n, len(paths), name)
