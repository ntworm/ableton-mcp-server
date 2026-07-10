# Architecture

## Components

The repository contains two cooperating components:

1. `ableton_mcp_server/` is the stdio FastMCP server. It owns Pydantic validation, JSONL encoding, reconnect policy, local log reading, and snapshot diffing. It imports no Ableton module.
2. `AbletonMCPServer_RemoteScript/` runs inside Live. It owns the loopback socket, the main-thread request queue, command handlers, Live Object Model access, and undo grouping.

The shape follows the SDK-free port/adapter boundary demonstrated by [Loophole](https://github.com/OthmanAdi/loophole), adapted to a Python MIDI Remote Script host.

## Data Flow and Thread Safety

```mermaid
flowchart LR
    Agent["MCP client"] -->|stdio MCP| Server["FastMCP tools + Pydantic"]
    Server -->|"TCP JSONL 127.0.0.1:9888"| Socket["Remote Script socket thread"]
    Socket -->|enqueue| Queue["serialized request queue"]
    Queue -->|"advance once per update_display"| Task["UI-tick command state machine"]
    Task -->|Live UI thread only| LOM["Live Object Model"]
    Task -->|verified result queue| Socket
```

The socket thread parses JSON and waits for a response queue. It never reads or writes a Live object. Reads and synchronous mutations can complete in one tick. Deferred mutations yield, let Live process its UI cycle, then read back state on a later tick. Requests are serialized while one deferred command is active, preserving command order and avoiding competing transport writes. Persistent connections remain open while idle; a one-second receive timeout only lets the thread observe shutdown.

## Windows and WSL Process Topology

The Remote Script always binds `127.0.0.1:9888`. On Windows, the MCP process must therefore run in the Windows network namespace. A WSL MCP client launches `.venv-win/Scripts/ableton-mcp-server.exe` through standard WSL interoperability; stdio crosses the boundary while TCP remains Windows-local.

Native Linux Python inside WSL NAT is intentionally not made to work by binding Live to `0.0.0.0`. The JSONL protocol has no remote authentication or encryption, so LAN exposure would be unsafe. Mirrored WSL networking may make localhost work, but it is an optional environment configuration rather than the canonical deployment.

## Socket Protocol

Every frame is UTF-8 JSON followed by `\n`. Frames larger than 1 MiB are rejected.

Request:

```json
{"type": "set_tempo", "params": {"tempo": 128.0}}
```

Success:

```json
{"status": "ok", "result": {"tempo": 128.0}}
```

Error:

```json
{
  "status": "error",
  "code": "PLAYHEAD_NOT_MOVED",
  "message": "Transport setter did not reach the requested value ...",
  "hint": "Live may be in a transitional state; retry after it settles."
}
```

The listener binds the literal `127.0.0.1`. It has no LAN mode.

## Error Model

| Code | Meaning | Recovery |
|---|---|---|
| `UNKNOWN_COMMAND` | Dispatcher has no such command. | Correct the tool/command name. |
| `INVALID_PARAMS` | Envelope or argument shape is invalid. | Fix the argument. |
| `READ_ONLY_VIOLATION` | An explicitly blocked creative mutation was requested. | Use an allowed debug tool. |
| `TIMEOUT` | The UI thread did not answer before the queue timeout. | Inspect Live before retrying mutations. |
| `LIVE_UNAVAILABLE` | Live rejected the operation or an expected host method is absent. | Inspect `Log.txt` and runtime version. |
| `INTERNAL_ERROR` | An unexpected batch handler failure occurred. | Inspect logs and report a reproduction. |
| `PLAYHEAD_NOT_MOVED` | Set/read verification failed after retries. | Let Live settle, inspect state, then retry. |
| `STALE_REFERENCE` | A path-id no longer resolves. | Re-list and use a fresh id. |
| `WRONG_TYPE` | The target exists but cannot perform that operation. | Select a matching track/clip type. |
| `BAD_INPUT` | A well-shaped argument is outside a safe domain. | Correct its value. |

`Client` maps remote errors and socket failures to typed Python exceptions. At the FastMCP boundary, expected bridge exceptions become typed MCP error results rather than internal framework failures. Empty arrays receive both structured `[]` data and a textual `[]` fallback for clients that ignore structured content.

The client automatically retries reads after connection failure. It never automatically retries a mutation: a broken connection does not prove that Live failed to apply the write. Client and Remote Script compute the same deadline from `contracts.request_timeout_seconds`; the 20-second base scales by serialized bulk/batch work units.

## Mutation Allowlist

`contracts.py` defines three disjoint sets:

- `READ_COMMANDS`: Remote Script reads.
- `ALLOWED_MUTATIONS`: transport, loop, cue, Session clip, MIDI-note, and batch debug operations.
- `READ_ONLY_COMMANDS`: creative/destructive operations that remain blocked.

There is no name-prefix rule. An unknown command reaches the dispatcher and returns `UNKNOWN_COMMAND`.

`contracts.py` is copied into `_contracts.py` by `python scripts/vendor_contracts.py`. The generated file has a stable header and identical remaining bytes. Live never imports the server package.

## Path-Id Scheme

Paths use `/`-joined index segments:

```text
track:2
track:2/device:1
track:2/device:1/param:3
track:2/clipslot:4
track:2/clipslot:4/clip
track:2/clip:0
```

Paths contain no Live handle and are JSON-safe. `list_device_params` resolves `track:N` against current Live state on every call. Missing targets return `STALE_REFERENCE`.

These paths are session-local locators, not persistent identities. If a track insertion shifts indexes, `track:2` refers to the new current track at index two. Agents must re-list after structural changes. No Live object is cached by the server.

## Transport Verification

Transport setters return step generators. Each attempt:

1. writes the requested property on Live's UI thread;
2. yields without sleeping or responding to the socket;
3. reads the observed property on a later `update_display` tick;
4. compares numeric state with `0.01` tolerance or boolean state exactly;
5. retries for at most ten UI ticks;
6. returns only the observed value, or raises a typed error.

Playhead writes suspend and restore clip-trigger quantization in `finally`. Start/stop playback, tempo, loop enablement, loop start, and loop length use the same deferred confirmation model.

Cue operations are multiphase. They move and verify `current_song_time`, the official LOM's “current Arrangement playback position”, invoke the toggle exactly once, then hold that position while polling for the locator across UI ticks. `Song.start_time` is intentionally untouched because it controls where playback will start and caused 8-bar/32-beat placement when used as a cue cursor. Names are read back and idempotently retried before success. Single operations finally restore the prior playback position. Bulk creation shares one position scope and restores once after all items, reducing UI writes and timeout pressure.

Python MIDI Remote Scripts do not use the Max LOM dictionary binding for `Clip.add_new_notes`. The handler creates a tuple of `Live.Clip.MidiNoteSpecification` objects and passes that tuple to the Python LOM method.

## Undo and Batch Semantics

Standalone mutations open and close one undo step. `run_batch` opens one outer step and invokes sub-handlers without nested undo steps.

The selected runtime object must expose `begin_undo_step()` and `end_undo_step()`. The Control Surface resolves this capability from the control-surface instance, `c_instance`, application, or song. If no target exposes both methods, the mutation fails with `LIVE_UNAVAILABLE` before changing the Set.

`run_batch` stops at the first error. Successful earlier commands remain applied inside the same undo step. `rolled_back` is always `false`; one Ctrl+Z reverts the grouped successful prefix. Reverse-operation replay is not attempted because it cannot restore every LOM mutation safely.

## State and Time Ownership

- MCP client: one process-global client, serialized by a lock for the server process lifetime.
- Request queue: one per enabled Control Surface.
- Response queue: one per JSONL request.
- Socket receive buffer: one per TCP connection.
- Mock state: one per mock server instance.
- Snapshot time: Unix epoch milliseconds from `time.time()`.
- Deferred attempts: UI ticks, with no sleep or busy-wait on Live's main thread.

## FastMCP Tool Listing Compatibility

FastMCP 3.x exposes an async `list_tools()`. `CountableFastMCP` returns a lazy awaitable proxy that also implements `__len__`, so both forms work:

```python
tools = await mcp.list_tools()
count = len(mcp.list_tools())
```

Tests assert both counts match the 37 registered tools.

`tools/list` remains deterministic metadata discovery. `get_bridge_status` and the `ableton-mcp doctor` CLI perform an actual `get_session_info` round trip and report WSL-specific topology hints when unavailable.

## Live Acceptance Verification

Unit and socket tests are supplemented by a guarded real-Live runner. It refuses mutation unless `get_project_metadata.song_name` exactly matches `--confirm-project-name`, the selected track is MIDI, and the selected slot is empty. It then verifies transport, loop state, exact cue round trips, Python-LOM MIDI notes, clip firing, and partial-batch behavior before restoring transport and loop state.

```powershell
ableton-mcp acceptance --confirm-project-name TESTE_CODEX --track-index 0 --clip-index 3 --fire-clip --json
```

The created Session clip remains intentionally; run only against a disposable Set.
