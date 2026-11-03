# Current Product User Manual

**HITL IDS — final current operational surface**

This source replaces the preliminary flow-feedback navigation instructions. Earlier submitted
Word files, screenshots and the archived v0.4 source remain historical project evidence.
The manual generator still reads this file; final Word formatting is outside this cleanup.

## (1) Overview

Suricata is the operational detector. PCAP / traffic → Suricata → EVE JSON → correlation →
System Attack Classification → operational priority → automated routing → Analyst Workstation.
XGBoost / TreeSHAP experiments are supporting historical research, not a second mandatory detector.

## (2) Installation and launch

Use Python 3.11 and the dependencies pinned in `hitl-ids/requirements.txt`. From `hitl-ids`:

```
python -m venv .venv
python -m pip install -r requirements.txt
python -m uvicorn apps.api.main:app
```

Activate that environment before installing/running. In another terminal, from `hitl-ids/apps/web`:

```
npm ci
npm run dev
```

The development frontend normally opens at http://localhost:5173 and proxies `/api` to port 8000.
Use the configured project database; an empty operational queue is valid. For a fresh local database,
run this once from `hitl-ids` before starting the API (it refuses to overwrite an existing database):

```
python -c "from pathlib import Path; from packages.contracts import db; from apps.api.auth import ensure_demo_accounts; p=Path('data/demo.db'); assert not p.exists(), 'Database already exists'; p.parent.mkdir(exist_ok=True); c=db.connect(p); db.create_schema(c); ensure_demo_accounts(c); c.close()"
```
 Do not generate a historical
flow-detection batch as a prerequisite for the current Suricata workflow.
Import real EVE through the existing Suricata import tooling, then inspect Incoming Alerts and admit
eligible alerts. Synthetic/demo input must stay explicitly labelled synthetic.
The real-PCAP validation procedure is recorded in the repository's `real-suricata-pcap-validation.md`.
Do not reset a database containing review history just to prepare a demo.

Current product accounts: **Security Analyst** `g.ang` / `analyst-demo` (Glenn Ang) and
**System Administrator** `admin` / `admin-demo` (LIOW CHEE KUANG). The System Administrator
owns Final V3.1 Evaluation and Current HITL Audit. Tier 2 / Senior Analyst investigation is
performed through Tier 2 Cases within the Security Analyst workflow, not a separate login role.
Legacy evaluator credentials and routes are retained only for academic/backward compatibility.
Shared multi-user tests provision Alice/Bob/Carol independently in a disposable database.

## (3) Current navigation

| Analyst destination | Purpose |
|---|---|
| Analyst Workstation (`/analyst/operations`) | Shared work, evidence, classification, priority, routing, Verdict and Human Learning |
| Tier 2 Cases | Investigation Assistance, Conclusion, Human Final Classification, Expert Learning, Response and Resolution |
| Triage Memory | Learned operational knowledge, support, conflict, validity and immutable evidence history |
| Selective Review | Current review disposition, safety explanation and human override |
| Incoming Alerts | Intake, eligibility and operational admission |

There is one Analyst Workstation. Old workstation/triage bookmarks redirect there; obsolete
queue, dashboard, overview, feedback-impact and investigation pages show Page not found.
System Administrator governance, evaluation, and audit remain distinct from the current Analyst
workflow. Legacy evaluator routes are historical academic compatibility surfaces.

Security Analysts can choose **Start tour** in the top bar for a read-only, 16-step guided walkthrough.
It navigates and highlights current Analyst pages without claiming alerts or recording decisions.

## (4) Demonstration sequence

1. Sign in as an Analyst and open Incoming Alerts. Review provenance and admit eligible real or
   clearly labelled synthetic Suricata alerts. Open the admitted alert in Analyst Workstation.
2. Use Available to select work. Read evidence, System Attack Classification, priority and routing.
   Routine Review goes to Tier 1; Critical / Expert Review creates a formal Tier 2 Case directly.
3. Intentionally select an eligible Available Tier 1 queue row. This automatically requests ownership
   through 750 ms arbitration; there is no Start Review button. The initial/default display, direct
   URL, arrival, reconnect, refresh, filter change, and background reconciliation do not claim.
   Only the owner can record that alert's Tier 1 Verdict. Other analysts remain Viewers and can read
   the alert without owner-only actions. A same-round collision assigns neither contender; select
   again explicitly. Persisted arrivals reach the Workstation through an authenticated near-real-time
   read-only stream with silent reconciliation and polling fallback. Arrival never claims.
4. Record the canonical Analyst Verdict with its reason. The alert moves to Completed/history.
   Exact Human Learning is recorded automatically: no second Memory outcome/reason or Exact button.
5. Inspect Human Learning and Triage Memory. Eligible benign Exact evidence is auto-activated by
   System Policy (`safe-memory-auto-activation-v1`). One Alert = One Current Vote; Tier 2 overrides
   Tier 1. The fixed validity is 30 days and conflicts withdraw unsafe reuse. Narrow learning remains
   an explicit human extension; historical/manual activation is not the normal Exact workflow.
6. Open Selective Review. Active Memory alone does not suppress review: current trusted context,
   safety gates and policy evaluation may produce No Immediate Review. Missing trusted context must
   not be treated as safe. No Immediate Review is neither a human Verdict, alert closure, nor response
   execution. Conflict safeguards and the human Require Human Review override remain authoritative.
7. For operational escalation, the owner enters a Decision reason and clicks Escalate to Tier 2.
   A formal Case is created in that same operation; open it using Open Tier 2 Case. There is no
   Candidate approval or separate Create Case stage. Shared work records Escalated.
8. In Tier 2 Cases, inspect the same immutable Primary Alert Evidence used in Tier 1, then the
   separate Investigation Assistance. Record Investigation Conclusion: Finding
   plus Human Final Attack Classification and reason. Exact Expert Learning is automatic into the
   same Memory. Historical Findings are readable but not the current conclusion form. Case Assignment
   may read Unassigned / Collaborative; Tier 2 V1 has no automatic assignment or workload balancing.
9. Review Response Recommendation, then make the human Approve/Reject decision. Approval displays
   Approved — Not Executed. No response is executed by this product.
10. Resolve the Case when its existing resolution prerequisites are met. Resolved cases are read-only;
    conclusions, response decisions, resolution and work events remain in audit/history.

## (5) Evaluation boundaries

System Administrator navigation is exactly Overview, Operational Workspace, HITL Governance,
Users & Access, and Evaluation & Audit. The latter contains the implemented Current HITL Audit,
the completed/frozen Final V3.1 Evaluation, and separate historical Feedback / Legacy Audit.

Operational Workspace can prepare Full Replay or Progressive V3.1 Presentation Replay in an isolated
database. Presentation preparation applies the 40 Learning history, then admits 10 initial Holdout
alerts; the other 150 Holdout alerts arrive progressively through the persisted alert path. Admin
can start or pause arrivals, advance one or five alerts, or load the remainder. Replay is a fixed
demonstration from frozen inputs, not Live Monitoring or a rerun of the official evaluation.
The authenticated alert-arrival stream updates the Workstation only after persistence; silent
reconciliation preserves the current selection, tab, and draft where supported. Arrival never claims.

The final Golden Path and shared Analyst validation use current routes only. Real Suricata PCAP
validation evidence is retained. Protocol V2 remains frozen and unopened. Final V3.1 Run 001 is
completed and frozen; this demonstration does not rerun it or open prospective collection.
