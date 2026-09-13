# SOC / IDS Analyst Console: Research Brief for the HITL-IDS UI Rebuild

Research date: 2026-09-13. Citations [n] refer to the source list at the end; every cited URL was fetched and read. Items marked **not verified** could not be confirmed from a fetched page.

## Executive summary

- **Standard layout: queue plus details pane.** Sentinel's Incidents page puts a toolbar and counts on top, a filterable grid in the centre and a details pane on the side. You can triage from the pane without leaving the grid [1]. Elastic uses an alerts table with a flyout [7][8], and Security Onion uses a grouped alert list with a right-side Details Panel [14]. Build the queue this way.
- **Triage controls are always the same four.** Every product exposes owner/assignee, status, severity/urgency and a closure classification. Sentinel [1], Splunk [12][13], Elastic [7] and CrowdStrike [18] all do this. Comments/notes and tags are nearly universal.
- **Closing requires a classification.** Sentinel requires one of True Positive, Benign Positive, False Positive (incorrect alert logic), False Positive (incorrect data) or Undetermined [1]. Elastic's reasons are True Positive, Benign Positive, False Positive, Duplicate, Automated Closure, Other and None [10]. Our "expected activity" verdict matches "Benign Positive" exactly, so use that industry term alongside it.
- **Status models are 3 to 5 states.** Elastic uses Open/Acknowledged/Closed [7]. Splunk uses Unassigned/New/In-progress/Pending/Closed [13]. CrowdStrike uses new/in_progress/reopened/closed [18]. Our new/claimed/in_progress/resolved/dismissed already fits.
- **Detail views answer "why did this fire?" first.** Elastic's flyout leads with an About section giving the rule description and the alert reason [8]. QRadar shows a description of "the cause of the offense" plus annotations explaining why traffic is threatening [17]. Put our combined explanation (signature clauses + SHAP + fusion reasoning) at the top of the detail view.
- **Related context is a first-class section.** Sentinel shows up to 20 similar incidents with a similarity reason [2]. Elastic has Correlations and Prevalence insights [8]. QRadar shows top 5 source and destination IPs [17]. Our "family" concept maps directly onto this pattern.
- **Scores map to severity bands.** Elastic maps a 0–100 risk score to four bands: 0–21 low, 22–47 medium, 48–73 high, 74–100 critical [9]. QRadar's magnitude combines relevance, severity and credibility [17]. Our 0–100 score and floors (70, 75) fit a similar band display.
- **Research warns about both explanation overload and misplaced trust.** Analysts accept AI output when explanations are relevant and evidence-backed, and prefer contextual depth over dashboard-only outcomes [20]. Uncalibrated confidence displays amplify false negatives [23]. Surfacing the right context cut alert validation time by 24% [21]. Show the top few SHAP features plus evidence, not raw model internals.
- **Accessibility rules to follow:**
  - Never convey severity by colour alone [24].
  - Chart marks and state indicators need 3:1 contrast [25].
  - Everything must work from the keyboard [26].
  - Use `font-variant-numeric: tabular-nums` so numbers align [27].
  - Carbon's status pattern combines symbol, shape, colour and text [28].
- **Demo scope.** The current API already supports a credible Tier-1 queue, detail, verdict and audit experience. The biggest gaps against industry norms are assignment/owner, comments, an entity (IP) pivot view, time-series KPIs and MITRE mapping. Assignment and an IP pivot are the cheapest backend additions with the largest perceived realism.

---

## 1. Visual conventions of SOC / SIEM / IDS consoles

**Layout patterns (verified)**
- **Microsoft Sentinel, Incidents page [1].**
  - Top: a toolbar for grid-wide and multi-select actions, plus counts of open incidents (new/active) and open incidents by severity.
  - Centre: the incident grid, with filters and a search bar.
  - Side: a details pane with key info and action buttons.
- **Microsoft Sentinel, Incident details page [2].**
  - Left: a persistent summary panel. It can collapse to a margin that still lets you change owner, status and severity.
  - Top button bar: Tasks, Activity log, Logs.
  - Tabs: Overview, whose widgets are Incident timeline, Similar incidents, Entities and Top insights, and Entities.
  - Entities tab: a list with a right side-pane made of Info, Timeline and Insights cards.
