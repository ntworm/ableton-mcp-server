# AbletonMCPServer MIDI Remote Script

This directory is the Live-side execution engine for `ableton-mcp-server`. It listens only on `127.0.0.1:9888`, queues JSONL requests, and executes every Live Object Model call from `update_display` on Live's main thread.

## Install

1. From the repository root, run `python scripts/vendor_contracts.py`.
2. Copy this entire directory into Live's MIDI Remote Scripts folder.
3. Delete any copied `__pycache__` directory.
4. Restart Live.
5. Select `AbletonMCPServer` as a Control Surface.

Do not edit `_contracts.py`; it is generated from root `contracts.py`.

## Diagnostics

Launch Live with `ABLETON_MCP_SERVER_VERBOSE=1` to enable `[PROBE]` logging for verified transport writes and cue-point creation. Search the active Live `Preferences\Log.txt` under `%APPDATA%\Ableton\Live *\`.

## Safety

- No LOM access occurs from socket threads.
- The listener is loopback-only.
- Unknown commands return `UNKNOWN_COMMAND`.
- Explicitly blocked creative mutations return `READ_ONLY_VIOLATION`.
- A missing undo API causes mutations to fail before execution.
- Batch failures do not automatically roll back their successful prefix.
