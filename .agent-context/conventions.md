# Conventions

## Python

- Runtime `>=3.10`; use `from __future__ import annotations` in modules.
- Ruff: line length 100, target py310, rules `E,F,I,UP,B,SIM`, ignoring `UP031`.
- Mypy is strict for `ableton_mcp_server`.
- Request boundaries use Pydantic models; do not pass unchecked MCP arguments directly to a bridge.
- Expected bridge failures remain typed/structured. Unexpected failures may surface as internal errors but must not be mislabeled as transport death.

Configuration: `pyproject.toml`.

## TypeScript Extension

- Package is ESM source, built as a bundled CommonJS Extension entry.
- TypeScript is strict and targets the installed beta SDK through local vendor tarballs.
- Activation initializes and stores one SDK context; deactivation stops the server and clears it.
- JSON-RPC handlers are asynchronous and return serializable result objects.

Configuration: `AbletonMCPServer_Extension/package.json`, `tsconfig.json`, and `build.ts`.

## Naming and boundaries

| Item | Convention | Example |
|---|---|---|
| MCP tool / remote command | `snake_case` | `get_session_info` |
| Pydantic request | `PascalCase` + `Request` | `RunBatchRequest` |
| Error code | `SCREAMING_SNAKE_CASE` | `LIVE_UNAVAILABLE` |
| Path ID | indexed slash path | `track:2/device:1` |
| Extension manifest name | PascalCase | `AbletonMCPServer` |

## Adding or changing a remote operation

1. Classify it in root `contracts.py` as read, allowed mutation, blocked, and/or WebSocket-routed.
2. Add or update the request model and `TOOL_REQUEST_MODELS` entry.
3. Register the MCP function in `server.py` and `PUBLIC_TOOL_FUNCTIONS` when public.
4. Implement exactly one Live-side route: Remote Script for Python LOM or Extension for SDK-only behavior.
5. Run `python scripts/vendor_contracts.py` whenever contracts change.
6. Add model, registry, forwarding, handler, error, and vendoring tests as applicable.
7. Update `docs/TOOL_REFERENCE.md`, architecture/quirk docs, and version metadata when public behavior changes.

Do not treat a proposal in `prompts/` as implemented until all these layers exist.

`live_find_device` and `live_find_clip` return fresh session-local locators. Their path IDs are not persistent handles; callers must search again after structural edits.

Dry-run behavior is deliberately bounded: only `set_tempo` and `create_clip` accept `dry_run`, and a dry run must validate without writing or opening an undo step. Installer previews use `ableton-mcp install-script --dry-run`; the PowerShell `-DryRun` switch delegates to that command.

## Deferred Live writes

Python LOM work must execute through the Remote Script request processor on `update_display()`. For writes that settle asynchronously, use the existing generator/read-back pattern and contract retry/tolerance values. Never block Live's UI thread with `sleep()`.

## Verification

Canonical local checks:

```powershell
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
```

Extension:

```powershell
cd AbletonMCPServer_Extension
npm run build
```

`doctor` proves TCP round-trip to a running Live instance. The guarded acceptance runner is manual and must target a disposable Set.

## Git and release hygiene

- Preserve unrelated dirty changes; inspect status before and after work.
- Do not push, tag, publish, or rewrite history without explicit authorization.
- Keep `pyproject.toml`, `manifest.json`, Extension package version, changelog, and release notes aligned.