- **Elastic Security [7][8].**
  - Alerts page: visualisations at the top ("Group and visualize alerts by field"), then a KQL search bar, time controls (default last 24 hours), dropdown filters (Status, Severity, User, Host) and a configurable alerts table.
  - Details: a flyout with Overview / Table / JSON tabs. Overview contains About, Investigation, Visualizations, Insights and Response sections. A footer holds the "Take action" menu.
- **Splunk ES analyst queue (Mission Control) [13].**
  - Columns: Title, ID, Entity, Risk score, Findings count, Time, Disposition, Urgency, Status, Owner.
  - Time range defaults to 24 hours.
  - Optional timeline visualisation, plus distribution charts by urgency, status, owner and domain.
  - Three-dot row menu for row actions.
- **Security Onion Alerts [14].**
  - Alerts are grouped by rule name and module by default, with a drill-down to individual alerts.
  - Sortable columns: timestamp, rule name, severity, IP/port.
  - Per-row action icons: acknowledge (bell), escalate (exclamation), details (info). Details open in a right-side Details Panel.
  - Time picker at the upper right.
- **Wazuh dashboard [16].** Navigation is split into Dashboards, Agents Management, Server Management, Index Management and Dashboard Management. Modules are grouped into Endpoint Security, Threat Intelligence (incl. threat hunting, MITRE ATT&CK), Security Operations (compliance) and Cloud Security.
- **IBM QRadar Offense Summary [17].**
  - Top: a magnitude bar, the description, offense type, source/destination IPs, start time and duration.
  - Bottom: "top contributors" tables. Top 5 source IPs, top 5 local destination IPs with a "Chained" column, top categories, and the last 10 events and flows.
  - Notes: you can add them, but "cannot edit or delete" them.
- **CrowdStrike Falcon.** Console UI screenshots and docs are behind login (**not verified**). The public developer docs confirm the detection data model: status, assignment, tactic/technique, severity, comments and tags [18].
- **Google SecOps.** The alerts/IOC pages fetched returned mostly navigation. A quickstart summary mentioned graph, events, entity, severity/priority and verdict elements [19], but no exact field names or layout could be confirmed (**not verified in detail**).

**Density, theme, typography**
- **Density.** All verified products use dense tables with configurable columns (Elastic lets you reorder, multi-sort and add/remove fields [7]). Sentinel truncates text and shows the full value in tooltips on hover [2]. Plan for compact rows with hover or tooltip expansion.
- **Dark vs light.** No fetched official page stated a default theme or a recommendation. **Not verified.** Recommendation: support both via theme tokens, since analysts may work long shifts. Do not rely on theme to carry meaning.
- **Monospace for IPs, ports and hashes.** No fetched vendor doc states this. **Not verified** as a documented convention. Recommended anyway: monospace keeps IPs and ports scannable and aligned. Combine it with tabular numerals for scores and counts [27].
- **Severity colour.** Carbon's status palette uses red for danger, orange for warning, yellow for caution, green for success and blue for info [28]. Sentinel draws a severity colour band on timeline rows and uses a dotted band for out-of-incident alerts, so it uses line style as well as colour [2].
- **Charts.** Charts sit above the list as filters or context, not as destinations: Elastic groups alerts by field [7], and Splunk offers a timeline and distribution charts [13]. SOC-manager metrics live in a separate workbook [4].

## 2. The triage workflow end to end

**Lifecycle as evidenced by product surfaces.** NIST SP 800-61r3 frames incident response within CSF 2.0. Only the landing page was readable, so lifecycle details from it are **not verified**.

| Step | What happens | UI surfaces (evidence) |
|---|---|---|
| Intake | Detections create alerts; correlation groups them | Sentinel incidents aggregate alerts and inherit entities, severity and MITRE tactics [2]. Fusion produces "low-volume, high-fidelity, and high-severity" multi-alert incidents [5]. Security Onion groups by rule [14]. |
| Triage | Pick up, assess, set owner, status and severity | Filter by Owner = "your personal workload". Triage from the details pane without opening full details [1]. Splunk: set Owner, Status, Urgency, Disposition [12]. Security Onion: Acknowledge [14]. |
| Investigation | Look at evidence, entities, timeline, related alerts | Sentinel: timeline, entities, similar incidents, top insights, investigation graph, in-context Logs [2]. Elastic: highlighted fields, correlations, prevalence, graph preview [8]. Security Onion: pivot to Hunt, PCAP [14]. |
| Escalation (T1→T2) | Promote to case/incident for deeper work | Security Onion: Escalate creates a new case or adds to an existing one [14][15]. Splunk: "Add to investigation" [13]. Elastic: add to case via Take action [8]. |
| Response | Contain or remediate | Sentinel: Run playbook [1][2]. Elastic: host isolation and response actions [8]. Splunk: Run Playbook, adaptive response [13]. (Out of scope for us: recorded flows.) |
| Closure | Classify and document | Sentinel requires a classification plus a comment [1]. Elastic closing reasons [10]. Splunk Disposition [13]. CrowdStrike resolution tags true_positive / false_positive / ignored [18]. |
| Tuning / learning | Reduce future noise | Sentinel: an automation rule from an FP incident suggests entity conditions, closes matching incidents with a reason, and expires after 24 h by default [3]. |

