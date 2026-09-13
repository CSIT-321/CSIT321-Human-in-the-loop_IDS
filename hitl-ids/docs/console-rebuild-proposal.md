# Console rebuild — proposal

**Status: R1 DONE (2026-09-13); R2 next.** Logged in `plan-changelog.md` v1.22.

**What it is.** A full redesign of every screen of the web console (`apps/web`), for all three roles.
- **Look:** the user's design reference, the *SOC Analyst Workstation* screen from their Figma Make file.
- **Workflow and interactions:** how real SOC/IDS consoles work.

**Evidence.** [`research/soc-console-research.md`](research/soc-console-research.md), drawing on 28 sources read: Microsoft Sentinel, Elastic Security, Splunk ES, Security Onion, QRadar, Wazuh and CrowdStrike docs; WCAG; four papers on analyst trust in explainable ML. Anything it could not verify is marked there.

## 0. Decisions (user, 2026-09-13)

| Question | Decision |
|---|---|
| Backend scope | **Frontend + core backend.** Status and assignment (B1), notes (B2), overview breakdowns (B4), IP entity view (B5) and queue additions (B6). Bulk actions, run history and cases come later. |
| Verdict labels | **Industry labels on screen:** True Positive · Benign Positive · False Positive · Needs investigation · Escalate to Tier 2. API values stay the same. |
| Design source | **A screenshot of the Figma Make screen.** The Make file cannot be read through the Figma MCP, so tokens are taken from the image. |

---

## 1. Design reference — the SOC analyst workstation

### Layout (at 1280 px and wider)

**Top bar:** brand, workstation name and tier, feed state, count of new alerts, UTC clock, user and tier.

**KPI strip:** critical · high · medium · unresolved · escalated · false positives · total events, plus a threat-level meter.

**Three columns:**
- **Alert queue** (left, ~340 px):
  - severity tabs: All / Critical / High / Medium / Low / Info
  - a filter box
  - stacked alert cards, each with a severity dot and label, title, relative time, src → dst, and asset
- **Alert detail** (centre):
  - a severity-accent rule down the left edge
  - ID and tier chip, then the title
  - actions: Mark FP · Escalate · Close Alert
  - two meters: detection confidence and false-positive probability
  - tabs: Overview · Raw log · MITRE · Notes
  - a key/value field list
  - an event timeline along the bottom
- **Context rail** (right, ~340 px): network topology · threat intel · related alerts · geolocation · quick actions.

### Visual language

- A near-black background, with square-ish panels separated by 1 px rules and no shadows.
- Section labels in uppercase, letter-spaced monospace.
- Data in monospace: IPs in blue, assets in amber.
- Severity shown as dot + word + colour.
- One blue primary action.

### Tokens

Taken from the image and adjusted for WCAG contrast during R2.

| Token | Value | Use |
|---|---|---|
| ground | `#0b0d10` | page |
| panel | `#111418` | columns, list rows |
| raised | `#171b21` | inputs, selected row |
| rule | `#242a33` | 1 px dividers |
| text / muted / dim | `#e6e8eb` / `#8a919c` / `#5c636e` | three text levels |
| primary | `#2f81f7` | primary action, active tab, focus |
| link / data-IP | `#58a6ff` | IPs, alert IDs |
| critical / high / medium / low / info | `#f85149` / `#f0883e` / `#e3b341` / `#3fb950` / `#58a6ff` | severity, always shown with a label |
| type | IBM Plex Sans for titles and body · JetBrains Mono for labels and data | |

**Brand stays "IDS Console".** The reference's "SENTINEL//IDS" wordmark is dropped, because Microsoft Sentinel is a real product.

### What each element shows here — real data only

The reference shows a live enterprise SOC. This system scores **recorded lab traffic**
(CSE-CIC-IDS2018). It has no hostnames, geolocation, threat-intel feeds, raw packet logs or response
tooling. Each design element is handled one of three ways, and nothing is invented:
- **kept**, where real data exists;
- **re-pointed**, where a real equivalent exists;
- **dropped**, otherwise.

