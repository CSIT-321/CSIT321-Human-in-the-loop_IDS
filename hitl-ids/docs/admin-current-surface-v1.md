# Current Admin Surface V1

This post-V3.1 product refinement makes **System Administrator** the governance layer for the current Suricata + HITL product. Its primary navigation is exactly **Overview**, **Operational Workspace**, **HITL Governance**, **Users & Access**, and **Evaluation & Audit**.

| Module | Purpose |
| --- | --- |
| Overview | Current selected workspace, operational work, Memory counts and policy versions. The read-only `GET /api/admin/overview` uses the selected operational database and current policy loaders. Unavailable values are shown as such. |
| Operational Workspace | Select Operational or prepare/activate isolated V3.1 Demo Replay. Existing workspace behavior is unchanged. |
| HITL Governance | Read-only projection of the current policy files through fixed server loaders; no generic file reader or editor. |
| Users & Access | Admin-only, read-only visibility of current product users: username, name, role, status, and last login. No credential or permission editing. |
| Evaluation & Audit | System Administrator owns Final V3.1 Evaluation and Current HITL Audit. Historical academic evidence remains accessible separately. |

The final product has two current user roles: **Security Analyst** and **System Administrator**. Tier 2 / Senior Analyst is an investigation responsibility within the Analyst's Tier 2 Case workflow, not another current login role. The seeded `admin` account's name is **LIOW CHEE KUANG**. The legacy evaluator account and routes remain available only for academic/backward compatibility. The three exact `v3-analyst-*` presentation-learning seed identities are also academic fixtures. These compatibility identities are excluded from Users & Access; independently created Analyst accounts remain visible.

The current governance sources are `config/suricata-classification-v3.json`, `config/system-routing-v1.json`, `config/triage-memory-v1.json`, `config/safe-memory-auto-activation-v1.json`, `config/selective-review-v1.json`, and `config/analyst-work-claim-v1.json`. The API reads these fixed files through the same validated loaders used by the product. Response execution remains disabled; a human approval records **Approved — Not Executed**.

Analyst operational pages (Tier 2 Cases, Triage Memory, Selective Review, Incoming Alerts, Alert Triage) are absent from Admin primary navigation because the Analyst Workstation owns that workflow. Their compatibility routes and backend authorization remain available. The historical `System Status` URL (`/admin/status`) retains Signature/XGBoost run diagnostics behind a clear legacy notice. Historical feedback-scoring Guardrails and the IP Security Report also remain directly accessible at their existing URLs, outside current primary navigation. Legacy Guardrails do not configure current Suricata routing, canonical Verdict learning, or safe Memory auto activation.

Final Evaluation V3.1 and its Memory Impact/drift evidence reuse the existing viewer; none of the new Admin pages was evaluated by the frozen run. Current HITL Audit is the current operational audit view. This phase does not create a policy editor. Frozen `evaluation/protocol-v3.1/**` and `evaluation/protocol-v3.1-run-001/**` artifacts are untouched.
