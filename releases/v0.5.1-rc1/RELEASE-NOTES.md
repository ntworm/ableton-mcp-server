# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `5f97433f9fcd42f9a5516e063b228ecc5643bb3f542d9dd37016fe82c7cf8a87`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `5a70b3ba3387f6975723dcb428ccee8a924cb2e95296255a6ce2d5ecdd652ab9`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `1975eeaeb7b83a0ddfb6dd706e928d0d154696392f8c3af61be94f84153e55c5`)