**Status models**
- Sentinel: New → Active → Closed [1][4].
- Elastic: Open / Acknowledged / Closed [7].
- Splunk ES: Unassigned, New, In-progress, Pending, Closed (queue columns) [13].
- CrowdStrike: new, in_progress, reopened, closed [18].

**Closure classifications**
- Sentinel [1]: True Positive (suspicious activity), Benign Positive (suspicious but expected), False Positive (incorrect alert logic), False Positive (incorrect data), Undetermined.
- Elastic [10]: True Positive, Benign Positive, False Positive, Duplicate, Automated Closure, Other, None. Available from the alerts table and flyout. Closing from Cases is proposed for 9.4.
- Splunk [13]: disposition ranges "Undetermined through False Positive variants"; exact list **not verified**.

**Mapping to our verdicts**

| Our verdict | Industry equivalent |
|---|---|
| confirm true positive | True Positive |
| mark false positive | False Positive |
| expected activity | Benign Positive |
| needs investigation | Acknowledged / In-progress, with no closure |
| escalate | Escalate / Add to case (Security Onion [14], Splunk [13]) |

## 3. Information on list rows and detail views

**List row (evidence)**
- Splunk: title, ID, entity, risk score, finding count, time, disposition, urgency, status, owner [13].
- Security Onion: timestamp, rule name, severity, source/destination IP and port, group count [14].
- Sentinel grid: searches by default across incident ID, title, tags, owner and product name. Severity counts sit in the header [1].
- Elastic: configurable columns and default filters on status, severity, user and host [7].

**Recommended row for us:**
- queue band
- score, with tabular numerals and a bar
- severity (icon + text)
- evidence class (corroborated / sig-only / model-only)
- predicted attack class plus model confidence
- src IP:port → dst IP:port in monospace
- protocol
- flow timestamp
- status
- "needs review" flag
- family indicator

**Detail view (evidence)**
- **Why it fired.** Elastic About section: rule description, alert reason, MITRE [8]. QRadar: description of cause, plus annotations on why the traffic is threatening [17].
- **Key fields.** Elastic: "Key fields relevant to the alert, plus any custom highlighted fields defined in the rule" [8][9]. Elastic Table tab: all fields as name-value pairs with pinning. JSON tab: raw data [8].
- **Entities.** Sentinel Entities widget and tab; an IP entity includes geolocation, a 7-day timeline and insights [2]. QRadar: top source and destination IPs [17].
- **Timeline.** Sentinel incident timeline of alerts and bookmarks [2].
- **Related alerts.** Sentinel: similar incidents with a "Similarity reason" column [2]. Elastic: Correlations and Prevalence [8]. QRadar: "Chained" destination IPs [17].
- **Recommended steps.** Elastic investigation guide [8][9]. Sentinel Tasks [2].
- **History and notes.** Sentinel Activity log mixes actions and comments, filterable [2]. Security Onion case History [15]. QRadar immutable notes [17].

**Our detail view should contain:**
- explanation sentence(s)
- signature clauses matched
- ML prediction plus confidence plus the top 5 SHAP features (signed direction, feature value)
- evidence-class rationale
- flow 5-tuple and key flow statistics
- family (size, prior verdicts)
- score-adjustment chain, with guardrail messages
- verdict history
- verdict actions

## 4. Interactable items

