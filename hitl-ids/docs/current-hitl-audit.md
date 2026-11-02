# Current HITL Audit

The Admin **Evaluation & Audit → Current HITL Audit** page is a read-only product timeline of durable decisions in the selected Operational or V3.1 Demo Replay workspace. It answers who acted, which system policy acted, what object changed, and what durable result was recorded. It does not ingest logs or execute a response.

## Sources and event mapping

| Category | Authoritative source | Displayed actions |
| --- | --- | --- |
| WORKSPACE | `workspaces/control.db` `actions` | Replay prepared/reset; workspace activated |
| WORK | `analyst_work_events`, `operational_routing_audit` | Claim request, finalization, contention, completion, escalation; Tier 1 routing |
| VERDICT | `analyst_verdict_events` | Canonical Tier 1 Verdict and later append-only corrections |
| MEMORY | `triage_memory_audit` | Exact candidate/evidence, support, conflict, automatic/manual activation, rejection; current status at the event |
| REVIEW | `selective_review_events` | Persisted disposition or human Require Review override only |
| TIER2 | `operational_routing_audit`, `tier2_case_events` | System/manual routing, Candidate handoff, automatic/manual Case creation, start, note, link, Investigation Conclusion |
| RESPONSE | `response_recommendations`, `response_decisions` | Durable recommendation, human approval/rejection; approval is **Not Executed** |
| RESOLUTION | `tier2_case_events` action `resolve` | Explicit human Case closure |

The projection reads fixed source tables at request time. It stores no parallel writable audit table and never rewrites source events. GET-only Review projections and time-based Memory expiry without a durable event are not fabricated as events.

## Normalized model and attribution

Each row has a stable deterministic `eventRef`, timestamp, category, event type, action, object type/reference, optional alert/case/lesson references, workspace, summary, result, source subsystem, and a narrow allowlisted `detail` object. Optional references are null when they do not apply. Stable identities include the source, workspace, and immutable event timestamp, so equivalent row IDs in Operational, Replay, and later Replay preparations cannot collide.

`actorType=human` and the stored user/display name identify a real analyst for claims, Verdicts, case decisions, response decisions, and resolution. Global workspace actions retain the authenticated Admin username stored in control history. `actorType=system`, `actorName=null`, and `decisionSource=system_policy` identify claim arbitration, automatic Memory evidence/activation, automatic Case creation, and persisted policy Review results. A persisted policy Review includes the human who initiated evaluation in details but attributes the computed disposition to System Policy. Automatic Memory evidence likewise names the source Verdict author in details without pretending that author performed the automatic evidence action.

## Workspace and API scope

`GET /api/admin/audit/current` requires System Administrator and uses a read-only connection to the selected operational database plus a fixed read-only connection to global workspace control history. Its `category`, `actor`, `decisionSource`, `objectType`, reference `search`, and `workspace` filters are applied on the server before `limit`/`offset` pagination. The response includes `activeWorkspace`. Operational and Replay event histories remain isolated; switching workspaces changes which database is read and does not rewrite either history. Global control actions are labelled `global` and can be filtered separately. The endpoint accepts no database path, table name, SQL, or file selector.

## Distinctions and limits

**Historical Feedback / Legacy Audit** (`/admin/audit`) retains older Signature/XGBoost feedback and historical operations. Those events are not presented as current HITL events. **Final V3.1 Evaluation** is the frozen formal effectiveness and safety record; this post-evaluation product audit does not change or rerun it.

The page shows the active workspace plus global control actions. It does not combine both operational databases into one cross-workspace search. The read-time projection scans current event tables before filtering, which is appropriate for the current bounded product dataset; an indexed server-side union would be needed for substantially larger histories. It intentionally omits raw request payloads, evidence snapshots, credentials, target values, and arbitrary database content from event detail. Approval records never imply execution, and resolved Cases never imply a response was executed.
