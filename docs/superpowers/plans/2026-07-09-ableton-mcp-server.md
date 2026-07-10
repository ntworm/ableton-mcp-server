# Ableton MCP Server v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user requires one final atomic commit, so do not commit between tasks.

**Goal:** Build and verify a greenfield FastMCP server plus Ableton MIDI Remote Script with 35+ tools over TCP JSONL.

**Architecture:** FastMCP tools validate parameters and call a typed TCP client. The Live-side Remote Script owns the loopback listener and queues every LOM operation onto Live's UI thread. A dependency-free contract file is vendored into the Remote Script, and all Live-specific behavior remains behind named handlers testable with fakes.

**Tech Stack:** Python 3.10+, FastMCP 3.x, Pydantic 2.x, pytest, pytest-asyncio, Ruff, mypy.

**Lint configuration:** Ruff target `py310`, line length 100; mypy Python 3.10 strict mode. `Live` and `ableton` imports are excluded from server-package checking and stubbed in Remote Script tests.

---

## File Structure

- `contracts.py`: dependency-free protocol constants, command sets, and retry values.
- `ableton_mcp_server/errors.py`: typed server-side bridge errors.
- `ableton_mcp_server/protocol.py`: JSONL request encoding and response decoding.
- `ableton_mcp_server/models.py`: Pydantic request models for every MCP tool.
- `ableton_mcp_server/ids.py`: path grammar, formatting, and parsed representation.
- `ableton_mcp_server/client.py`: reconnecting TCP client.
- `ableton_mcp_server/snapshot.py`: snapshot normalization and validation.
- `ableton_mcp_server/diff.py`: deterministic recursive diffing.
- `ableton_mcp_server/write_guard.py`: contract re-exports and block enforcement.
- `ableton_mcp_server/server.py`: 35+ documented FastMCP tools.
- `AbletonMCPServer_RemoteScript/__init__.py`: socket, UI queue, reads, writes, undo, debug probes.
- `AbletonMCPServer_RemoteScript/_contracts.py`: generated contract copy.
- `scripts/vendor_contracts.py`: deterministic vendor generator.
- `scripts/mock_remote_script.py`: stateful local JSONL fake.
- `scripts/integration_check.py`: smoke test against mock or Live.
- `tests/`: unit, MCP registry, Remote Script, and socket integration tests.
- `docs/`: architecture, tools, known bugs, and manual verification.

### Task 1: Bootstrap and Boundary Contracts

**Files:** create `.gitignore`, `pyproject.toml`, `manifest.json`, `LICENSE`, `ableton_mcp_server/__init__.py`, `contracts.py`, `tests/test_contracts.py`, `tests/test_protocol.py`, `tests/test_errors.py`, `tests/test_ids.py`.

- [ ] Write tests asserting the exact JSONL envelopes, hint preservation, explicit allowed/blocked sets, absence of `set_song_length`, and valid/invalid path forms.
- [ ] Run `python -m pytest tests/test_contracts.py tests/test_protocol.py tests/test_errors.py tests/test_ids.py -q`; expect import failures because production modules do not exist.
- [ ] Implement dependency-free contracts, typed errors, protocol codecs, and path parsing.
- [ ] Re-run the command; expect all tests to pass.

Core API fixed by these tests:

```python
encode_request("set_tempo", {"tempo": 128.0})
# b'{"type": "set_tempo", "params": {"tempo": 128.0}}\n'

parse_path("track:2/device:1/param:3")
# ParsedPath(kind="parameter", track_index=2, device_index=1, parameter_index=3)
```

### Task 2: Models, Client, Snapshots, and Diff

**Files:** create `ableton_mcp_server/models.py`, `client.py`, `snapshot.py`, `diff.py`, `write_guard.py`, `tests/test_models.py`, `tests/test_client.py`, `tests/test_snapshot.py`, `tests/test_diff.py`.

