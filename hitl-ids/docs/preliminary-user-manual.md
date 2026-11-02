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

Demo accounts: `g.ang` / `analyst-demo`, `admin` / `admin-demo`, `evaluator` / `evaluator-demo`.
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
Admin/Evaluator Alert Triage provides role-scoped operational inspection. Their audit, governance
and historical research diagnostics remain explicitly distinguished from the current analyst flow.

## (4) Demonstration sequence

1. Sign in as an Analyst and open Incoming Alerts. Review provenance and admit eligible real or
   clearly labelled synthetic Suricata alerts. Open the admitted alert in Analyst Workstation.
2. Use Available to select work. Read evidence, System Attack Classification, priority and routing.
   Routine Review goes to Tier 1; Critical / Expert Review creates a formal Tier 2 Case directly.
3. Click Start Review. Only the owner can record that alert's Tier 1 Verdict. In Review identifies
   the owner; a same-round collision gives neither contender ownership. Refresh and retry explicitly.
   Queue refresh is a read-only 15-second refresh, not an automatic claim.
4. Record the canonical Analyst Verdict with its reason. The alert moves to Completed/history.
   Exact Human Learning is recorded automatically: no second Memory outcome/reason or Exact button.
5. Inspect Human Learning and Triage Memory. Eligible benign Exact evidence is auto-activated by
   System Policy (`safe-memory-auto-activation-v1`). One Alert = One Current Vote; Tier 2 overrides
   Tier 1. The fixed validity is 30 days and conflicts withdraw unsafe reuse. Narrow learning remains
   an explicit human extension; historical/manual activation is not the normal Exact workflow.
6. Open Selective Review. Active Memory plus current safe context can yield No Immediate Review.
   Canonical Verdict guards, conflict safeguards and human override remain authoritative. Missing
   trusted context must not be treated as safe. Suppression does not close an alert or execute a response.
7. For operational escalation, the owner enters a Decision reason and clicks Escalate to Tier 2.
   A formal Case is created in that same operation; open it using Open Tier 2 Case. There is no
   Candidate approval or separate Create Case stage. Shared work records Escalated.
8. In Tier 2 Cases, inspect Investigation Assistance and record Investigation Conclusion: Finding
   plus Human Final Attack Classification and reason. Exact Expert Learning is automatic into the
   same Memory. Historical Findings are readable but not the current conclusion form.
9. Review Response Recommendation, then make the human Approve/Reject decision. Approval displays
   Approved — Not Executed. No response is executed by this product.
10. Resolve the Case when its existing resolution prerequisites are met. Resolved cases are read-only;
    conclusions, response decisions, resolution and work events remain in audit/history.

## (5) Evaluation boundaries

The final Golden Path and shared Analyst validation use current routes only. Real Suricata PCAP
validation evidence is retained. Protocol V2 remains frozen and unopened; do not open prospective
collection during the demonstration. Readiness for a later Protocol V3 does not open it automatically.
