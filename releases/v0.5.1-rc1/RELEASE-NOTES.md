# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `9a6d96880f9df646c3bc3468844c35abfe1137979872d7cf922c355547a91a57`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `17a51ed79076d4054dbf9a8ff8ab4a48b573e634d14df19118b7593cb65f0ff9`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `dcfeef80ce3c01cd5bfa4f3e208bad302453ab60298cd47a5adf98abf72a0b5f`)
