# Release Notes

## v0.8.0

v0.8.0 delivers the modular MIDI Remote Script architecture, chain-order-safe device loading, and strict acceptance preflight verification. This stable release is bound to a guarded acceptance report with `release_ready=true`.

### Highlights

- **Remote Script Modularization**: Split the monolithic 4,555-line `__init__.py` into 17 clean domain modules (`common`, `lom`, `reads`, `devices`, `instruments`, `transport`, `cues`, `tracks`, `arrangement`, `clips`, `automation`, `composition`, `lifecycle`, `preconditions`, `handlers`, `dispatch`, `socket_server`).
- **Chain-Order Device Insertion**: `load_device_to_track` places devices according to Live's signal flow (MIDI effects -> Instrument -> Audio effects) via browser category discovery and target index resolution. Second instrument insertions are cleanly rejected with `BAD_INPUT`.
- **Preflight Clean-Set Proof**: Guarded acceptance verifies `can_undo is False` before mutating the disposable Set, preventing dirty state leaks under Live 12.4.25b1 where `Song.is_dirty` is unavailable.
- **MCP Bundle Support**: Adds `scripts/build_mcpb.py` producing self-contained `.mcpb` packages for the 97-tool surface with stdio smoke validation.

### Artifacts

- `ableton_mcp_server-0.8.0-py3-none-any.whl` (sha256 `30a39e70fbce07667774834656d5fc3aa64df93c818abd3a11852e3120fb3323`)
- `AbletonMCPServer_RemoteScript-0.8.0.zip` (sha256 `dde95a3e526025b90f7314e839ced3d0ecbf2a672cf6e5705748039a6cfdab1e`)
- `AbletonMCPServer-Extension-0.8.0.ablx` (sha256 `1e1b8effb98aa84dd4d78327b45477a85058ceab1097082c09c6ffbe5ccb143c`)
- `ableton-mcp-server-0.8.0.mcpb` (sha256 `b6ead65a681399739e634c15d5b9be11ab32289a9b2bd9e91ddbd1acb827ed39`)
