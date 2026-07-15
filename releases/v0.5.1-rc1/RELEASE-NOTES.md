# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `c86adc163ac670ef574d22d0cb1e2b67f01fea9e3d5081ff1c836d77f2cf83ac`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `47ff1d99ac7c02388183b7175f7cb92ad11c7f793e74eb0b9b57471901a3452b`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `88fc1643c87907b07195f8f8aa16380a71852132de8edfe3fa4f44ff37ea58ce`)
