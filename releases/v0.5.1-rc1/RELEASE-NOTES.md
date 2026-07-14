# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `3b3ec2adc095525b76787497dcc57415b40f6d3ec7d1d8b3ee0026f0407ee915`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `01d83e8aacb7848237a0522496ce875fd2fece46306e9630ee10ace72fef178d`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `2b4448cb263c338aed4d1f4697badb5f2b3715ea955513987e84ce7eab5265e4`)
