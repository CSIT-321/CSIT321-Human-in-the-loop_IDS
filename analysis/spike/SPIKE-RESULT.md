# Spike B result — packets to E1 on capture day 2018-02-14

Date: 2026-11-06. Branch `feat/tier-views-auto-escalation`. Product code unchanged (detection = approved engine as is).

## Input

3 host captures from `Wednesday-14-02-2018/pcap.zip` (public S3), CRC-verified by `scripts/fetch_capture.py`:
`172.31.69.25` (brute-force victim), `172.31.64.80` (source of `AL-00478`), `172.31.65.56` (benign). 1.4 GB.

## Pass criteria (decided 2026-11-05)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Suricata and CICFlowMeter both run on the same packets on this PC | **PASS** | Suricata 8.0.7 + ET Open: 76,443 alerts. CICFlowMeter fork (built with `javac`, Java 21): 362,146 flows. Pipeline 3 min 23 s. |
| 2 | >= 90% of Suricata alerts link to a CICFlowMeter flow (addresses, ports, time) | **PASS — 0.9997** | 76,417 of 76,443 linked (`link.py`) |
| 4 | One alert where both detectors agree arrives live and E1 escalates it | **PARTIAL** | E1 fires on real-packet flows through the unchanged approved engine (batch `run_detection`): 287,591 E1-flow-rule, 46 E1-suricata. **Not shown: live arrival through the console** — the live path does not exist yet (Phase B). |

## Findings

1. **E1 is correct on real packets.** All 287,591 E1 flows involve one of the 2 known attacker IPs; **0** E1 flows
   involve any other host (`check_e1.py`; "attacker" = endpoint is `18.221.219.4` or `13.58.98.64`, inferred from
   the labelled sample). Of the 134 labelled brute-force flows in the demo sample, 133 were matched and all 133 are
   `corroborated` + E1.
2. **The false-positive story reproduces.** `AL-00478` comes out `ml_only`, predicted `Web Attack`, score **92.7**
   (demo: 99.89). Suricata raised no alert on it. The score differs, cause not measured (likely the missing feature
   below, or the fork's flow-split differences).
3. **Volume.** One day of real brute force is **287,591 flows**, not 134. The demo sample is a 5,000-row
   stratified sample of 63 million flows. A real start-to-end run produces a queue in the hundreds of thousands.
4. **BLOCKER for decision D3a — the share limit fails on real data.** 90% over the last 500 arrivals blocks
   **277,495 of 287,591 correct E1 escalations** (peak share 0.988). On `demo.db` it blocked 0. The demo sample hid
   the burst because sampling thinned it.
5. **Alert fatigue, shown by our own pipeline.** Without grouping, one attacker becomes 287,591 Tier 2 cases.
   Grouping by source IP (decision D3b) would make it **2** items — but D3b groups Suricata alerts only.
6. **Suricata adds little on this day.** It flags the SSH attacker (`ET SCAN Potential SSH Scan`, 46 alerts, all also
   E1-flow-rule). It has **no FTP brute-force alert**. Most of its 76,443 alerts are `ET INFO RDP - Response To
   External Host` (54,742) on one benign host — noise a grouping rule must absorb.
7. **One model feature is missing.** The fork's CSV lacks `Total TCP Flow Time` (1 of 82 features); the spike set it
   to 0. The corrected dataset release added that column after the fork.
8. **Damaged captures.** Host `172.31.65.56` has 3 damaged record headers; without repair Suricata reads 571,670 of
   714,224 packets. `scripts/repair_pcap.py` fixes it (298 bytes dropped).
9. **Cost.** Detection of 362,143 flows took **62 min** and a **6.2 GB** database (`spike.db`). The approved engine
   is a batch engine; it is not fast enough for a whole day as a live feed.

## Files

- Download requirement: `hitl-ids/data/raw/PCAP-DOWNLOAD.md`. Scripts: `hitl-ids/scripts/fetch_capture.py`,
  `hitl-ids/scripts/repair_pcap.py`.
- Spike tools: `analysis/spike/` (`build_cicflowmeter.sh`, `run_suricata.sh`, `spike_pipeline.sh`, `link.py`,
  `spike_detect.py`, `check_e1.py`, `eve_summary.py`, `pick_hosts.py`).
- Outputs (gitignored): `hitl-ids/data/spike/Wednesday-14-02-2018/` (8.4 GB), captures `hitl-ids/data/raw/pcap/`
  (1.4 GB), tools `hitl-ids/.tools/` (296 MB).