- [ ] Write failing tests for model bounds, client error mapping/reconnect, snapshot normalization/schema validation, recursive diffs, and write-guard behavior.
- [ ] Run those five test files; expect failures for missing implementations.
- [ ] Implement minimal behavior and retain the exact `{type, params}`/response envelopes.
- [ ] Re-run the focused tests; expect all to pass.

The client must raise a typed error without losing the remote hint:

```python
with pytest.raises(StaleReferenceError, match="track:9") as exc:
    client.call("get_track_state", {"track_index": 9})
assert exc.value.hint == "Re-list tracks and use a fresh path-id."
```

### Task 3: Remote Script Core and Read Handlers

**Files:** create `AbletonMCPServer_RemoteScript/__init__.py`, `AbletonMCPServer_RemoteScript/README.md`, `tests/remote_fakes.py`, `tests/test_remote_reads.py`, `tests/test_remote_threading.py`.

- [ ] Write failing tests that import the script through fake `Live` modules and exercise all read handlers.
- [ ] Assert the socket handler only enqueues and `update_display` performs dispatch.
- [ ] Implement named free-function handlers, safe LOM access, snapshot capture, dispatcher lookup, queue timeouts, and error envelopes.
- [ ] Run the focused tests and AST parse command; expect pass and exit code 0.

The UI-thread boundary is observable: a request remains pending until `update_display()` drains the queue; no handler is called by the socket thread.

### Task 4: Transport and Cue-Point Mutations

**Files:** modify Remote Script; create `tests/test_transport_retry.py`, `tests/test_cue_points.py`, `tests/test_bulk_create.py`.

- [ ] Write a stuck-property fake and a failing test that expects exactly three writes and `PLAYHEAD_NOT_MOVED`.
- [ ] Write tests for quantization restoration on success and failure.
- [ ] Write tests proving create renames an existing cue, create toggles only after verified movement, delete moves then toggles, times are cast to float, and bulk delegates to the single-item handler.
- [ ] Implement `_set_transport_value(song, attribute, value, ...)` with `setattr` then `float(getattr(...))`; do not use callable identity.
- [ ] Implement cue handlers and debug probes gated by `ABLETON_MCP_SERVER_VERBOSE=1`.
- [ ] Run the focused tests; expect pass.

### Task 5: Clip Mutations and Batch Undo

**Files:** modify Remote Script; create `tests/test_clip_mutations.py`, `tests/test_transaction.py`.

- [ ] Write failing tests for clip creation, firing, MIDI-note replacement, standalone one-undo behavior, batch single-undo behavior, first-error abort, successful-prefix persistence, and `end_undo_step` in `finally`.
- [ ] Implement `create_clip`, `fire_clip`, and `add_notes_to_clip` as allowed debug mutations.
- [ ] Implement centralized undo ownership and a non-nesting `run_batch` path.
- [ ] Run focused tests; expect pass.

Batch result contract:

```json
{
  "results": [{"index": 0, "status": "ok", "result": {"tempo": 128.0}}],
  "completed": 1,
  "aborted_at": 1,
  "rolled_back": false
}
```

### Task 6: Vendoring and Mock Integration

**Files:** create `scripts/vendor_contracts.py`, generated `_contracts.py`, `scripts/mock_remote_script.py`, `scripts/integration_check.py`, `tests/test_vendoring.py`, `tests/test_mock_integration.py`.

- [ ] Write failing tests for deterministic header/content equality and stateful JSONL calls over a real loopback socket.
- [ ] Implement the vendor script and mock server.
- [ ] Run the vendor script twice and assert no second diff.
- [ ] Run the focused tests; expect pass.

### Task 7: FastMCP Server and 35+ Tools

**Files:** create `ableton_mcp_server/server.py`, `tests/test_server_tools.py`, `tests/test_tool_registry.py`.

