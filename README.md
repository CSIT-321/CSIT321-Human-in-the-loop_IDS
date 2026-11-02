# Human-in-the-Loop Intrusion Detection System

The current product lives in **`hitl-ids/`**. Start with the
[current user manual](hitl-ids/docs/preliminary-user-manual.md) and
[final surface cleanup record](docs/final-legacy-cleanup.md).

Suricata → EVE JSON → Correlation → System Attack Classification → Priority / Routing →
Analyst Workstation → Shared Claim → canonical Verdict → automatic Exact Human Learning →
Triage Memory / Selective Review → Tier 2 Investigation → Response Decision → Case Resolution.

The Security Analyst navigation is Analyst Workstation, Tier 2 Cases, Triage Memory,
Selective Review and Incoming Alerts. There is one current Workstation at `/analyst/operations`.
Response approval does not execute a response. Protocol V2 remains frozen and unopened.

## Run

From `hitl-ids`, activate a Python 3.11 environment, install `requirements.txt`, and run
`python -m uvicorn apps.api.main:app`. From `hitl-ids/apps/web`, run `npm ci` and `npm run dev`.
The manual describes accounts, intake and the review sequence. A legacy flow batch is not required.

## Validation and evidence

- [Final Golden Path](hitl-ids/docs/final-golden-path-e2e.md)
- [Real Suricata PCAP validation](hitl-ids/docs/real-suricata-pcap-validation.md)
- [Shared Analyst Workstation / exclusive claims](hitl-ids/docs/shared-analyst-workstation-claim.md)

Run frontend tests with `npm test`, type checking with `npm run typecheck`, and build with
`npm run build` from `hitl-ids/apps/web`. Backend regression uses `python -m pytest` from `hitl-ids`.
Dedicated Playwright configurations run disposable Golden Path and shared-work services.

## Repository boundaries

`hitl-ids/apps`, `packages` and current operational scripts implement the product.
`stage-1` through `stage-5`, `prototype-demo`, older plans and research documents are historical
academic artifacts, not alternative product entry points. Signature/XGBoost/TreeSHAP experiments
are retained as historical/supporting research. The superseded top-level `dashboard/` application
has been removed; its sample data is preserved under `docs/history/dashboard-data/`.

GitHub Pages builds `hitl-ids/site`, an informational documentation site, not another IDS runtime.
Its older walkthroughs are explicitly historical; the published user manual describes the current product.
