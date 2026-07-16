# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0.

## Certification

The baseline acceptance run against the disposable `TESTE_CODEX` Set finished with:

- 65 tools
- `release_ready=true`
- 55 `live_passed`
- 8 `offline_passed`
- 2 `manual_required` (expected: `save_set` and `quit_ableton`)
- 0 `failed`

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `971326e00b974d61387b2be10c8fb6069459d322b9fe7513e06f8dd12a93a3a4`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `f57d55d03607d4d282c8865aee1ff468948a6fcb40c8ec9f5ac3ff8c8946238d`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `0b2bb31c117a3bf7fe2e8d13c6b9a5cfb0d5aa462bf4737f75dd1ce2e729ea38`)