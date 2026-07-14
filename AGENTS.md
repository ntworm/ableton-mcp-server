# AGENTS.md — ableton-mcp-server

## Purpose

`ableton-mcp-server` v0.5.1 exposes 65 MCP tools for inspecting and safely mutating an Ableton Live Set. A Python FastMCP process coordinates a Live MIDI Remote Script over TCP and an Ableton Extension over WebSocket. The repository is MIT-licensed and targets Windows-hosted Ableton Live; WSL clients must launch the Windows-native executable.

## Read order

1. This file for repository-wide rules.
2. `.agent-context/generated/summary.md` for compact inventory evidence.
3. Only the relevant `.agent-context/{architecture,conventions,dependencies,hot-files,risks}.md` file.
4. Current source, tests, Git evidence, and canonical docs for task-specific claims.

Canonical project docs are `README.md`, `docs/ARCHITECTURE.md`, `docs/TOOL_REFERENCE.md`, and `docs/KNOWN_BUGS.md`. Files under `prompts/` are proposals/handoffs and can be partially superseded; verify them against current code before acting.

## Architecture

```text
MCP client -> FastMCP/Python stdio
               |-> TCP JSONL 127.0.0.1:9888 -> Remote Script -> Live Python LOM
               \-> WS JSON-RPC :9889          -> Extension    -> Live Node LOM
```

- `ableton_mcp_server/`: public tools, validation, routing, diagnostics, CLI, acceptance runner.
- `AbletonMCPServer_RemoteScript/`: Live-side TCP server and main-thread Python LOM execution.
- `AbletonMCPServer_Extension/`: TypeScript Extension for warp operations and device insertion.
- `contracts.py`: canonical ports, command sets, error codes, and routing constants.

Detailed boundaries and state ownership: `.agent-context/architecture.md`.

## Critical paths

| Path | Responsibility |
|---|---|
| `ableton_mcp_server/server.py` | Registers the 65 public MCP tools. |
| `ableton_mcp_server/models.py` | Pydantic request models and batch validation. |
| `ableton_mcp_server/client.py` | Routes commands to TCP or WebSocket clients. |
| `AbletonMCPServer_RemoteScript/__init__.py` | Queues socket requests and touches Python LOM only on Live's UI thread. |
| `AbletonMCPServer_Extension/src/index.ts` | WebSocket JSON-RPC handlers for three Extension operations. |
| `contracts.py` | Source of truth mirrored into `_contracts.py`. |
| `docs/KNOWN_BUGS.md` | Canonical Live/LOM failure modes and mitigations. |

## Setup and verification

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
```

Extension:

```powershell
cd AbletonMCPServer_Extension
npm install
npm run build
```

Real Live connectivity is proven by `\.venv-win\Scripts\ableton-mcp.exe doctor --json`, not by local tool discovery. Run the guarded acceptance command only against a disposable Set with the exact project-name confirmation and an empty target MIDI clip slot.

## Coupled-change rules

- Edit root `contracts.py`, then run `python scripts/vendor_contracts.py`; never hand-edit `_contracts.py`.
- A public tool change normally requires synchronized changes in `server.py`, `models.py`, tests, `docs/TOOL_REFERENCE.md`, and the asserted tool count.
- A routed command change must keep contracts, Python client, Remote Script or Extension handler, models, and tests aligned.
- Keep `pyproject.toml`, root `manifest.json`, and `AbletonMCPServer_Extension/package.json` versions aligned for a release.
- Expected bridge errors must remain structured MCP errors; do not turn them into framework crashes.
- Never call Live Python LOM from the socket thread; defer through the request queue and `update_display()`.

## Safety

- Preserve dirty worktrees and unrelated agent/user changes.
- Do not push, publish, tag, release, force-reset, or rewrite history without explicit authorization.
- Do not retry mutations after ambiguous network failure.
- `run_batch` is grouped undo, not rollback: a successful prefix persists and `rolled_back` is `false`.
- Path IDs are session-local index locators; re-list after structural edits.
- Keep bridges local-only. See the unresolved WebSocket bind verification in `.agent-context/risks.md` before changing network behavior.

## Persistent context

Context was produced with `repo-context-loader` format v2. Generated evidence is ignored; curated files are reviewed and finalized. If `check` reports stale, inspect only reported changes and affected consumers rather than remapping the repository.