| Interaction | Evidence | Standard or nice-to-have | Our status |
|---|---|---|---|
| Filters + free-text search | Sentinel [1], Elastic KQL + dropdowns [7], Splunk SPL [13] | Standard | Supported |
| Time-range picker | Elastic default 24 h [7], Splunk [13], Security Onion [14] | Standard (live data) | Low value on static data. Use a flow-timestamp range filter; needs backend param |
| Bulk actions | Sentinel toolbar on selected incidents [1]; Elastic "Selected x alerts" [7]; Splunk select page / all, Edit, Assign to me [13] | Standard | Needs backend: bulk verdict/status endpoint |
| Assign / claim / "Assign to me" | Sentinel Owner [1], Splunk [13], CrowdStrike [18] | Standard | Needs backend |
| Status change | All [1][7][13][18] | Standard | Status field exists; transition endpoint **not confirmed** |
| Severity override | Sentinel Severity dropdown [1]; Elastic severity/risk override at rule level [9] | Standard | Partial: verdicts adjust score within guardrails |
| Closure classification + mandatory comment | Sentinel [1], Elastic [10] | Standard | Supported via verdicts; comment text **unknown** |
| Comments / notes | Sentinel [1][2], Security Onion markdown [15], QRadar non-editable [17], CrowdStrike [18] | Standard | Needs backend |
| Tags | Sentinel [1], Elastic [7], CrowdStrike [18] | Standard | Needs backend |
| Saved views | Splunk saved views [13] | Should-have | Needs backend (or local storage) |
| Pivot on value (IP/port → related) | Security Onion Hunt / Include / Exclude / Only [14]; Sentinel entity timeline [2] | Standard | Mostly supported: search filter on IP; entity page needs backend |
| Group-by | Security Onion groups by rule [14]; Elastic group by field [7] | Should-have | Needs backend aggregation (or client-side over 5,000) |
| Similar / related | Sentinel similar incidents [2] | Standard in modern tools | Supported (family) |
| Investigation graph | Sentinel [2], Elastic graph preview [8] | Nice-to-have | Later |
| Export JSON / CSV | Elastic JSON export [8] | Should-have | Client-side from detail |
| Create exception from FP | Sentinel automation rule from incident [3] | Nice-to-have | Family learning is our analogue |
| Keyboard shortcuts | No fetched vendor doc confirmed shortcuts (**not verified**) | Nice-to-have, but WCAG requires full keyboard operation [26] | Frontend only |

## 5. Dashboard / overview KPIs

The Sentinel Security operations efficiency workbook [4] contains:
- incidents created over time
- incidents by closing classification, severity, owner and status
- mean time to triage (FirstModifiedTime − CreatedTime)
- mean time to closure (ClosedTime − CreatedTime)
- percentiles of both
- mean time to triage per owner
- recent activities and closing classifications

Splunk's queue offers distributions by urgency, status and owner [13]. QRadar exposes top source and destination IPs and top categories [17]. Wazuh has alert-level summaries and a MITRE module [16].

| KPI | Computable from our data? |
|---|---|
| Alerts by severity / band / evidence class | Yes: dashboard counts [supported] |
| Open vs resolved/dismissed; verdict breakdown (TP/FP/benign/escalated) | Yes, from status and verdict history |
| Top attack classes (predicted and signature) | Yes, via aggregation |
| Top talkers (src/dst IP, dst port) | Yes, from flows; needs an aggregation endpoint |
| Detector agreement (corroborated vs single-source) | Yes, a distinctive KPI for our fusion story |
| Guardrail interventions (floors hit, caps applied) | Yes, from the adjustment chain / audit |
| Family learning activations | Yes, from the audit log |
| Per-class precision / recall / F1, three-arm comparison | Yes: evaluation metrics [supported] |
| Alert volume over time | Only flow-timestamp histograms of recorded data (not real-time); needs backend |
| MTTA / time-to-triage, MTTR / time-to-closure | Only from verdict and audit timestamps within a demo session. Label as "session analyst activity", not operational MTTD |
| MTTD | No. Detection is a batch over recorded flows |
| Analyst workload per owner | No, until assignment exists |

## 6. Human-in-the-loop and explainable ML alert UX

**Product patterns**
- **Elastic ML anomaly explanation [11].**
  - Anomaly score from 0–100.
  - An "Anomaly explanation section" breaks the score into single bucket impact, multi-bucket impact (marked "+") and anomaly characteristics impact.
  - Notes that renormalisation can change scores.
  - Pattern to borrow: decompose a score into named, human-readable contributing factors, as with our score adjustment chain.
- **Sentinel UEBA [6].**
  - Two separately explained scores: investigation priority (0–10, event-level) and anomaly score (0–1, behaviour-level).
  - A worked example of why they differ (a first-time action scores high priority but low anomaly).
  - The behaviors layer adds "natural language explanations" and MITRE mappings.
  - Pattern to borrow: when showing two scores (ML confidence vs fused score), explain the difference in one sentence.
