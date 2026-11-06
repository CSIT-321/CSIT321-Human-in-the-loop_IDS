# Live-demo replay window — measured (2026-11-06)

Built by `analysis/spike/build_replay_window.py` from spike B (capture day 2018-02-14, 3 hosts).
Output (gitignored): `hitl-ids/data/spike/Wednesday-14-02-2018/replay-window/` — `flows.csv` (detection input),
`eve.jsonl` (linked Suricata alerts), `truth.json` (labels, evaluation only).

## Ground truth for the whole spike day (new)

The corrected release's day file `Wednesday-14-02-2018.csv` (inside the local 10.4 GB zip) labels our
CICFlowMeter flows: **359,348 of 362,143 matched** by 5-tuple + start time (`truth_extract.py`, `window_measure.py`).
On the full day, measured against those labels:

| Rule | Escalated | Correct | Wrong | Missed attacks |
|---|---|---|---|---|
| E1-flow-rule | 287,591 | 287,271 | **40** labelled benign (280 unlabelled) | **0** |

Precision 0.99986, recall 1.00000. All 40 "benign" E1 flows come from the two attackers to the victim's FTP/SSH
ports (`e1_timeline.py`: 30 × 2-packet FTP flows, 10 × 24–27-packet SSH flows) — failed or short attempts the release
labels BENIGN. They are not traffic from an innocent host. The earlier statement "0 errors" (`SPIKE-RESULT.md`,
check by attacker IP) holds by host; by the release's per-flow labels it is 40 of 287,591.

## Window content

| Slice | Time (UTC) | Flows | Flagged | E1-flow-rule | E1-suricata | False positives | Flagged groups |
|---|---|---|---|---|---|---|---|
| S1 false positive | 12:34–12:47 | 9,546 | 11 | 0 | 0 | **11** (incl. the `AL-00478` flow, `ml_only` 92.7) | 3 |
| S2 FTP onset | 14:33–14:36 | 5,361 | 5,100 | 5,100 | 0 | 0 | 1 |
| S3 SSH onset | 18:01–18:13 | 12,609 | 11,613 | 11,613 | **6** | 0 | 1 |
| **Total** | 28 min of capture | **27,516** | 16,724 | 16,713 | 6 | 11 | **5** |

4,270 Suricata alerts link to window flows (benign RDP noise in S1, the SSH scan alerts in S3).

## What the demo shows with grouping on

27,516 flows → 16,724 flagged → **5 grouped Tier 1 / Tier 2 items**: 3 false-positive groups for Tier 1 to judge,
and 2 attacker groups that E1 escalates automatically (one FTP, one SSH; the SSH group carries both E1 branches).

## New-groups limit (decision D3a replacement)

Measured peak of **new** E1 groups per minute over the full day: **1**. Default chosen: **M = 5 per minute**
(5 × the measured peak), Admin can change it. Inference: a real multi-attacker campaign would raise the peak;
this day has only 2 attackers, so M is set from thin evidence.