- [ ] Write failing forwarding tests for every tool and schema/model coverage tests for every registry entry.
- [ ] Write a FastMCP compatibility test asserting both `len(mcp.list_tools()) >= 35` and `len(await real_tool_listing) == len(mcp.list_tools())`.
- [ ] Implement 22 reads and 14 mutations with full docstrings, Pydantic validation, and structured client calls.
- [ ] Run server and registry tests; expect pass.
- [ ] Run `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"`; expect at least 35.

### Task 8: Documentation and Release Metadata

**Files:** create `README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/TOOL_REFERENCE.md`, `docs/KNOWN_BUGS.md`; finalize `manifest.json` and `pyproject.toml` at `0.2.0`.

- [ ] Document every tool's signature, parameters, response, example, edge cases, and side effects.
- [ ] Document Categories A-I, including successful-prefix batch persistence and manual undo.
- [ ] Document loopback-only security, path-id limits, UI-thread queue, vendoring, verbose probes, deployment, and manual Live checklist.
- [ ] Search for sibling-project paths and forbidden `set_song_length`; only the design's historical explanation may mention the reference backup.

### Task 9: Full Verification and Corrections

**Files:** modify only files implicated by failures; add regression tests before every behavioral correction.

- [ ] Run `python -m pytest tests/ -q --tb=line`.
- [ ] Measure line execution with a stdlib trace-based coverage script because new coverage dependencies are forbidden; require at least 85% for the server package and Remote Script testable functions.
- [ ] Run Remote Script AST parse, vendoring verification, Ruff, strict mypy, tool count, and integration smoke test.
- [ ] If a behavior fails, add or confirm a failing regression test before changing production code.

### Task 10: Requirement Audit and Atomic Commit

**Files:** all intended project files.

- [ ] Re-read the approved design and acceptance checklist; map each requirement to a test or documented manual limitation.
- [ ] Confirm no `.ablx`, caches, venv, unrelated reference code, or absolute sibling-project coupling is tracked.
- [ ] Run the complete final verification suite again and capture fresh output.
- [ ] Commit once with `refactor(ableton-mcp-server): v0.2.0 full rewrite`.
- [ ] Capture SHA, pytest, Ruff, mypy, tool count, clean status, stat, contracts diff command, and corrected prompt inconsistencies.

## Self-Review

Spec coverage: every approved category, required read, protocol constraint, verification command, and final report item maps to Tasks 1-10. The design intentionally exposes 36 tools because hiding the bulk cue helper would reduce utility solely to force an exact count.

Placeholder scan: no implementation placeholders or deferred behavioral choices remain. Live-only acceptance is explicitly a manual boundary, not a deferred code requirement.

Type consistency: request names use snake_case throughout; path fields and envelope fields match between design, tasks, and tests.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: every behavioral task names its failing assertions and matching implementation API.
- PASS Per-task command executability: focused pytest commands only reference test files created by that task; final commands run after all modules exist.
- PASS File usage audit: every generated file is imported, served through FastMCP, copied by vendoring, loaded by tests, or referenced by deployment docs.
- PASS Spec lifecycle audit: connect, disconnect, timeout, retry, abort, and undo outcomes are assigned explicit state behavior and tests.
- PASS Time source audit: snapshots use Unix epoch milliseconds; retry sleeps use duration seconds and never compare timestamps across clocks.
- PASS State scope audit: MCP client is process-global; socket queues are per Control Surface; response queues are per request; mock state is per server instance; path cache stores JSON only.
- PASS Environment audit: all network endpoints are desktop-only loopback `127.0.0.1`; no LAN/mobile path exists.
- N/A Browser event audit: the project has no browser UI or browser events.
- PASS Lint/import audit: server modules target Python 3.10 strict typing; Live-only imports are isolated to the Remote Script and stubbed in tests.
- PASS Non-obvious API audit: FastMCP async listing is locally inspected and covered by an awaitable compatibility test; Live-only APIs are called through reference-backed patterns and marked for manual verification.