- **Sentinel Fusion [5].** Presents ML correlation as incidents titled by scenario ("Possible multistage attack activities detected by Fusion"). It lets admins exclude detection patterns, which is an analyst/admin feedback path.
- **Sentinel false-positive handling [3].** Analyst-driven exceptions pre-fill from the incident's entities, record a closing reason and comment, and expire by default after 24 h to "reduce the chance of false negative errors". This is a strong precedent for our bounded guardrails and 3-verdict family threshold. Show the analyst the scope and limits of what their feedback will change.

**Academic evidence (fetched)**
- **Too Much to Trust? (CCS 2025) [20].** Survey N=248, interviews N=24. Analysts accepted XAI outputs "even in cases of lower predictive accuracy, when explanations were perceived as relevant and evidence-backed." They preferred contextual depth and advocated "role-aware, context-rich XAI designs aligned with SOC workflows." Design implication: pair SHAP with raw evidence (flow values, signature clauses), and tailor depth per role.
- **ContextBuddy [21].** Recommending relevant context cues raised non-expert users' classification accuracy by 21.1% and cut alert validation time by 24% (13-participant within-subject study). Implication: curate a short "key evidence" section rather than dumping every field.
- **Decision-Aware Trust Signal Alignment [23].** Uncalibrated confidence scores are "hard to read when under pressure". Misaligned confidence displays amplified false negatives in simulation, while calibrated, cost-aware trust signals greatly reduced cost-weighted loss. Implication: show confidence as a calibrated band, not a false-precision percentage. Keep critical and infiltration floors visibly separate from model confidence.
- **LLMs in the SOC [22].** 3,090 queries from 45 analysts over 10 months. Analysts kept decision authority and used AI as a sensemaking aid. Implication: position the model as advice; the verdict is the analyst's.
- **Not verified (fetch blocked):**
  - Alahmadi et al., "99% False Positives" (USENIX Security 2022). Per search snippet only, most "false positives" are benign triggers explained by legitimate behaviour, which supports a distinct Benign Positive verdict.
  - Tariq et al., "Alert Fatigue in SOCs" (ACM CSUR 2025), which frames mitigation as automation, augmentation and human–AI collaboration.

  Both were confirmed to exist via search results only; cite cautiously or re-fetch from a library.

**Recommended XAI presentation for our alerts**
1. A one-sentence verdict-neutral explanation, e.g. "Signature SSH-brute clause matched and model predicts SSH-Bruteforce (high confidence); corroborated."
2. Evidence split into two columns: Signature (clauses matched) | Model (class, confidence band, top 5 SHAP features as a signed horizontal bar with feature value and direction labels in text).
3. Guardrail and feedback transparency: an adjustment chain (base score → each verdict delta → clamp/floor), with each step's guardrail sentence shown inline.
4. Family learning state, e.g. "2 of 3 agreeing verdicts; next verdict will apply to 14 similar alerts".

## 7. Accessibility and usability for dense dashboards

- **Do not use colour alone.** SC 1.4.1: "Color is not used as the only visual means of conveying information…" [24]. Severity, band and evidence class each need text or icon shape. Carbon requires combining symbols, shapes, colours and type, with "at least three of these elements" for status indicators. It also advises consistent filled vs outlined icons, and filled icons for high attention [28].
- **Non-text contrast.** 3:1 against adjacent colours for UI components and graphical objects, including chart segments and state indicators [25]. This applies to SHAP bars, severity pills and focus rings.
- **Keyboard.** "All functionality of the content is operable through a keyboard interface…" [26]. Required behaviour:
  - row navigation in the queue
  - Enter opens detail
  - verdict buttons reachable in order
  - drawer focus trap and return focus on close
  - no hover-only information (Sentinel relies on hover tooltips for truncated text [2]; provide a keyboard/focus equivalent)
- **Tabular numerals.** `tabular-nums` makes "numbers… all of the same size, allowing them to be easily aligned like in tables" [27]. Use it for scores, counts, ports, metrics and F1 tables.
- **Restraint.** Carbon: don't use status indicators "when no user action is necessary", because too many "tax a user" [28]. Show the "needs review" flag only when it is true.
- **Colour-blind-safe palette.** Beyond the contrast and not-colour-alone rules above, no specific palette source was fetched (**not verified**). Recommendation: pair a red/orange/yellow/blue ramp with icon shapes and text labels. Test with a CVD simulator.

