# Ableton MCP Server

`ableton-mcp-server` gives MCP-compatible agents complete access to a running
Ableton Live Set. A stdio FastMCP server communicates with a MIDI Remote Script
over newline-delimited JSON on TCP `127.0.0.1:9888`, and with an Extension Host
bridge over WebSockets on `127.0.0.1:9889`.

Version 0.3.0 exposes 46 tools: reads/diagnostics (including composition diagnostics
and scale mapping), and creative mutations for transport, loop state, cue points,
Session clips, MIDI notes, track renaming, guarded MIDI track creation, audio warping control,
plug-in device loading, and extension scaffolding/building.

## Architecture

```text
               /-> TCP JSONL (9888) ------> Remote Script (Python LOM)
MCP client -> FastMCP Server (Python)
               \-> WebSockets (9889) ------> Extension Host (Node.js LOM)
```

Socket threads never touch the Live Object Model. Python mutations execute and verify
their read-back over successive `update_display` ticks, while Node.js extension actions
resolve concurrently via async/await. See [Architecture](docs/ARCHITECTURE.md).

## Windows installation

From PowerShell in the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

This creates a distinct native environment at `.venv-win`, installs the package,
copies the bundled Remote Script into the User Library, removes stale bytecode,
and verifies file hashes.

Then restart Live, select `AbletonMCPServer` under
`Preferences -> Link, Tempo & MIDI -> Control Surfaces`, and run:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
.\.venv-win\Scripts\ableton-mcp.exe doctor --json
```

`doctor` calls `get_session_info` through the real JSONL bridge. Tool discovery
alone does not prove that Live is reachable.

## WSL clients

Live runs in Windows, so the recommended WSL topology is to launch the Windows
MCP executable through WSL interoperability:

```text
/mnt/c/Users/Usuario/repos/ableton-mcp-server/.venv-win/Scripts/ableton-mcp-server.exe
```

This process still uses stdio with the WSL MCP client, but it runs in the Windows
network namespace and can securely reach Live's loopback listener. Do not point
Hermes at `.venv/bin/python` from a Linux venv when WSL uses NAT networking.

The bridge deliberately rejects non-loopback hosts. It never binds `0.0.0.0` and
does not expose unauthenticated Live control to the LAN.

## Remote Script lifecycle

The installed script can be managed independently:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe install-script --json
.\.venv-win\Scripts\ableton-mcp.exe install-status --json
```

Set `ABLETON_MCP_SERVER_VERBOSE=1` before starting Live to emit
`[MCP-Server]` startup and verification diagnostics in `Log.txt`. Override log
discovery when necessary with `ABLETON_MCP_LOG_PATH`.

## Guarded Live acceptance test

Use only with a disposable Set. The exact project-name confirmation and an empty
MIDI clip slot are required before any mutation is sent:

```powershell
.\.venv-win\Scripts\ableton-mcp.exe acceptance `
  --confirm-project-name TESTE_CODEX `
  --track-index 0 `
  --clip-index 3 `
  --fire-clip `
  --json
```

The runner exercises transport, loop state, cue creation/deletion, clip creation,
Python-LOM MIDI note insertion, clip firing, and partial-batch semantics. It
restores transport and loop state, but the created clip intentionally remains in
the disposable Set.

## Development verification

```powershell
python -m pytest -q --tb=line
python scripts\coverage_check.py
python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
python -m mypy --strict ableton_mcp_server
python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"
```

Mock socket smoke test:

```powershell
python -m scripts.mock_remote_script --port 9889
python -m scripts.integration_check --port 9889
```

Extension build:

```powershell
cd AbletonMCPServer_Extension
npm install
npm run build
```

## Safety and limitations

- Mutations are not replayed after ambiguous network failures.
- `run_batch` aborts at the first error; the successful prefix persists in one
  undo step and `rolled_back` is `false`.
- `song_length` is read-only.
- Path-ids are session-local index locators and are re-resolved per call.
- The WSL-safe default is a Windows-native MCP process, not a remotely exposed
  bridge.

## Documentation

- [Tool reference](docs/TOOL_REFERENCE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Known Live API quirks](docs/KNOWN_BUGS.md)
- [Changelog](CHANGELOG.md)

## License

MIT
