# Optional provider laboratory

The deterministic groove generator is the complete runtime and has no neural
dependency. A provider is eligible only after an offline, allowlisted lab run;
the runtime never downloads models, opens a network connection, or accepts an
executable, command, path, token, or model location from a request.

Published `groove.provider-gate.v1` thresholds:

| Gate | Threshold |
| --- | ---: |
| Contract invalid candidates | 0 |
| Deterministic fallback pass rate | 1.0 |
| Reproducibility match rate | 1.0 |
| HVO F1 | >= 0.90 |
| Feature MAE | <= 0.05 |
| Privacy path leaks | 0 |
| Blocked lineage | 0 |
| p95 latency | <= 5.0 s |
| Peak memory | <= 512 MiB |
| Response bytes | <= 262144 |
| Candidate events | <= 2048 |

Reports contain bounded gate measurements, identities, a payload digest, and a
lab signature. They never contain source paths, raw MIDI, payload bytes,
notes, SQL, credentials, or provider diagnostics. Any failed gate keeps the
provider disabled; every provider failure returns the seeded deterministic
artifact with a stable reason.

The subprocess adapter uses only the closed `hello`, `generate`, and
`shutdown` IPC methods. Frames are UTF-8 length-prefixed JSON (256 KiB maximum,
depth 8), with 2 seconds startup, 5 seconds generation, 1 second shutdown,
2 seconds CPU, 512 MiB memory, and 16 KiB sanitized stderr limits. Process
trees are terminated once on timeout, protocol, output, or resource failure;
there is no retry.