---

## Recommended information architecture for our console

Global shell:
- a left nav with role-scoped items
- a top bar with the current detection run, role/user and theme toggle
- a main area using a list plus right-drawer pattern [1][7][14]

### A. Security analyst

**A1. Alert Queue (home)**
- Header counts by band, evidence class and severity [supported by current API: dashboard counts]
- Filter bar: band, evidence, severity, status, attack class, needs review, score range, search [supported by current API]
- Row fields per section 3 [supported by current API]
- Family indicator on row [supported by current API: family in detail]. Showing it on the row may need a list field [needs backend: include family id/size in queue response], **not confirmed**.
- Sort by score/time [supported by current API: ranked queue]. Arbitrary column sort [needs backend: sort param], **not confirmed**.
- Row click opens the detail drawer; keyboard j/k/Enter [frontend only]
- Quick verdict from the drawer [supported by current API: verdict submission]
- Bulk select + bulk verdict/status [needs backend: bulk verdict endpoint with per-alert guardrail results]
- "Assign to me" / owner column / "My queue" filter [needs backend: assignment/ownership]
- Group by attack class, src IP or signature [needs backend: aggregation endpoint]
- Saved views [needs backend: saved views], or store in local storage for demo
- Pivot: click IP or port to filter the queue by that value [supported by current API: search filter]
- Flow-time range filter [needs backend: timestamp range param]

**A2. Alert Detail (drawer, expandable to full page)**
- Explanation sentence + evidence class rationale [supported by current API: combined explanation]
- Signature clauses [supported by current API]
- ML prediction, confidence, top SHAP features [supported by current API]
- Flow 5-tuple and flow features, with a Table/JSON toggle as in Elastic [8] [supported by current API: flow]
- Family panel: similar alerts, agreeing-verdict progress toward 3 [supported by current API: family]
- Score-adjustment chain with guardrail sentences [supported by current API]
- Verdict history [supported by current API]
- Verdict actions: Confirm TP, Benign Positive (expected activity), False Positive, Needs investigation, Escalate to Tier 2. Preview the guardrail effect before submitting [supported by current API: verdict submission]. A dry-run preview would [needs backend: simulate verdict endpoint].
- Status change (claim → in progress → resolved/dismissed) [needs backend: status transition endpoint], unless verdicts already set status (**not confirmed**)
- Comments/notes thread [needs backend: comments]
- Tags [needs backend: tags]
- MITRE ATT&CK technique chip [needs backend: static class→technique mapping, could be a frontend lookup table]
- Related by entity: other alerts with the same src/dst IP [supported by current API: search filter]. A proper count [needs backend: related-by-entity query].
- Export alert JSON [frontend only]

**A3. Entity (IP) view**, should-have
- Alerts involving the IP, verdict mix, first/last seen, top peer IPs and ports [needs backend: entity aggregation endpoint]. Demo fallback: the queue pre-filtered by IP search [supported by current API].

**A4. Tier-2 / Escalated view**
- Queue preset: band = Tier 2 candidate or verdict = escalate [supported by current API: filters], if verdict is filterable. **Not confirmed**: filtering on verdict type [needs backend: verdict filter].
- Case grouping of escalated alerts [needs backend: cases/incidents], later.

**A5. My activity / Audit**
- Audit log with filters, restricted to the current user [supported by current API: audit log with filters]

### B. System administrator

**B1. Overview dashboard**
- Counts by band, severity, evidence class, status [supported by current API]
- Detection run summary: flows processed, detector hit counts, run time [supported by current API]
- Top attack classes, top src/dst IPs, top dst ports [needs backend: aggregation endpoint]
- Verdict breakdown and guardrail interventions [needs backend: aggregate over audit/verdicts]
- Flow-timestamp histogram by severity [needs backend: time-bucket aggregation]
- Analyst activity: verdicts per user, median time from first view to verdict [needs backend: aggregation; view events not currently logged]

**B2. Guardrail configuration**
- Current floors, caps, clamp and family threshold, each with its explanation sentence [supported by current API: guardrail config]
- Edit with validation plus an audit entry [supported by current API]. Edit endpoint existence **not confirmed**; if read-only [needs backend: update guardrail config].

**B3. Audit log**
- Append-only table with actor, action, target and before/after, filterable [supported by current API]
- CSV export [frontend only]

**B4. Detection runs**
- Run summary and history [supported by current API: detection run summary]. History across multiple runs **not confirmed**.

