# Canonical Verdict and Selective Review safety

R01: Selective Review reads the latest canonical Analyst Verdict directly, using
its authoritative revision ordering. `canonicalVerdict` records the Verdict
reference, revision and outcome in ReviewInputs. Every existing Verdict outcome
sets the existing human-verdict guard. A new Verdict or correction changes the
input version and recalls a persisted deferral without a Memory contribution.
No-Verdict inputs preserve their previous hash shape; historical snapshots remain
readable. KPI, queues, detail and assistance use the existing effective-review
projection and existing reload/polling paths.

R02: unsafe_suppression_count counts distinct alerts with at least one recorded
No Immediate Review decision strictly earlier than their current authoritative
unsafe human outcome (confirmed_malicious or suspicious). Authority is selected
before checking time: latest Tier 2 primary-Case conclusion/Finding, otherwise
latest canonical Tier 1 Verdict, otherwise primary historical Memory outcome.
Linked alerts do not inherit a Case conclusion. Timestamps are compared as aware
datetimes, including microseconds; equal timestamps are not later.

This is a current-outcome metric, not a cumulative ever-unsafe event count.
A malicious Verdict corrected to Expected Activity/False Positive no longer
counts. An expert Expected Activity or Inconclusive supersedes an earlier unsafe
Tier 1 conclusion; a later malicious expert conclusion supersedes a safe Tier 1
Verdict. Inconclusive is not proof of safety. Repeated deferrals, revisions and
optional learning contributions never multiply an alert's vote. All original
history remains intact.

Reads do not migrate, write decisions or contribute Memory. Detection,
classification, priority, routing, Memory policy, response and Case lifecycle
are unchanged. Verdict authoring remains an independent explicit human action.

Data basis remains: Observed local decisions and human outcomes; not a measured
real-world workload benefit. Final prospective evaluation requires a future new
protocol after validation. Protocol V2 and its pinned hashes remain unchanged;
no collection is opened.

R03 role-specific VerdictLearning links remain MINOR / DO NOT BLOCK backlog.
