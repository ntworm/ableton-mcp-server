# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-07-10

### Added
- Hybrid Dual-Bridge Architecture: support for routing transport/MIDI commands to Remote Script (TCP `9888`) and warping/device commands to Extension Host (WebSocket `9889`).
- Node.js/TypeScript Extension Host bridge component (`AbletonMCPServer_Extension`).
- Pydantic models and FastMCP tool interfaces for 9 new tools:
  - `get_composition_structure` (full track layout metadata).
  - `diagnose_midi_clip` (note overlap detection, C-major scale matching, and grid timing drift analysis).
  - `create_midi_track` (guarded with 96-track safety limit).
  - `rename_track` (renaming tracks/clips).
  - `get_warp_state` & `set_warp_state` (reading and writing audio clip warping properties via WebSocket).
  - `load_device_to_track` (loading native instruments/devices via WebSocket).
  - `scaffold_extension` & `build_extension` (scaffolding and compiling native Ableton Extensions).
- `ExtensionUnavailableError` and `TrackLimitError` error classes.
- Unit tests for WSClient, composition queries, track mutations, and MIDI diagnostics.

## [0.2.2] - 2026-07-10

### Changed

- Cue toggles and cue renames are observed across up to ten Live UI ticks before a result is reported.
- Playhead and state writes now tolerate up to ten transitional UI ticks.
- JSONL deadlines use a shared 20-second base and scale with bulk/batch work instead of using conflicting client/server constants.
- Bulk cue creation holds the working cursor and restores the original cursor once after all items.

### Fixed

- Empty list results retain structured `[]` data and an explicit text fallback across FastMCP clients.
- Expected bridge errors become typed MCP error results instead of escaping as framework exceptions and tracebacks.
- Idle persistent JSONL connections stay open; the socket timeout now polls for shutdown rather than closing a healthy client.
- Windows socket failures become typed `LIVE_UNAVAILABLE` errors and keep mutation retry decisions explicit.
- Delayed cue toggles no longer race cursor restoration and leave default-name markers at the restored position.
- Cue names are verified and idempotently retried when Live drops a name write.
- Cue operations no longer write `Song.start_time`; the official LOM defines it as the playback start position rather than the cue cursor.
- Live 12 Beta Arrangement-grid snapping is detected transactionally. An unintended off-grid cue creation or deletion is reversed and returned as `CUE_SNAPPED_TO_GRID` instead of leaking or corrupting a locator.

## [0.2.1] - 2026-07-09

### Added

- Native Windows bootstrap, packaged Remote Script installer, installation status, and bridge doctor commands.
- A guarded real-Live acceptance runner that refuses to mutate unless the disposable Set name, MIDI track, and empty clip slot all match.
- `get_bridge_status`, bringing the public FastMCP surface to 37 tools.
- Cross-platform Ableton log discovery with an explicit `ABLETON_MCP_LOG_PATH` override.

### Changed

- WSL uses the native Windows MCP executable to reach Live's loopback listener; the listener remains bound to `127.0.0.1:9888`.
- Live mutations now advance and verify across `update_display` ticks without sleeping on Live's UI thread.
- Batches execute deferred child operations inside one outer undo step, abort at the first error, and report the exact successful prefix.

### Fixed

- Embedded Python note insertion now constructs `Live.Clip.MidiNoteSpecification` objects instead of passing Max-for-Live-style dictionaries.
- Transport and loop results are verified only after Live has had a UI tick to apply each write.
- Cue creation/deletion moves and restores both `current_song_time` and `start_time`, preventing misplaced toggles and false failures.
- Verbose diagnostics use a consistent `[MCP-Server]` prefix and emit a startup endpoint record.
- Wheel builds include the canonical contracts module and installable Remote Script assets.

### Security

- The bridge remains loopback-only. WSL compatibility does not expose port 9888 on the LAN.

## [0.2.0] - 2026-07-09

### Added

- Greenfield `ableton_mcp_server` package and MIDI Remote Script.
- Thirty-six documented FastMCP tools.
- TCP JSONL protocol on `127.0.0.1:9888` with typed error envelopes.
- Dependency-free canonical contracts with deterministic vendoring.
- Session path-ids, typed bridge errors, Pydantic request models, snapshots, and diffs.
- Verified transport setters, idempotent cue-point handling, clip creation/firing, MIDI note insertion, and grouped batch execution.
- Stateful mock Remote Script, socket integration check, and test suite runnable without Live.
- Opt-in `[PROBE]` logging through `ABLETON_MCP_SERVER_VERBOSE=1`.

### Changed

- Debug-relevant mutations are explicitly allowed instead of being blocked by command-name prefixes.
- Mutations are not automatically retried after ambiguous connection failures.
- Batch errors preserve the already-applied prefix in a single undo step rather than claiming automatic rollback.

### Removed

- `set_song_length`, because `Song.song_length` is read-only in the Live Object Model.
- Prefix-based mutation blocking and duplicated protocol constants.

### Fixed

- Transport verification now reads an explicit attribute after every write; it never compares lambda identity.
- Cue deletion uses `set_or_delete_cue` after a verified playhead move.
- Cue beat-time objects are cast to `float` before comparison.
- `create_clip`, `fire_clip`, and `add_notes_to_clip` are no longer incorrectly blocked.