| Design element | In this console | Data |
|---|---|---|
| LIVE · Pause Feed | **Recorded · run #1** badge; no pause | detection run |
| "47 NEW" | count of alerts with status `new` | B1 status |
| UTC clock | kept | client |
| a.kowalski · T2 | demo user and role label, marked as the auth stub | session |
| KPI strip | Critical · Needs review · Tier 2 candidates · Unresolved · Escalated · False positives · Total alerts | dashboard + B1/B4 |
| Threat level meter | **dropped** — a single "threat level" would be an invented composite | — |
| Severity tabs | All · Tier 2 · Needs review · Corroborated · Model only · Nothing flagged. Queue bands carry the triage meaning, and severity in this data is only Critical or Informational. | queue filters |
| Card: title · time ago · asset | predicted attack class (or "No detection") · flow timestamp · **dst IP:port** instead of an asset name | alert summary |
| Detection confidence meter | **model confidence** (ML probability), with its band | ML panel |
| False-positive probability meter | **dropped** — the model is not calibrated for this, and the research warns that uncalibrated confidence misleads analysts | — |
| Mark FP · Escalate · Close Alert | the five verdicts (industry labels) plus **Claim** / **Close** status actions | verdicts + B1 |
| Overview · Raw log · MITRE · Notes | Overview (explanation, evidence, adjustment chain) · **Flow record** (all features as table/JSON) · MITRE (sourced static mapping) · Notes (thread) | detail + F1 + B2 |
| Field list | source IP:port, destination IP:port, protocol, duration, packets, bytes, rule matched, evidence class, band, flow time, source record | flow panel |
| Geolocation | **dropped** — there is no geo data, and the testbed addresses are cloud-internal | — |
| Event timeline | **alert history:** flow observed → detected by rule or model → verdicts → guardrail actions → family learning | audit log for the alert |
| Network topology | **flow diagram:** source IP → destination IP:port over protocol, drawn from the 5-tuple; peers come from the entity view | flow + B5 |
| Threat intel (AbuseIPDB, VirusTotal, Shodan, ASN) | **detector evidence:** signature clauses ∣ model top features | signature + ML panels |
| Related alerts | family members, plus other alerts sharing the IP, each with its reason | family + B5 |
| Quick actions: Hunt IOCs · Blocklist · Isolate · IR ticket | **real actions only:** all alerts for this IP · open the family · copy IOC · export alert JSON. Response actions are out of scope for recorded flows. | queue pivot, B5, client |

### Pre-build plan (frontend design skill, Layer 1)

- **Visual thesis.** A dense, instrument-panel workstation for someone triaging on a long shift. The background recedes and data carries the colour. Monospace labels read like console output. Severity and queue band stay legible at a glance without relying on colour.
- **Content plan.** A primary workspace (queue → selected alert), orientation above it (top bar and KPI strip), and an inspector to the side (context rail). The same shell carries the overview dashboards, entity view, admin and evaluator screens.
- **Interaction plan.**
  - Keyboard triage: `j`/`k` move the queue selection and the detail panel swaps without a page load.
  - After a verdict, the score-adjustment chain steps in left to right so the guardrail binding is visible, and the row slides to its new band position.
  - A family-progress meter fills toward the three-verdict gate.
  - All of this stays static under `prefers-reduced-motion`.

---

## 2. What the research says a SOC console must be

- **A queue beside a details pane**, not a page per alert.
- **Explanation first:** our combined explanation, signature clauses and TreeSHAP.
- **Four triage controls:**
  - owner — **the column exists, unused**
  - status — **the column exists, unused**
  - severity
  - closing classification — our verdicts
- **Industry closing labels**, which map one-to-one onto our verdicts.
- **Related context as a first-class element.** Our *family* is Sentinel's "similar incidents".
- **Trust:** short, evidence-backed explanations and a confidence band, with guardrail floors kept separate from model confidence.
- **Accessibility:** never colour alone; 3:1 contrast on marks and state indicators; full keyboard operation; tabular numerals.

## 3. Verified against the code

| Item | Fact |
|---|---|
| Sort by column | **Supported** — queue · combined_score · detection_score · created_at · severity, with direction |
| Guardrail edit | **Supported** — `PUT /api/config/guardrails`, admin only, reason required, audited |
| Status | **Column exists** (`alerts.status`: new / claimed / in_progress / resolved / dismissed, indexed). No endpoint changes it, and the feedback service never sets it, so every alert is `new`. |
| Owner | **Column exists** (`alerts.owner_id` → `users.id`, indexed). No endpoint sets it. **No migration needed.** |
| Notes thread | **Missing** — only a verdict carries one `note`. Needs a new table, which means a **migration**. |
| Filter by verdict | **Missing** — rows carry only `hasFeedback` |
| Detection run history | **Missing** — only the latest run |
| Aggregations | **Missing** |
| Entity (IP) view | **Missing** — queue search already filters by IP |