**B5. Users/roles**
- [needs backend: user management], later

### C. Evaluator

**C1. Experiment overview**
- Three-arm comparison (control / feedback / guardrails-off): macro F1, precision, recall [supported by current API: evaluation runs and metrics]

**C2. Per-class metrics**
- 8-class table with tabular numerals, plus a small-multiples bar chart per class across arms [supported by current API]
- Confusion matrix [needs backend: confusion counts], if not included in metrics

**C3. Run detail**
- Config, seed, verdict count and guardrail interventions per arm [supported by current API: evaluation runs]. Intervention counts per arm **not confirmed** [needs backend].

**C4. Explanation quality**, later
- SHAP feature frequency per class [needs backend: global SHAP aggregation]

---

## Priority list

**Must-have for demo**
1. App shell with role-based nav, top bar and theme tokens (light + dark). Severity and band shown by icon + text + colour [24][28].
2. Alert Queue with all current filters, header counts, ranked rows, monospace IPs and tabular-numeral scores.
3. Alert Detail drawer:
   - explanation first
   - signature vs model evidence columns
   - SHAP bars with text values
   - family progress
   - score-adjustment chain with guardrail sentences
   - verdict history
4. Verdict panel using industry labels (True Positive / Benign Positive / False Positive / Needs investigation / Escalate), with inline guardrail feedback after submit.
5. Click-to-pivot on IP/port into a filtered queue.
6. Overview dashboard from existing counts + detection run summary.
7. Audit log view with filters.
8. Guardrail config view.
9. Evaluator three-arm comparison + per-class metrics table/chart.
10. Full keyboard operation of queue, drawer and verdict actions; visible focus; 3:1 non-text contrast [25][26].

**Should-have**
1. Assignment ("Assign to me", owner column, My queue) [backend].
2. Comments/notes on alerts [backend].
3. Bulk verdict/status [backend].
4. Aggregations for top classes, top talkers, verdict mix and guardrail interventions [backend].
5. MITRE ATT&CK chip via static mapping.
6. Entity (IP) view [backend aggregation].
7. Saved views (local storage first).
8. Group-by in queue.
9. Verdict dry-run preview [backend].

**Later**
1. Cases/incidents grouping for Tier 2 [backend].
2. Investigation graph / timeline visualisation.
3. Tags, notifications, user management.
4. Time-series and time-to-verdict analytics.
5. Confusion matrix and global SHAP views for evaluator.
6. Exception/suppression rules from FP verdicts (Sentinel-style, time-limited [3]).

---

## Sources

