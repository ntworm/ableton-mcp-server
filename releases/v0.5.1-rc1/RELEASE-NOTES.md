# v0.5.1 — Slice 1 stabilization

This release candidate bundles the Slice 1 corrections on top of v0.5.0. It is **not yet certified** — the baseline acceptance run against the disposable `TESTE_CODEX` Set must finish with zero `failed` rows before promotion to a stable tag.

## Highlights

- 65-tool capability catalog is the single source of truth for the FastMCP surface and the per-tool certification report.
- `live_fade` distributes its writes across the requested `duration` via `time.monotonic` and never blocks the Live main thread.
- The Extension WebSocket binds explicitly to `127.0.0.1:9889`; LAN exposure is forbidden by design.
- Cross-bridge error taxonomy adds `CAPABILITY_UNAVAILABLE`, `AMBIGUOUS_MATCH`, `VERIFICATION_FAILED`, `ACCEPTANCE_GUARD_FAILED` on top of the existing transport codes.
- `ableton-mcp acceptance --profile baseline` runs the full 65-tool surface against the disposable Set, returns a CertificationReport, and the CLI exits non-zero on any `failed` row.

## Artifacts

- `ableton_mcp_server-0.5.1-py3-none-any.whl` (sha256 `e5e6033970da554eca99dd1cb92507cef124f1e335113a21d4867e0570199a7a`)
- `AbletonMCPServer_RemoteScript-0.5.1.zip` (sha256 `5a70b3ba3387f6975723dcb428ccee8a924cb2e95296255a6ce2d5ecdd652ab9`)
- `AbletonMCPServer-Extension-0.5.1.ablx` (sha256 `911760a11972b29fb0e914ceceaf5285ac69d9e09e51a51d47d0ce711a8a645d`)