## 4. Screens per role

**Shell (all roles):**
- top bar and KPI strip
- role-scoped navigation
- dark first, with a light theme from the same tokens
- keyboard: `j`/`k` move, `Enter` opens, `Esc` closes, `?` lists shortcuts

| Role | Screens |
|---|---|
| Security analyst | **Workstation** (home: queue · detail · context rail) · **Overview** (top classes, top source/destination IPs and ports, verdict mix, guardrail interventions, flow-time histogram) · **Entity (IP)** · **Tier 2 / Escalated** preset · **My activity** |
| System administrator | **Operations overview** (run summary, detector hit counts, verdicts per analyst, guardrail interventions) · **Guardrails** (form, each setting's explanation, log) · **Audit trail** (filters, CSV export) |
| Evaluator | **Experiment overview** (three arms, deltas as measured, the wrong-way banner) · **Per-class metrics** (8 classes, small multiples, saturation, precision@k) · **Run detail** (pre-registration, who moved, guardrails prevented) |

## 5. Backend additions

All of these are contract-first and built by Claude, because they touch contracts, feedback or audit.

| ID | Addition | Notes |
|---|---|---|
| B1 | `POST /api/alerts/{ref}/status` (claim · in progress · resolve · dismiss) and `POST /api/alerts/{ref}/assign` | Uses the existing `status` and `owner_id` columns and audits `ALERT_STATUS_CHANGE`. Transition rules are defined and tested. |
| B2 | `GET/POST /api/alerts/{ref}/notes` | Append-only; a new `alert_notes` table, added by migration |
| B4 | `GET /api/dashboard/breakdowns` | top IPs, ports, classes, verdict mix, guardrail interventions, flow-time histogram |
| B5 | `GET /api/entities/ip/{ip}` | alerts, verdict mix, first/last seen, peers, ports |
| B6 | Queue: `verdict`, `owner` and flow-time range filters; `familySize` on rows | contract additions |
| F1 | MITRE ATT&CK class → technique table | Frontend. Each mapping is sourced from attack.mitre.org before it ships. |
| Later | B3 bulk verdict/status · B7 run history · cases | — |

## 6. Build order (by dependency; no dates)

| Step | Work | Delegation |
|---|---|---|
| R0 | Design intake: tokens, component inventory, data mapping (this document) | Claude |
| R1 ✅ | B1, B2 (with migration), B4, B5, B6; OpenAPI regenerated; Python tests. **Done:** 411 Python tests, web typecheck and `check:api` clean, 103 web tests, rehearsal holds | Claude |
| R2 | New design system: tokens, shell, KPI strip, primitives (dense list, tabs, meters, key/value list, timeline, flow diagram, severity marker) | Claude writes tokens and primitives; DeepSeek builds from them |
| R3 | Analyst workstation: queue, detail, context rail, verdict and status actions, keyboard | Components delegated; the verdict panel and guardrail messaging stay with Claude |
| R4 | Overview dashboards and entity view | Delegated, reviewed |
| R5 | Admin and evaluator screens | Delegated, reviewed |
| R6 | Re-verify the S16 gate: web tests, `rehearse_demo.py`, updated `npm run e2e`, recaptured demo guide, PUM regenerated from the product, lifecycle docs | Claude |

Workers run under `timeout 1500`, at most two at a time (HANDOVER §6).

## 7. Risks

- **Tests match visible wording.** New labels and layout break the web tests, the browser narrative and the guide. R6 re-passes the S16 gate to cover this.
- **Notes need a migration.** Schema changes after S9 must be migrations with tests.
- **Stub authentication.** "Claim" assigns the alert to the demo user of the chosen role, and the screen says so.
- **No real-time data.** Time-to-verdict reflects session activity only and is labelled that way.
- **Screenshot fidelity.** Exact values are matched by eye, then adjusted for contrast.
