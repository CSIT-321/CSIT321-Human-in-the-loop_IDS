# Current Admin Surface V1

This post-V3.1 product refinement makes **System Administrator** the governance layer for the current Suricata + HITL product. Its primary navigation is exactly **Overview**, **Operational Workspace**, **HITL Governance**, **Users & Access**, and **Evaluation & Audit**.

| Module | Purpose |
| --- | --- |
| Overview | Current selected workspace, operational work, Memory counts and policy versions. The read-only `GET /api/admin/overview` uses the selected operational database and current policy loaders. Unavailable values are shown as such. |
| Operational Workspace | Select Operational or prepare/activate isolated V3.1 Demo Replay. Existing workspace behavior is unchanged. |
| HITL Governance | Read-only projection of the current policy files through fixed server loaders; no generic file reader or editor. |
| Users & Access | Admin-only account visibility (username, display name, role, status, last login). No credential or permission editing. |
| Evaluation & Audit | Links to the existing frozen Final V3.1 viewer and retained Audit Trail. The trail contains historical event types and is not yet a unified V2/HITL audit. |

The current governance sources are `config/suricata-classification-v3.json`, `config/system-routing-v1.json`, `config/triage-memory-v1.json`, `config/safe-memory-auto-activation-v1.json`, `config/selective-review-v1.json`, and `config/analyst-work-claim-v1.json`. The API reads these fixed files through the same validated loaders used by the product. Response execution remains disabled; a human approval records **Approved — Not Executed**.

Analyst operational pages (Tier 2 Cases, Triage Memory, Selective Review, Incoming Alerts, Alert Triage) are absent from Admin primary navigation because the Analyst Workstation owns that workflow. Their compatibility routes and backend authorization remain available. The historical `System Status` URL (`/admin/status`) retains Signature/XGBoost run diagnostics behind a clear legacy notice. Historical feedback-scoring Guardrails and the IP Security Report also remain directly accessible at their existing URLs, outside current primary navigation. Legacy Guardrails do not configure current Suricata routing, canonical Verdict learning, or safe Memory auto activation.

Final Evaluation V3.1 and its Memory Impact/drift evidence reuse the existing viewer; none of the new Admin pages was evaluated by the frozen run. This phase does not change authentication, create a policy editor, or create a unified audit projection. Frozen `evaluation/protocol-v3.1/**` and `evaluation/protocol-v3.1-run-001/**` artifacts are untouched.