1. https://learn.microsoft.com/en-us/azure/sentinel/incident-navigate-triage — Sentinel Incidents page layout (toolbar/grid/details pane), owner/status/severity/tags/comments, search defaults, mandatory closing classifications.
2. https://learn.microsoft.com/en-us/azure/sentinel/investigate-incidents — Incident details page: left panel, Overview widgets (timeline, similar incidents with similarity reason, entities, top insights), Entities tab side pane, investigation graph, activity log/comments.
3. https://learn.microsoft.com/en-us/azure/sentinel/false-positives — False positive causes; automation-rule exceptions from an incident (pre-filled entities, closing reason, 24 h default expiry); analytics rule exceptions.
4. https://learn.microsoft.com/en-us/azure/sentinel/manage-soc-with-incident-metrics — SOC efficiency workbook metrics (mean time to triage/closure, by classification/severity/owner/status), SecurityIncident schema.
5. https://learn.microsoft.com/en-us/azure/sentinel/fusion — ML correlation into low-volume, high-fidelity incidents; scenario titles; exclusion of detection patterns; alert-fatigue framing.
6. https://learn.microsoft.com/en-us/azure/sentinel/identify-threats-with-entity-behavior-analytics — UEBA investigation priority (0–10) vs anomaly score (0–1) and worked example; natural-language behaviour explanations; MITRE mappings.
7. https://www.elastic.co/docs/solutions/security/detect-and-alert/manage-detection-alerts — Elastic Alerts page: grouping visualisations, KQL, 24 h default time, status/severity/user/host filters, Open/Acknowledged/Closed, bulk actions, tags, assignees.
8. https://www.elastic.co/docs/solutions/security/detect-and-alert/view-detection-alert-details — Elastic alert flyout: Overview/Table/JSON tabs, About (reason, MITRE), highlighted fields, insights (entities, correlations, prevalence), Take action menu.
9. https://www.elastic.co/guide/en/security/8.19/rules-ui-create.html — Elastic severity definitions and risk-score ranges (0–21/22–47/48–73/74–100), severity/risk overrides, investigation guide, highlighted fields.
10. https://github.com/elastic/kibana/issues/234050 — Elastic closing reasons (True Positive, Benign Positive, False Positive, Duplicate, Automated Closure, Other, None) shipped for table/flyout; Cases proposal.
11. https://www.elastic.co/docs/explore-analyze/machine-learning/anomaly-detection/ml-ad-explain — Elastic anomaly score explanation: single/multi-bucket and characteristics impact, explanation section in UI.
12. https://help.splunk.com/en/splunk-enterprise-security-8/user-guide/8.2/mission-control/triage-findings-and-finding-groups-in-splunk-enterprise-security — Splunk ES triage fields (Owner, Status, Urgency, Disposition, Sensitivity); optional mandatory notes.
13. https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/mission-control/manage-analyst-workflows-using-the-analyst-queue-in-splunk-enterprise-security — Splunk analyst queue columns, status/urgency values, saved views, time range, bulk edit/Assign to me, timeline and distribution charts, row menu.
14. https://docs.securityonion.net/en/2.4/alerts.html — Security Onion Alerts: grouping, acknowledge/escalate/details icons, Hunt/PCAP/Add to case pivots, include/exclude filters, time picker.
15. https://docs.securityonion.net/en/2.4/cases.html — Security Onion Cases: assignee/status/severity/priority/TLP/PAP/category/tags, Comments/Attachments/Observables/Events/History tabs, escalation.
16. https://documentation.wazuh.com/current/user-manual/wazuh-dashboard/navigating-the-wazuh-dashboard.html — Wazuh dashboard navigation sections and module grouping (incl. threat hunting, MITRE ATT&CK).
17. https://www.ibm.com/docs/SSKMKU/com.ibm.qradar.doc/t_qradar_ug_offense_summary_investigate.html — QRadar Offense Summary: magnitude bar, cause description, top 5 source/destination IPs with Chained, last 10 events/flows, immutable notes, annotations.
18. https://developer.crowdstrike.com/falcon-mcp/modules/detections/ — CrowdStrike detection statuses (new/in_progress/reopened/closed), assignment, comments, tags, resolution tags true_positive/false_positive/ignored.
19. https://docs.cloud.google.com/chronicle/docs/review-alert — Google SecOps alert review quickstart; only general elements (graph, events, entity, severity, verdict) extracted; details not verified.
20. https://arxiv.org/abs/2503.02065 — "Too Much to Trust?" (CCS 2025): N=248 survey + 24 interviews; relevant, evidence-backed explanations drive acceptance; role-aware, context-rich XAI.
21. https://arxiv.org/abs/2506.09365 — ContextBuddy: recommended context cues improved accuracy 21.1% and cut validation time 24% in an IDS alert study.
22. https://arxiv.org/abs/2508.18947 — LLMs in the SOC: 45 analysts, 3,090 queries; analysts retain decision authority, AI used for sensemaking.
23. https://arxiv.org/abs/2601.04486 — Decision-aware trust signals: misaligned confidence displays amplify false negatives; calibrated, cost-aware signals recommended.
24. https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html — WCAG 1.4.1 Use of Color.
25. https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html — WCAG 1.4.11 Non-text Contrast, 3:1 for UI components, chart segments, state indicators.
26. https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html — WCAG 2.1.1 Keyboard.
27. https://developer.mozilla.org/en-US/docs/Web/CSS/font-variant-numeric — `tabular-nums` definition for aligned numerals.
28. https://v10.carbondesignsystem.com/patterns/status-indicator-pattern/ — Carbon status indicators: attention levels, combine symbol/shape/colour/type, filled vs outlined, status palette, avoid overuse.

**Located but not read (fetch blocked); do not cite as verified:**
- Alahmadi, Axon, Martinovic, "99% False Positives", USENIX Security 2022: https://www.usenix.org/conference/usenixsecurity22/presentation/alahmadi (403)
- Tariq et al., "Alert Fatigue in Security Operations Centres", ACM CSUR 57(9), 2025: https://dl.acm.org/doi/10.1145/3723158 (not fetched; mirror 502)
- NIST SP 800-61r3: https://csrc.nist.gov/pubs/sp/800/61/r3/final (landing page only; lifecycle content not read)
