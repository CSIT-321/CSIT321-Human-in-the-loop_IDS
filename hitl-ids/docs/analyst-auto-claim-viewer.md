# Analyst Auto-Claim + Viewer

In Analyst Workstation, an Analyst explicitly selecting an **Available for Review** Tier 1 queue row requests ownership through the existing claim endpoint. The claim keeps its 750 ms arbitration window. A sole claimant becomes **Owner**; two or more distinct Analysts selecting during the same round all receive **Claim Conflict**, no owner is assigned, and each must select an alert again. There is no automatic retry.

Opening the Workstation, its default first alert, a direct `alertRef` URL, refresh, polling, search, filters, and pagination only read data. Selecting No Immediate Review, Unknown or automatic Tier 2, Completed, Escalated, or another Analyst's In Review alert also does not request a claim. An Analyst viewing another owner's alert sees **Your Access: Viewer** and may inspect the alert but cannot use owner-protected Tier 1 actions. Existing backend owner checks remain authoritative.

The queue response identifies its Operational or V3.1 Demo Replay workspace. The selection checks the work record in that same workspace and sends the workspace identifier with the claim. A switch before the POST is rejected with `WORKSPACE_CHANGED`; no claim is written to the newly selected database. The claim arbitration, verdict, routing, case, scoring, and frozen V3.1 evaluation logic are unchanged.

Validation covers focused frontend interaction tests, TypeScript, the real two- and three-Analyst claim arbitration tests, workspace isolation tests, and browser journeys for shared work and Replay ownership/Viewer access. Browser fixtures use disposable databases and never write frozen evaluation results.
