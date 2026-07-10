# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
