# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `4bce8c8194f0a582c5b262bf3e791878977c4c4ad4bbddfa956ff593f54b639c`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `f2c7708a7a32014709c8d63541980ae71290856388eee6b6a519b9a2b5638a16`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `ca176055f1d08805bf61314e34acb40fbc1fb4d7ec7e75abd56b0698d23c2788`)
