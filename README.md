# Ableton MCP Server

`ableton-mcp-server` gives MCP-compatible agents debug-grade access to a running Ableton Live Set. It consists of a Python stdio MCP server and a MIDI Remote Script that communicate over newline-delimited JSON on TCP `127.0.0.1:9888`.

The server exposes 36 tools: 22 reads plus 14 constrained mutations for transport, loop state, cue points, Session clips, MIDI notes, and one-undo batch execution. Creative/destructive operations such as deleting tracks or loading Browser items remain blocked.

## Architecture

```text
MCP client -> FastMCP stdio server -> TCP JSONL -> Remote Script socket thread
                                               -> main-thread queue -> Live Object Model
```

Only `AbletonMCPServer_RemoteScript/` imports Live's Python API. The MCP package is testable without Ableton. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the protocol, thread-safety rules, path-ids, undo semantics, and error model.

## Requirements

- Windows 11
- Ableton Live 12.4.x or a compatible Live 12 build
- Python 3.10 or newer for the MCP server
- An MCP-compatible client

## Install the MCP server

```powershell
cd C:\Users\Usuario\repos\ableton-mcp-server
python -m pip install -e ".[dev]"
python -m ableton_mcp_server.server
```

The server uses stdio for MCP and connects to `127.0.0.1:9888`. Override only the port when necessary:

```powershell
$env:ABLETON_MCP_SERVER_PORT = "9888"
python -m ableton_mcp_server.server
```

The host is deliberately fixed to loopback.

## Install the Remote Script

1. Run `python scripts/vendor_contracts.py`.
2. Copy the whole `AbletonMCPServer_RemoteScript` directory into Live's MIDI Remote Scripts directory.
3. Remove any copied `__pycache__` directory.
4. Restart Live.
5. Select `AbletonMCPServer` under `Preferences -> Link, Tempo & MIDI -> Control Surfaces`.

For verbose cue-point diagnostics, launch Live with `ABLETON_MCP_SERVER_VERBOSE=1` and search Live's `Log.txt` for `[PROBE]`.

## Verify locally

```powershell
python -m pytest tests -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript
python -m mypy --strict ableton_mcp_server
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
```

Start the mock bridge in a second terminal for a socket smoke test:

```powershell
python scripts\mock_remote_script.py --port 9889
python scripts\integration_check.py --port 9889
```

## Safety and limitations

- Live Object Model calls execute only from Live's UI thread.
- Mutations are not automatically retried after network failure because the original mutation may already have executed.
- `run_batch` aborts at the first error but does not roll back earlier successful commands. One Ctrl+Z reverts the grouped successful prefix.
- `song_length` is read-only. Grow the Arrangement by placing content on its timeline.
- Path-ids are session-local index paths. Re-list after structural changes.
- The automated suite cannot prove behavior inside the real Live process. Follow the manual checklist in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#manual-live-verification).

## Documentation

- [Tool reference](docs/TOOL_REFERENCE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Known Live API quirks](docs/KNOWN_BUGS.md)
- [Changelog](CHANGELOG.md)

## License

MIT
