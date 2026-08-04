# AGENTS.md — ableton-mcp-server

## Purpose

`ableton-mcp-server` v0.5.2 exposes 65 MCP tools for inspecting and safely mutating an Ableton Live Set; the current line adds colour writes, clip-target diagnostics and the five refusing hierarchy tools, so the asserted count on `main` is 73. A Python FastMCP process coordinates a Live MIDI Remote Script over TCP and an Ableton Extension over WebSocket. The repository is MIT-licensed and targets Windows-hosted Ableton Live; WSL clients must launch the Windows-native executable.

## Read order

1. This file for repository-wide rules.
2. Only the relevant `.agent-context/{architecture,conventions,dependencies,hot-files,risks}.md` file.
3. Current source, tests, Git evidence, and canonical docs for task-specific claims.

Canonical project docs are `README.md`, `docs/ARCHITECTURE.md`, `docs/TOOL_REFERENCE.md`, and `docs/KNOWN_BUGS.md`. Files under `prompts/` are proposals/handoffs and can be partially superseded; verify them against current code before acting.

## Recent change context (read this if working on transport, capability matrix, or resolved envelope)

The v0.5.2 release landed four coordinated changes driven by the comparison with the public `8309/ableton-agent-hub` project. Any agent picking up follow-up work should read the planning and handoff documents first to avoid re-litigating settled decisions:

- `docs/ABLETON_AGENT_HUB_REFACTORING.md` — the original direction-setting plan (compare/contrast, scope decisions, items explicitly NOT to copy from the upstream project).
- `docs/superpowers/specs/2026-08-01-r1-resolved-field.md` — the canonical shape of the `resolved` sub-object returned by mutation tools; deviating from this spec requires a new spec and a coordinated test update.
- `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md` — the design behind the new `get_bridge_status.tools` / `capability_counts` / `capability_source` fields; the spec contains a known non-blocking drift note about `live_required_tools` (57, not 59) that should be reconciled.
- `tasks/v0-5-1-refactor-r1r3/HANDOFF.md` — the per-wave status, audit findings, and the items that are explicitly **out of scope** of the v0.5.2 branch (R2 `dry_run`, R6 `-DryRun` on the installer, E1 `find_device`/`find_clip`, E4–E6). Do not silently re-introduce them without owner authorization.

The 4 items below are not yet implemented and the gating work for each is described in the HANDOFF:

- **`R2` (`dry_run` on mutation tools).** Limited to `set_tempo` and `create_clip` if attempted; the broader set breaks invariants because `load_device_to_track` runs over the WebSocket to a live Extension, `create_audio_track` requires post-state readback, and `live_fade` is concurrent and time-dependent. Spec first.
- **`R6` (an install dry-run).** Decide whether the dry-run belongs in `ableton-mcp install-script --dry-run` (Python) or `setup_windows.ps1 -DryRun` (PowerShell) before patching either.
- **`E1` (`find_device` / `find_clip` tools).** Blocked on the owner's decision about path-id handling (KNOWN_BUGS §"Category G" — `STALE_REFERENCE`). New tools must return `(track_index, device_index)` tuples or names, never `path-id` locators.
- **`E2`/`E3` (UDP transport, Max for Live surface adapter).** Explicitly rejected in `docs/ABLETON_AGENT_HUB_REFACTORING.md` §4. Do not reopen without a new comparison.

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
| `ableton_mcp_server/server.py` | Registers the 73 public MCP tools. |
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
- `resolved` is the canonical identity sub-object on success results for `set_parameter_value`, `create_clip`, `set_tempo`, and `load_device_to_track`; future tools adopting resolved identity must use the same sub-object convention and omit unavailable name keys.
- Never call Live Python LOM from the socket thread; defer through the request queue and `update_display()`.
- Operations with no public API (track move/reorder/re-parent/ungroup/merge) belong in `contracts.UNSUPPORTED_CAPABILITIES` + `CAPABILITY_EVIDENCE`, stay out of `ALLOWED_MUTATIONS`, validate before refusing, and answer `CAPABILITY_UNAVAILABLE` with `details`. Never let one open an undo step, and never emulate a missing operation with duplicate + delete.

## Safety

- Preserve dirty worktrees and unrelated agent/user changes.
- Do not push, publish, tag, release, force-reset, or rewrite history without explicit authorization.
- Do not retry mutations after ambiguous network failure.
- `run_batch` is grouped undo, not rollback: a successful prefix persists and `rolled_back` is `false`.
- Path IDs are session-local index locators; re-list after structural edits.
- Keep bridges local-only. See the unresolved WebSocket bind verification in `.agent-context/risks.md` before changing network behavior.

## Persistent context

Context was produced with `repo-context-loader` format v2. Generated evidence is ignored; curated files are reviewed and finalized. If `check` reports stale, inspect only reported changes and affected consumers rather than remapping the repository.
