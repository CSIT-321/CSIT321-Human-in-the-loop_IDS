# Final Evaluation Protocol V3 — FROZEN / UNOPENED

This directory contains inputs and methodology, **not experimental results**.
Read [the protocol](../../docs/final-evaluation-protocol-v3.md) before opening a run.

- `protocol-v3.json`: pre-registered design, populations, metrics, safeguards and limitations.
- `manifest.json`: exact runtime, policy versions/hashes, workload, oracle, documentation and tooling hashes.
- `workload/operational-workload.jsonl`: 200 controlled Suricata-format EVE alert records only.
- `workload/trusted-context.json`: frozen synthetic per-alert trusted context prerequisites.
- `oracle/external-outcomes.json`: evaluator-only outcomes; forbidden in runtime worker.
- `expected/workload-structure.json`: phase/stratum/order/pattern/identity metadata; not imported into product evidence.
- `result-record.schema.json`: paired post-decision record schema for the later evaluator.

Generate a comparison copy with `python scripts/build_protocol_v3_workload.py --out <new-directory>`
from `hitl-ids`. The generator refuses to overwrite this frozen directory.
Run `python scripts/validate_protocol_v3.py` for read-only preflight.
The separate eight-alert development smoke is never the final workload.

Do not infer an experimental percentage from workload design or development smoke results.
Exact false-positive lessons may activate at support 3, while Selective Review requires support 5.
The real 10% deterministic audit sampling is preserved; no identities were selected to avoid it.
Real Suricata engine/PCAP integration was validated separately. V3 does not run a detector accuracy study.

The frozen bundle stays unchanged. A future explicitly authorized opening creates an external
receipt and fresh result directories, not edits to this bundle or to Protocol V2.
