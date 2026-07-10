# Ableton MCP Server v0.2.0 Design

## Goal

Build a standalone Python MCP server and Ableton MIDI Remote Script that expose debug-grade reads and a constrained set of reversible mutations over newline-delimited JSON on TCP `127.0.0.1:9888`.

The project is greenfield. The prior implementation was used only as a behavioral reference, not as a source of truth or runtime dependency.

## Constraints

- The server runs as a stdio FastMCP process and never imports Ableton's `Live` module.
- Only `AbletonMCPServer_RemoteScript\` imports the Live Object Model.
- The socket thread performs no LOM access. It queues requests for `update_display`, which runs on Live's main thread.
- Requests are `{"type": "command", "params": {...}}` followed by `\n`.
- Responses are either `{"status": "ok", "result": ...}` or `{"status": "error", "code": "...", "message": "...", "hint": "..."}`.
- No dependencies beyond `mcp`, `fastmcp`, `pydantic`, `pytest`, `pytest-asyncio`, `ruff`, and `mypy`.
- No `.ablx`, no push, no coupling to sibling projects, and one final atomic commit.
- The real Ableton runtime remains a manual acceptance boundary.

## Architecture

The MCP-facing process contains transport-independent validation and result shaping. `Client` is the TCP adapter. The Live-side script owns the socket listener, the main-thread request queue, command dispatch, LOM reads, and mutations.

```text
MCP client
  -> FastMCP tool + Pydantic validation
  -> Client.call(command, params)
  -> TCP 127.0.0.1:9888 JSONL
  -> socket thread / request queue
  -> update_display on Live UI thread
  -> named command handler
  -> structured JSONL response
```

`contracts.py` is dependency-free and is vendored to `AbletonMCPServer_RemoteScript\_contracts.py`. The generated copy is never edited directly. Error codes and command classifications therefore cannot drift between the processes.

## Tool Surface

The server exposes 36 tools initially, satisfying the 35+ acceptance threshold.

Reads (22):

1. `get_session_info`
2. `get_track_list`
3. `get_track_state`
4. `get_locators`
5. `take_snapshot`
6. `get_ableton_logs`
7. `get_control_surfaces`
8. `get_scenes`
9. `get_scene_state`
10. `get_project_metadata`
11. `get_loop_settings`
12. `get_selected_context`
13. `get_clip_summary`
14. `get_clip_notes`
15. `get_device_list`
16. `get_parameter_value`
17. `get_routing`
18. `get_browser_categories`
19. `diff_snapshots_tool`
20. `get_song_length`
21. `live_find_track`
22. `list_device_params`

Mutations (13):

1. `create_cue_point`
2. `bulk_create_cue_points`
3. `delete_cue_point`
4. `set_current_song_time`
5. `set_tempo`
6. `start_playback`
7. `stop_playback`
8. `set_loop`
9. `set_loop_start`
10. `set_loop_length`
11. `run_batch`
12. `add_notes_to_clip`
13. `fire_clip`
14. `create_clip`

The mutation list contains 14 names because `bulk_create_cue_points` is a convenience aggregation over `create_cue_point`; the MCP registry will expose all 36 useful tools rather than hiding it. The acceptance threshold remains at least 35.

Blocked commands are `create_midi_track`, `delete_track`, `set_track_name`, `duplicate_session_clip_to_arrangement`, `switch_to_arrangement_view`, `load_instrument_or_effect`, and `load_browser_item`. `create_clip`, `fire_clip`, and `add_notes_to_clip` are explicitly allowed.

## Path IDs

Accepted forms are:

- `track:N`
- `track:N/device:D`
- `track:N/device:D/param:P`
- `track:N/clipslot:S`
- `track:N/clipslot:S/clip`
- `track:N/clip:C`

Every path-accepting call parses and resolves the path against current Live state. A missing index produces `STALE_REFERENCE`; a mismatched object produces `WRONG_TYPE`. Paths are session-local locators, not immutable object identities. If an insertion shifts an index, callers must re-list and use the new path. The short cache stores only recently returned JSON snapshots; it never stores or serializes Live objects.

## Error Model

All boundary failures use stable codes: `UNKNOWN_COMMAND`, `INVALID_PARAMS`, `READ_ONLY_VIOLATION`, `TIMEOUT`, `LIVE_UNAVAILABLE`, `INTERNAL_ERROR`, `PLAYHEAD_NOT_MOVED`, `STALE_REFERENCE`, `WRONG_TYPE`, and `BAD_INPUT`.

The Remote Script converts local exceptions into envelopes. `Client` converts error envelopes into typed `BridgeError` subclasses while retaining `code`, `message`, and optional `hint`. FastMCP tools do not silently replace these errors with unrelated values.

## Live API Quirks A-I

- A: transport setters use an explicit attribute name, perform set/read/compare, sleep between attempts, restore quantization in `finally`, and raise `PlayheadNotMovedError` on exhaustion.
- B: cue creation/deletion checks existing cues before invoking `set_or_delete_cue`.
- C: `song_length` is read-only; there is no setter tool.
- D: cue deletion uses move-and-toggle, never a nonexistent `delete_cue_point` method.
- E: cue times are converted with `float` and compared with a `0.01` beat tolerance.
- F: command classifications and protocol constants come from vendored `contracts.py`.
- G: path IDs are parsed and resolved on every call; missing targets raise `STALE_REFERENCE`.
- H: `run_batch` groups prior successful mutations into one undo step and aborts on the first error. There is no automatic rollback. One Ctrl+Z reverts the grouped successful prefix.
- I: allowed and blocked mutations are explicit sets. There is no prefix-based mutation block.

## Undo Semantics

The dispatcher wraps each standalone allowed mutation in one `begin_undo_step`/`end_undo_step` pair. `run_batch` opens one outer undo step and invokes handlers without nested undo steps. Bulk cue creation is one command and therefore one undo step.

If a batch command fails, later commands are not run. Earlier mutations persist until the user invokes Undo. The result reports the successful prefix and the failing index. Manual reverse-op replay is intentionally not implemented because it cannot restore every LOM mutation safely.

## Testing

Pure server modules are tested directly. The Remote Script is loaded in tests with stub `Live` and `ableton.v2.control_surface` modules so named handler functions can be exercised without Ableton. Tests cover JSONL framing, typed errors, path parsing, allow/block decisions, transport retries, cue toggles, batch undo grouping, bulk aggregation, snapshots, diffs, MCP registration, and a real loopback socket against the mock server.

AST parsing, Ruff, strict mypy, vendoring equality, and tool count are release gates. Live-only behavior is covered by a documented manual checklist rather than claimed as locally verified.

## FastMCP Compatibility

FastMCP 3.x exposes `list_tools()` as an async method, while the requested acceptance command calls `len(mcp.list_tools())`. A small `CountableFastMCP` compatibility subclass returns an awaitable proxy that also implements `__len__`. Awaited behavior delegates to FastMCP unchanged; synchronous `len(...)` reports the registered count and is cross-checked against the real async result in tests.
