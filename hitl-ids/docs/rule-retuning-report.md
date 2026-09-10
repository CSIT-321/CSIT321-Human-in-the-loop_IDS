# Rule Retuning Report

- rows: 5,000  |  malicious (attackType != Benign): 1,000
- as-shipped total signature hits: 63  (dedup 63, class-correct precision 0.8571, recall 0.0540)

## Per-rule retuning

| Rule | Target | Current hits | Best precision | Best recall | Reaches >= 0.90 |
|---|---|---|---:|---:|---|
| SIG-FTP-BRUTE-FORCE | Brute Force | 0 | 1.0000 | 0.7300 | yes |
| SIG-SSH-BRUTE-FORCE | Brute Force | 55 | 1.0000 | 0.2700 | yes |
| SIG-DOS-HIGH-RATE-FLOW | DoS | 0 | 0.0000 | 0.0000 | no |
| SIG-DDOS-HIGH-RATE-FLOW | DDoS | 0 | 0.3423 | 0.3800 | no |
| SIG-BOTNET-BEACON-FLOW | Botnet | 0 | 0.0000 | 0.0000 | no |
| SIG-WEB-ATTACK-FLOW | Web Attack | 5 | 0.7838 | 0.4833 | no |
| SIG-INFILTRATION-LONG-FLOW | Infiltration | 3 | 0.2500 | 0.0250 | no |

## Which rules can reach precision 0.90

- reach >= 0.90: SIG-FTP-BRUTE-FORCE, SIG-SSH-BRUTE-FORCE
- cannot reach >= 0.90: SIG-DOS-HIGH-RATE-FLOW, SIG-DDOS-HIGH-RATE-FLOW, SIG-BOTNET-BEACON-FLOW, SIG-WEB-ATTACK-FLOW, SIG-INFILTRATION-LONG-FLOW

## Coverage: retuned signatures vs ML (truly-malicious rows)

| Metric | Count |
|---|---:|
| caught by ML only | 794 |
| caught by retuned signatures only | 0 |
| caught by both | 200 |
| missed by both | 6 |
| total malicious | 1000 |

## Conclusion

The retuned signatures catch no malicious rows that the ML model misses (signature-only = 0). Every malicious row the signatures flag is already flagged by the ML model, so on this dataset the signature engine adds no incremental coverage.
