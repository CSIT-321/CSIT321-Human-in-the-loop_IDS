# Packet captures — download requirement (spike B and the start-to-end pipeline)

The packet captures are **not in git**. They are large (one capture day is 36–55 GiB) and public.
Download them with the script; nothing else needs an account or a key.

## What you need

| Item | Where | Size | Check |
|---|---|---|---|
| CSE-CIC-IDS2018 original captures | public AWS bucket `cse-cic-ids2018` (ca-central-1), folder `Original Network Traffic and Log data/<day>/pcap.zip` | per day 36–55 GiB; per host 1–850 MB | CRC-32 of every member, checked by the script |
| Suricata 8.0.7 (Windows x64 MSI) | https://www.openinfosecfoundation.org/download/windows/Suricata-8.0.7-1-64bit.msi | 36.7 MB | SHA-256 `f0acc93179a4ffb05d450bb08153a94bd5aa46b0e56b3b3be496cabf0b4152b7` |
| Npcap 1.90 (only `wpcap.dll` and `Packet.dll` are taken; no driver install) | https://npcap.com/dist/npcap-1.90.exe | 1.3 MB | — |
| Emerging Threats Open rules for Suricata 8 | https://rules.emergingthreats.net/open/suricata-8.0/emerging.rules.tar.gz | changes daily | record the SHA-256 of the copy you used |
| CICFlowMeter, Engelen et al. fork | https://github.com/GintsEngelen/CICFlowMeter (commit `4dd5319ad36457010d7a406505790b17a5828108`) | — | built with plain `javac` (Java 11 or later) |

All tools go in `hitl-ids/.tools/` and all captures in `hitl-ids/data/raw/pcap/`. Both folders are gitignored.

## Steps

From `hitl-ids/`:

1. **List a day's captures** (reads only the archive's directory, a few MB):
   `.venv/Scripts/python.exe scripts/fetch_capture.py --day Wednesday-14-02-2018 --list`
2. **Download the hosts you need** (each member is CRC-checked; a re-run skips verified files):
   `.venv/Scripts/python.exe scripts/fetch_capture.py --day Wednesday-14-02-2018 --member pcap/UCAP172.31.69.25 --member pcap/capWIN-J6GMIG1DQE5-172.31.64.80 --member pcap/capDESKTOP-AN3U28N-172.31.65.56`
3. **Install the tools** into `.tools/` (no system install):
   - Suricata: `msiexec /a Suricata-8.0.7-1-64bit.msi /qn TARGETDIR=<abs path>\.tools\suricata`
   - Npcap: extract `wpcap_x64.dll` and `Packet_x64.dll` from `npcap-1.90.exe` with 7-Zip; copy them next to
     `suricata.exe` as `wpcap.dll` and `Packet.dll`.
   - ET Open: extract the archive into `.tools/et/`.
   - CICFlowMeter: `git clone` the fork into `.tools/cicflowmeter`, then run
     `bash ../analysis/spike/build_cicflowmeter.sh`.
4. **Run the pipeline** for the downloaded hosts:
   `bash ../analysis/spike/spike_pipeline.sh Wednesday-14-02-2018 172.31.69.25 172.31.64.80 172.31.65.56`
   It repairs each capture (`scripts/repair_pcap.py`), runs Suricata, and runs CICFlowMeter.

## Why the repair step exists

Some captures hold a damaged record header (measured: caplen 37,496,642 against snaplen 65,535 in host
`172.31.65.56`). Suricata and jnetpcap stop reading at that record and lose the rest of the file — Suricata read
571,670 of 714,224 packets. `scripts/repair_pcap.py` skips the damaged bytes (298 bytes in 3 places in that file)
and keeps every whole record.

## The three spike hosts (2018-02-14)

| Host | Role in the demo | Capture size |
|---|---|---|
| `172.31.69.25` | Victim of all 134 brute-force flows (80 FTP from `18.221.219.4`, 54 SSH from `13.58.98.64`) | 852,795,392 B |
| `172.31.64.80` | Source of `AL-00478`, the false-positive story | 372,945,975 B |
| `172.31.65.56` | Benign host (7 demo flows) | 215,603,953 B |
