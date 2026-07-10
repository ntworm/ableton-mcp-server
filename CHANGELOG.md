# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
