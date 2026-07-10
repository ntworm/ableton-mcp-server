# AbletonMCPServer MIDI Remote Script

This directory is the Live-side execution engine for `ableton-mcp-server`. It listens only on `127.0.0.1:9888`, queues JSONL requests, and executes every Live Object Model call from `update_display` on Live's main thread.

## Install

1. From a native Windows environment, run `ableton-mcp install-script`.
2. Restart Live.
3. Select `AbletonMCPServer` as a Control Surface.

For repository development, `python scripts/vendor_contracts.py` refreshes `_contracts.py` before a manual copy.

Do not edit `_contracts.py`; it is generated from root `contracts.py`.

## Diagnostics

Launch Live with `ABLETON_MCP_SERVER_VERBOSE=1` to enable `[MCP-Server]` records for startup, verified writes, and cue-point operations. Run `ableton-mcp doctor --json` for an end-to-end bridge probe and `ableton-mcp install-status --json` to compare the installed script with the packaged copy.

## Safety

- No LOM access occurs from socket threads.
- Deferred mutations advance one step per `update_display` tick and never sleep on Live's UI thread.
- Persistent JSONL clients are not disconnected for idleness, and command deadlines scale with serialized bulk/batch work.
- Cue toggles execute once, are observed across UI ticks, and are named before the working cursor is restored.
- The listener is loopback-only.
- Unknown commands return `UNKNOWN_COMMAND`.
- Explicitly blocked creative mutations return `READ_ONLY_VIOLATION`.
- A missing undo API causes mutations to fail before execution.
- Batch failures do not automatically roll back their successful prefix.
