# Rewriting the Ableton MCP Server — Full Handoff

**audience**: CODEX CLI / GPT-5.x / Claude Opus / any agent with file-edit + terminal access on the Windows host.
**goal**: build **`ableton-mcp-server`**, a standalone MCP server that gives an LLM agent full debug-grade read/write access to a running Ableton Live Set. The deliverable is one Python package (the MCP server) plus one Ableton MIDI Remote Script (the Live-side execution engine) that talk to each other over a localhost TCP socket. Both live in one repo. Nothing else.

**The repo lives at** `C:\Users\Usuario\repos\ableton-mcp-server\` (a brand-new repo at this path; do not nest inside any existing `source-repos/` or sibling directory). Create the directory if it does not exist; init a fresh git repo inside it.

**Reference architecture**: study https://github.com/OthmanAdi/loophole before writing a line. The shape (core/mcp/extension split, `LiveBridge` port, path-id scheme, one-undo-per-write, Zod-validated inputs, transport-agnostic server, typed error model) is the model. **Internalize the patterns. Do not copy code.** Adapt to our context: we run the Live-side piece as a MIDI Remote Script + Python LOM because we target Live on Windows with the Extensions SDK rollout still limited for our install. Keep that surface for now, but structure the Python server code so a future port to the SDK adapter is mechanical, not a rewrite.

---

## 0. What this project is

**`ableton-mcp-server`** is **one repo, two cooperating components**:

1. **The MCP server package** — a Python package the maintainer runs as a stdio MCP server. Translates MCP tool calls from any MCP-compatible client (Claude, Cursor, Codex CLI, custom agents) into newline-delimited JSON TCP requests to the Live-side script.
2. **The Ableton MIDI Remote Script** — a single Python file the maintainer copies into Live's MIDI Remote Scripts directory and enables in `Preferences → Link, Tempo & MIDI → Control Surfaces`. Listens on TCP `127.0.0.1:9888`, executes commands on the Live UI thread, and reads/writes the Live Object Model.

Both communicate over a newline-delimited JSON TCP socket. The Remote Script queues requests and dispatches them on the Live UI thread (cross-thread LOM access crashes Live).

**The project is standalone.** It does not depend on, integrate with, share code with, or live alongside any other project. Any reference to other repos, paths, or workflows is accidental and should be removed.

The maintainer runs **Live 12.4.5b7 (Beta)** on Windows 11. Every change is tested manually on a real Live session. The agent cannot test inside Live — code must be **provably correct on inspection** and shipped in a state where a one-click reload in Live works.

---

## 1. Repo layout — read this first

```
C:\Users\Usuario\repos\ableton-mcp-server\
├── manifest.json                              # package identity (name/version/author)
├── pyproject.toml                             # Python package metadata, deps, ruff/mypy config
├── README.md                                  # what + why + install
├── LICENSE
├── CHANGELOG.md                               # follows Keep a Changelog
├── contracts.py                               # single source of truth, zero deps, vendored
├── ableton_mcp_server\                        # MCP server package (runs as stdio MCP server)
│   ├── __init__.py
│   ├── client.py                              # TCP client to the Remote Script
│   ├── protocol.py                            # request/response envelope dataclasses
│   ├── server.py                              # FastMCP tool decorators, the public surface
│   ├── snapshot.py                            # full-state snapshot data shape
│   ├── diff.py                                # snapshot diffing for change-detection
│   ├── ids.py                                 # path-id scheme: parse / format / resolve
│   ├── errors.py                              # typed BridgeError hierarchy
│   ├── models.py                              # Pydantic input/output models
│   └── write_guard.py                         # re-exports from contracts.py
├── AbletonMCPServer_RemoteScript\             # Live-side script (copied into Live's MIDI Remote Scripts dir)
│   ├── __init__.py                            # the Remote Script
│   ├── _contracts.py                          # vendored copy of ../contracts.py
│   └── README.md
├── docs\
│   ├── ARCHITECTURE.md                        # system overview + socket protocol + thread safety
│   ├── TOOL_REFERENCE.md                      # tool-by-tool docs
│   └── KNOWN_BUGS.md                          # Live API quirks we work around
├── scripts\
│   ├── vendor_contracts.py                    # copies contracts.py → _contracts.py
│   ├── integration_check.py                   # smoke test against a mock Remote Script
│   └── mock_remote_script.py                  # in-memory Remote Script for local testing
└── tests\
    ├── test_client.py
    ├── test_protocol.py
    ├── test_server_tools.py
    ├── test_snapshot.py
    ├── test_diff.py
    ├── test_ids.py                            # NEW — path-id scheme
    ├── test_contracts.py                      # NEW — allowlist / blocklist
    ├── test_cue_point_retry.py                # NEW — retry pattern regression
    ├── test_bulk_create.py                    # NEW — bulk operation aggregation
    ├── test_transaction.py                    # NEW — batch / undo grouping
    └── fixtures\{sample_snapshot.json, sample_diff.json}
```

Read every existing file before changing anything.

---

## 2. Bugs and Live-API quirks — the canonical list

The current Live-side script has bugs and the Live Python LOM has quirks that any implementation must work around. These are **categories**, not tied to any specific user project. Document each as a category so future implementers recognize new instances.

### 2.1 Category A — non-deterministic transport setters

**Symptom (canonical form)**: setting a transport-related property on the Live Song object (playhead, loop start, loop length, etc.) does not always produce the requested value. The setter may clamp, snap, ignore, or apply a partial move.

**Workaround**: every transport-state write must:
1. Suspend `clip_trigger_quantization` (set `Song.Quantization.q_no_q`) before the write; restore in `finally`.
2. Write the value.
3. Read it back and compare to the requested value.
4. Retry up to N times (default 3) with a short inter-attempt sleep (default 0.01 s — must NOT busy-wait the UI thread).
5. If the value still does not match, raise a structured error (e.g. `PLAYHEAD_NOT_MOVED`) and **do not perform any follow-up operations** that depend on the move having succeeded.

This pattern is mandatory for: `current_song_time`, `loop_start`, `loop_length`, `start_marker`, `end_marker`, `signature_numerator`, `signature_denominator`.

### 2.2 Category B — toggle operations masquerading as create

**Symptom (canonical form)**: certain Live API methods that read as "create X" actually toggle X at the current playhead. If X already exists at the playhead, the call deletes it; if not, it creates it. The caller has no in-band signal of which happened.

**Workaround**: before any such call, enumerate the existing objects and decide which branch (create vs delete) the user actually wants. NEVER call the toggle without first verifying intent.

This applies to: `Song.set_or_delete_cue()` (the only way to create cue points via Python — there is no `Song.create_cue_point()` method). Document each toggle method explicitly in `KNOWN_BUGS.md`.

### 2.3 Category C — read-only properties that look writable

**Symptom (canonical form)**: a Live Song property (e.g. `song_length`) looks like it should be settable but raises `"property of 'Song' object has no setter"` at runtime. The property is derived from Set content (clips on the Arrangement timeline grow the song length automatically; clip triggers in Session view do NOT).

**Workaround**: do not expose a "set X" tool for any read-only property. Remove any existing attempt. Document the workaround in `KNOWN_BUGS.md` and in the relevant tool's reference page (e.g. "to grow `song_length`, drop a MIDI or audio clip on the Arrangement timeline").

### 2.4 Category D — non-existent methods

**Symptom (canonical form)**: code references a Live API method that does not exist on the actual object (e.g. `song.delete_cue_point(cp)`). The call fails at runtime with `AttributeError`.

**Workaround**: before adding any LOM call, verify the method exists on the target object type. The canonical place for "I want to delete a cue point" is: move playhead to the cue's time + call the toggle (`set_or_delete_cue`). The canonical place for "I want to create a cue point" is the same toggle, after first checking that no cue exists at the target time.

### 2.5 Category E — custom beat-time type, not float

**Symptom (canonical form)**: `Song.cue_points[i].time` returns a `Live.BeatTime` object (or similar custom numeric subclass), not a Python `float`. Comparing it with `<`, `abs()`, or arithmetic operators against a plain `float` may produce unexpected results because of operator overloading or unit ambiguity.

**Workaround**: always cast `float(cp.time)` when comparing against a Python float. Use a generous tolerance (default `0.01` beats) — Live's beat resolution is coarse enough that 0.01 is safe and avoids spurious misses.

### 2.6 Category F — duplicated protocol constants drift

**Symptom (canonical form)**: the same allowlist/blocklist of commands lives in two places (server-side and Remote-Script-side) and the two copies drift apart, causing the server to permit a command the Remote Script rejects (or vice versa).

**Workaround**: keep exactly one canonical copy of all protocol constants in a dependency-free module (`contracts.py`). The Remote Script folder vendors a copy via a build script (`scripts/vendor_contracts.py`) at release time. The vendor file has a header that says "GENERATED FILE — DO NOT EDIT". CI verifies the vendor file is up to date with the canonical.

### 2.7 Category G — session-local integer indices

**Symptom (canonical form)**: every existing tool returns integer `track_index`, `device_index`, `clip_index` that is only meaningful in the current Live session. Indices shift as tracks are added or removed. An agent that captured "track 2 = bass" five minutes ago cannot reason about it anymore.

**Workaround**: introduce a path-id scheme (`track:N`, `track:N/clipslot:S`, `track:N/device:D/param:P`, `track:N/clip:C`). Path-ids are session-local but **re-resolved on every call** by the server (the integer indices inside the path are re-fetched from the live snapshot before each tool invocation). When an object has been deleted, raise `STALE_REFERENCE` with a hint to re-resolve via `live_find_track`. Tools that take path-ids validate them; tools that return data return path-ids. Legacy integer-index tools are kept as thin wrappers for one minor version and marked deprecated in their docstrings.

### 2.8 Category H — many small mutations = many undo steps

**Symptom (canonical form)**: a single high-level operation (e.g. "create 40 cue points for a setlist") currently expands to 40 separate tool calls, each producing its own Live undo step. Hitting Undo 40 times to revert is broken UX.

**Workaround**: expose a `run_batch` tool that accepts a list of sub-commands and executes them inside one `app.begin_undo_step() / app.end_undo_step()` pair. Document that one batch call = one Live undo step. The sub-commands are executed sequentially, and the first error aborts the batch (the undo step still closes, which rolls back the partial state).

### 2.9 Category I — over-defensive mutation blocklist

**Symptom (canonical form)**: the initial implementation blocklists any command whose name starts with `set_`, `create_`, `delete_`, `fire_`, etc. This blocks legitimate debug operations (move the playhead, start/stop playback, set tempo, set loop bounds) because the blocklist is a defense-in-depth measure against destructive operations, but real debug workflows need these tools.

**Workaround**: split the allowlist into two explicit sets:
- `ALLOWED_MUTATIONS`: debug-necessary mutations (transport, tempo, loop, cue points, batch). Allow these.
- `READ_ONLY_COMMANDS`: blocked because they're creative/production operations with no debug value (delete track, load browser item, switch view). Keep these blocked.

Anything not in either set is allowed by default (the blocklist is no longer prefix-based). Document the rationale for every entry in both sets in `KNOWN_BUGS.md`.

---

## 3. The rewrite target architecture

### 3.1 New folder layout

See §1. The shape is:
- One canonical Python package for the server (`ableton_mcp_server/`)
- One Remote Script folder (`AbletonMCPServer_RemoteScript/`) that vendors `contracts.py`
- One docs folder with three documents
- One scripts folder with vendor + smoke test
- One tests folder with unit + integration coverage

### 3.2 `contracts.py` — the single source of truth

Top-level, **zero deps**, pure constants and enums. Vendored into the Remote Script folder via `scripts/vendor_contracts.py`.

```python
"""Single source of truth for the protocol between MCP server and Live Remote Script.

This file is intentionally dependency-free so it can be vendored into
AbletonMCPServer_RemoteScript/_contracts.py without polluting Live's import path.

DO NOT IMPORT ANYTHING HERE. Pure stdlib only.
"""

# === Command allowlist ===
ALLOWED_MUTATIONS: frozenset[str] = frozenset({
    # Transport
    "set_current_song_time",
    "start_playback",
    "stop_playback",
    # Tempo
    "set_tempo",
    # Loop
    "set_loop",
    "set_loop_start",
    "set_loop_length",
    # Cue points
    "create_cue_point",
    "bulk_create_cue_points",
    "delete_cue_point",
    # Composition
    "run_batch",
})

READ_ONLY_COMMANDS: frozenset[str] = frozenset({
    "create_clip",
    "create_midi_track",
    "delete_track",
    "set_track_name",
    "fire_clip",
    "add_notes_to_clip",
    "duplicate_session_clip_to_arrangement",
    "switch_to_arrangement_view",
    "load_instrument_or_effect",
    "load_browser_item",
    # NOTE: set_song_length intentionally REMOVED — read-only in Live's LOM
})

# === Error codes ===
ERROR_UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
ERROR_INVALID_PARAMS = "INVALID_PARAMS"
ERROR_READ_ONLY_VIOLATION = "READ_ONLY_VIOLATION"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_LIVE_UNAVAILABLE = "LIVE_UNAVAILABLE"
ERROR_INTERNAL_ERROR = "INTERNAL_ERROR"
ERROR_PLAYHEAD_NOT_MOVED = "PLAYHEAD_NOT_MOVED"   # Category A
ERROR_STALE_REFERENCE = "STALE_REFERENCE"         # Category G
ERROR_WRONG_TYPE = "WRONG_TYPE"
ERROR_BAD_INPUT = "BAD_INPUT"

# === Protocol constants ===
DEFAULT_PORT = 9888
REQUEST_TYPE_FIELD = "type"
REQUEST_PARAMS_FIELD = "params"
RESPONSE_STATUS_OK = "ok"
RESPONSE_STATUS_ERROR = "error"

# === Retry / tolerance ===
CUE_TIME_TOLERANCE = 0.01          # beats (Category E)
PLAYHEAD_MOVE_RETRIES = 3          # Category A
PLAYHEAD_MOVE_SLEEP = 0.01         # seconds — must NOT busy-wait the UI thread

# === Snapshot freshness ===
SNAPSHOT_REFRESH_INTERVAL_MS = 100 # main-thread poll interval


def is_allowed_mutation(command_name: str) -> bool:
    return command_name.strip().lower() in ALLOWED_MUTATIONS


def is_read_only(command_name: str) -> bool:
    return command_name.strip().lower() in READ_ONLY_COMMANDS


def assert_read_only(command_name: str) -> None:
    """Raises ValueError if command_name is in READ_ONLY_COMMANDS.
    Allows ALLOWED_MUTATIONS and read-only commands.
    """
    if is_read_only(command_name):
        raise ValueError(
            f"Command '{command_name}' is blocked: state mutation is not allowed."
        )
```

### 3.3 New modules — `ids.py`, `errors.py`, `models.py`

**`ids.py`** — path-id grammar:

```python
import re
from typing import Literal

TrackKind = Literal["midi", "audio", "return", "master"]

# Path-id grammar:
#   track:N                          a track
#   track:N/device:D                 a device on track
#   track:N/device:D/param:P         a device parameter
#   track:N/clipslot:S               a Session clip slot
#   track:N/clipslot:S/clip          the clip in that slot
#   track:N/clip:C                   an Arrangement clip (by arrangement index)

_PATH_RE = re.compile(
    r"^track:(?P<track>\d+)"
    r"(?:/(?P<seg1>(?:device|clipslot|clip)(?::\d+)?)(?:/(?P<seg2>(?:param|clip)(?::\d+)?))?)?$"
)


def parse_path(path: str) -> dict:
    """Parse a path-id string into its segments. Raises ValueError on malformed input."""
    m = _PATH_RE.match(path)
    if not m:
        raise ValueError(f"Invalid path-id: {path!r}")
    # ... return {"kind": "track", "track_index": 2} or
    # {"kind": "device", "track_index": 2, "device_index": 1} etc.


def format_path(*segments: str) -> str:
    """Build a path-id from segments."""
    return "/".join(segments)
```

**`errors.py`** — typed BridgeError hierarchy:

```python
class BridgeError(Exception):
    """Base class for all errors that cross the MCP boundary."""
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint

    def to_envelope(self) -> dict:
        return {
            "status": "error",
            "code": self.code,
            "message": str(self),
            **({"hint": self.hint} if self.hint else {}),
        }


class StaleReferenceError(BridgeError):
    code = "STALE_REFERENCE"

    def __init__(self, path_id: str):
        super().__init__(
            f"Path-id {path_id!r} no longer points at a live object.",
            hint="Re-resolve via live_find_track or live_snapshot.",
        )


class WrongTypeError(BridgeError):
    code = "WRONG_TYPE"


class BadInputError(BridgeError):
    code = "BAD_INPUT"


class PlayheadNotMovedError(BridgeError):
    code = "PLAYHEAD_NOT_MOVED"

    def __init__(self, requested: float, actual: float, attempts: int):
        super().__init__(
            f"Transport setter did not reach the requested value "
            f"(asked={requested}, got={actual} after {attempts} retries).",
            hint="Live API may be in a transitional state. Retry the call later or report upstream.",
        )
```

**`models.py`** — Pydantic input models per tool:

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class CuePointSpec(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=256)]
    time: Annotated[float, Field(ge=0, le=100000, description="Beats from song start.")]


class BulkCuePointRequest(BaseModel):
    items: Annotated[list[CuePointSpec], Field(min_length=1, max_length=500)]


class NoteSpec(BaseModel):
    pitch: Annotated[int, Field(ge=0, le=127)]
    start: Annotated[float, Field(ge=0, description="Beats within the clip.")]
    duration: Annotated[float, Field(gt=0)]
    velocity: Annotated[int, Field(ge=0, le=127)] = 100
```

### 3.4 Remote Script rewrite — the core of this task

`AbletonMCPServer_RemoteScript/__init__.py` needs to be **rewritten, not patched**. The current 829-line file mixes socket handling, command dispatch, snapshot capture, and LOM access. Split into internal helpers but keep **one file** (Live Remote Scripts must be a single Python file in a flat folder).

New internal structure (still one file, just organized):

```
__init__.py
├── _contracts.py                    # vendored from ../contracts.py
├── imports
├── constants (PORT, QUEUE_TIMEOUT, etc)
├── class AbletonMCPServer           # the control surface
│   ├── __init__                     # builds socket listener thread, register listeners
│   ├── disconnect / reconnect
│   ├── _on_update_display           # main UI thread poll
│   ├── _execute_command             # dispatcher
│   └── _capture_snapshot            # moves out of _execute_command
├── command handlers (free functions)
│   ├── cmd_get_session_info
│   ├── cmd_get_track_list
│   ├── cmd_get_track_state
│   ├── cmd_get_device_list
│   ├── cmd_get_clip_summary
│   ├── cmd_get_clip_notes
│   ├── cmd_get_control_surfaces
│   ├── cmd_get_browser_categories
│   ├── cmd_get_routing
│   ├── cmd_get_locators
│   ├── cmd_get_selected_context
│   ├── cmd_get_scenes
│   ├── cmd_get_project_metadata
│   ├── cmd_get_loop_settings
│   ├── cmd_take_snapshot
│   ├── cmd_create_cue_point         # uses Category A + B patterns
│   ├── cmd_bulk_create_cue_points   # delegates to cmd_create_cue_point
│   ├── cmd_delete_cue_point         # uses Category D workaround
│   ├── cmd_set_current_song_time    # uses Category A pattern
│   ├── cmd_set_tempo
│   ├── cmd_start_playback
│   ├── cmd_stop_playback
│   ├── cmd_set_loop
│   ├── cmd_set_loop_start
│   ├── cmd_set_loop_length
│   └── cmd_run_batch                # Category H — one batch = one undo step
├── socket server helpers
│   ├── _start_socket_server
│   ├── _serve_client
│   └── _read_request / _write_response
├── snapshot capture
│   └── _capture_full_snapshot
└── log helpers
    └── _setup_logger
```

**Canonical pattern for any transport-state setter (Category A):**

```python
def _set_transport_value(song, setter, value: float, *, retries: int = PLAYHEAD_MOVE_RETRIES) -> float:
    """Set a transport value with retry-and-verify. Returns the actual value reached.

    Raises PlayheadNotMovedError if the value still does not match after retries.
    """
    prev_quant = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = Song.Quantization.q_no_q
        actual = None
        for _ in range(retries):
            setter(value)
            actual = song.current_song_time if setter is _set_current_song_time else value
            if abs(float(actual) - value) < 0.01:
                return float(actual)
            time.sleep(PLAYHEAD_MOVE_SLEEP)
        raise PlayheadNotMovedError(value, float(actual) if actual is not None else -1.0, retries)
    finally:
        song.clip_trigger_quantization = prev_quant
```

**Canonical pattern for `create_cue_point` (Categories A + B + D + E):**

```python
def cmd_create_cue_point(song, *, name: str, time: float) -> dict:
    """Create a cue point at the given time with the given name. Idempotent rename if exists."""
    name = str(name).strip()
    if not name:
        raise BadInputError("name must be non-empty")
    time = float(time)
    if time < 0 or time != time:
        raise BadInputError(f"time must be finite and non-negative (got {time})")

    # Step 1: idempotency (Category B + E) — if cue already exists at this time, rename it.
    for cp in song.cue_points:
        if abs(float(cp.time) - time) < CUE_TIME_TOLERANCE:  # Category E
            cp.name = name
            return {"name": name, "time": float(cp.time), "action": "renamed"}

    # Step 2: prepare transport.
    prev_time = song.current_song_time
    try:
        # Step 3: move playhead with retries (Category A).
        _set_transport_value(song, lambda t: setattr(song, "current_song_time", t), time)

        # Step 4: toggle creates a cue at the playhead (Category B/D — the only way).
        song.set_or_delete_cue()

        # Step 5: find the cue we just created and rename it.
        for cp in song.cue_points:
            if abs(float(cp.time) - time) < CUE_TIME_TOLERANCE:
                cp.name = name
                return {"name": name, "time": float(cp.time), "action": "created"}

        raise BridgeError(
            f"set_or_delete_cue() did not produce a cue near time={time}",
            hint="Live did not create a cue despite a successful playhead move. Check Log.txt for clues.",
        )
    finally:
        song.current_song_time = prev_time
```

**Canonical pattern for `bulk_create_cue_points`:**

Thin wrapper that calls `cmd_create_cue_point` for each item and collects per-item results. **No duplicated logic** — the source of truth stays in `cmd_create_cue_point`. All successes + per-item errors in one response.

**Canonical pattern for `delete_cue_point` (Category D workaround):**

```python
def cmd_delete_cue_point(song, *, time: float) -> dict:
    time = float(time)
    target = None
    for cp in song.cue_points:
        if abs(float(cp.time) - time) < CUE_TIME_TOLERANCE:
            target = cp
            break
    if target is None:
        return {"deleted": False, "reason": "no cue at time"}

    prev_time = song.current_song_time
    try:
        _set_transport_value(song, lambda t: setattr(song, "current_song_time", t), float(target.time))
        song.set_or_delete_cue()  # toggle = delete since cue exists at playhead
    finally:
        song.current_song_time = prev_time
    return {"deleted": True, "time": float(target.time)}
```

**Canonical pattern for `run_batch` (Category H):**

```python
def cmd_run_batch(song, *, commands: list[dict]) -> dict:
    """Execute a list of sub-commands inside one Live undo step.
    Each sub-command has {type, params}. Stops on first error.
    """
    results = []
    app = Live.Application.get_application()
    try:
        app.begin_undo_step()
        for i, sub in enumerate(commands):
            try:
                handler = COMMAND_HANDLERS.get(sub.get("type", ""))
                if handler is None:
                    raise UnknownCommandError(sub.get("type", ""))
                result = handler(song, **(sub.get("params") or {}))
                results.append({"index": i, "status": "ok", "result": result})
            except BridgeError as e:
                results.append({"index": i, "status": "error", **e.to_envelope()})
                results.append({"status": "aborted", "completed": i})
                break
        return {"results": results, "completed": len([r for r in results if r.get("status") == "ok"])}
    finally:
        app.end_undo_step()
```

### 3.5 The MCP server tool surface (35+ tools)

Keep all 22 existing tools. Add these 13:

| # | Tool | Params | Notes |
|---|------|--------|-------|
| 23 | `set_current_song_time` | `time: float` | moved from blocklist (Category A pattern) |
| 24 | `set_tempo` | `tempo: float` (20–999) | debug tool |
| 25 | `start_playback` | — | debug tool |
| 26 | `stop_playback` | — | debug tool |
| 27 | `set_loop` | `enabled: bool` | debug tool |
| 28 | `set_loop_start` | `start_beat: float` | Category A pattern |
| 29 | `set_loop_length` | `length_beats: float` | Category A pattern |
| 30 | `run_batch` | `commands: list[CommandSpec]` | Category H — one batch = one undo step |
| 31 | `live_find_track` | `query: str` | path-id resolution |
| 32 | `list_device_params` | `track_id: str` (path-id) | Category G — path-ids |
| 33 | `add_notes_to_clip` | `track_index, clip_index, notes: list[NoteSpec]` | moved from blocklist |
| 34 | `fire_clip` | `track_index, clip_index` | moved from blocklist |
| 35 | `create_clip` | `track_index, clip_index, length_beats: float` | moved from blocklist |

Tools remaining in the blocklist (`READ_ONLY_COMMANDS`): `create_midi_track`, `delete_track`, `set_track_name`, `duplicate_session_clip_to_arrangement`, `switch_to_arrangement_view`, `load_instrument_or_effect`, `load_browser_item`. These are still risky / not needed by debug workflows.

Every tool gets a docstring of the form:

```python
"""One-line summary.

Longer description if needed.

Side effects: writes to transport (one undo step).
Side effects: none (pure read).

Example:
    request: {"type": "set_tempo", "params": {"tempo": 128.0}}
    response: {"status": "ok", "result": {"tempo": 128.0}}

Edge cases:
- BPM below 20 or above 999 → BadInputError
- Audio thread busy → LiveUnavailableError
"""
```

### 3.6 The path-id scheme (Category G)

All path-ids are strings of the form `kind:index` chained with `/`. They are **session-local** — re-resolved on every call. The server keeps a small index cache with a short TTL (e.g. 5 seconds) to avoid hammering the Live API for back-to-back calls, but every tool invocation re-fetches the actual indices.

When a tool's input accepts a path-id, parse it via `ids.parse_path()` and resolve it to a live object before operating. When the object's index has shifted, raise `StaleReferenceError` so the agent can re-fetch.

Examples of path-id use in tool inputs:

- `set_loop("track:2")` — set loop on track 2
- `add_notes_to_clip("track:2/clipslot:4/clip", notes=[...])`
- `fire_clip("track:0/clipslot:0/clip")`

For backwards compat: keep the legacy integer-index variants of existing tools (`get_track_state(track_index=2)`) but mark them deprecated in tool descriptions. New tools (`live_find_track`, `list_device_params`) only accept path-ids.

### 3.7 Tests

- Keep all existing tests. They should pass unchanged.
- Add `tests/test_cue_point_retry.py` with **mocked `Song` objects** that simulate the playhead-stuck behavior. Assert the new retry logic actually retries and raises `PlayheadNotMovedError` after the threshold.
- Add `tests/test_ids.py` — pure unit tests of path-id parse/format, including malformed inputs.
- Add `tests/test_contracts.py` — pure unit tests of the allowlist/blocklist.
- Add `tests/test_bulk_create.py` — verifies `bulk_create_cue_points` calls `create_cue_point` for each item and aggregates results.
- Add `tests/test_transaction.py` — verifies `run_batch` wraps in a `begin_undo_step`/`end_undo_step` pair, that errors abort the batch, that the undo step is always closed even on exception.
- Run `pytest --cov` and require ≥85% coverage on `ableton_mcp_server/` and `AbletonMCPServer_RemoteScript/__init__.py`.

### 3.8 Vendoring strategy

Live's Remote Script folder runs with its own `sys.path`. It cannot reliably import from `ableton_mcp_server` (a Python package). The fix is to **vendor** `contracts.py` into `AbletonMCPServer_RemoteScript/_contracts.py`:

- Add `scripts/vendor_contracts.py` that does a literal file copy with a header comment indicating generation timestamp.
- Document in `docs/ARCHITECTURE.md`: "the Remote Script does not import the server package. `contracts.py` is the single source of truth; vendor it with `python scripts/vendor_contracts.py` whenever you change the canonical file."
- Add a comment in `AbletonMCPServer_RemoteScript/_contracts.py`:
  ```
  # GENERATED FILE — DO NOT EDIT.
  # Source: ../contracts.py
  # Regenerate with: python scripts/vendor_contracts.py
  ```

### 3.9 Docs

- **`CHANGELOG.md`**: new, follow [Keep a Changelog](https://keepachangelog.com/). First entry is `0.2.0` dated today with subsections for Added / Changed / Removed / Fixed.
- **`TOOL_REFERENCE.md`**: rewrite for every tool. Each entry has: signature, params, return shape, example request, example response, edge cases.
- **`KNOWN_BUGS.md`**: new. Document every Live API quirk we work around, using the **Category A–I labels** from §2 as the structure. Each entry has: symptom (generic), root cause, workaround, link to bug report if any.
- **`ARCHITECTURE.md`**: expand the "Thread Safety" section with the retry-without-busy-wait pattern. Add new sections for "Mutation Allowlist", "Path-Id Scheme", and "Transaction Grouping".

---

## 4. Tasks — exact order, with verification steps

1. **Read every existing file** in the source repo (server, client, protocol, snapshot, diff, write_guard, remote script, all tests, both docs). Don't skip.
2. **Read the Loophole repo** (https://github.com/OthmanAdi/loophole) at least: root README, `packages/core/README.md`, `packages/mcp/README.md`, `packages/extension/README.md`. Take notes on the architecture. Use it as the reference for the port + tools + path-id pattern.
3. **Create `contracts.py`** at repo root with the contents from §3.2. Pure stdlib only.
4. **Create `scripts/vendor_contracts.py`** that copies `contracts.py` to `AbletonMCPServer_RemoteScript/_contracts.py` with a header. Run it. Verify the file exists and starts with the GENERATED FILE comment.
5. **Create `errors.py`** with the `BridgeError` hierarchy from §3.3.
6. **Create `ids.py`** with the path-id scheme from §3.3.
7. **Create `models.py`** with the Pydantic models from §3.3 plus per-tool models for all 35 tools.
8. **Refactor `write_guard.py`** to import from `contracts.py` and re-export. Behavior unchanged.
9. **Add `tests/test_contracts.py`**, `tests/test_ids.py` with unit tests. Run `pytest tests/test_contracts.py tests/test_ids.py -v` — must pass.
10. **Rewrite `AbletonMCPServer_RemoteScript/__init__.py`** following §3.4. Use `_contracts` instead of inline constants. Add the new commands per §3.4. Lift all other commands into named functions. Target: 700–900 lines (a small bump from 829 is OK for readability gains; a large drop means you dropped features).
11. **Run `python -c "import ast; ast.parse(open('AbletonMCPServer_RemoteScript/__init__.py').read())"`** — must exit 0.
12. **Add `tests/test_cue_point_retry.py`** with a mocked Song that doesn't move its playhead. Verify retry logic raises `PlayheadNotMovedError` after the configured number of retries.
13. **Add `tests/test_bulk_create.py`** verifying bulk_create aggregates per-item results.
14. **Add `tests/test_transaction.py`** verifying batch wraps in begin_undo_step/end_undo_step and aborts on first error.
15. **Run full test suite**: `python -m pytest tests/ -v --tb=short`. Must pass, coverage ≥85%.
16. **Expand `server.py`** with the 13 new tools per §3.5. Every tool gets a docstring. Use the Pydantic models from `models.py`.
17. **Run `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"`** — must print a number ≥ 35.
18. **Run `python -m ruff check ableton_mcp_server/ AbletonMCPServer_RemoteScript/`** — must exit 0.
19. **Run `python -m mypy --strict ableton_mcp_server/`** — must exit 0.
20. **Update `docs/TOOL_REFERENCE.md`** with every tool. Order: reads first, writes second, snapshots/diff last.
21. **Update `docs/ARCHITECTURE.md`** with the mutation-allowlist section, path-id scheme, transaction grouping, and the new thread-safety writeup.
22. **Create `docs/KNOWN_BUGS.md`** with the Live API quirks from §2.
23. **Create `CHANGELOG.md`** with the `0.2.0` entry.
24. **Bump `manifest.json` and `pyproject.toml` to `0.2.0`**.
25. **Commit everything as ONE atomic commit**:
    ```
    git add -A
    git status    # verify only intended files
    git commit -m "$(cat <<'EOF'
    refactor(ableton-mcp-server): v0.2.0 — full rewrite

    - extract contracts.py (single source of truth for allowlist/blocklist)
    - rewrite Remote Script with retry pattern for non-deterministic transport setters
    - lift blocklist on debug-necessary mutations (transport, tempo, loop, set_current_song_time)
    - add 13 new MCP tools (set_tempo, start/stop_playback, set_loop*, run_batch, ...)
    - add Pydantic models for all tool params
    - add typed BridgeError hierarchy (StaleReferenceError, WrongTypeError, PlayheadNotMovedError, ...)
    - add path-id scheme (track:N, track:N/clipslot:S/clip, ...) modeled on loophole
    - add run_batch command grouping mutations into one Live undo step
    - vendor contracts.py into Remote Script via scripts/vendor_contracts.py
    - add test_cue_point_retry.py + test_bulk_create.py + test_transaction.py + test_ids.py + test_contracts.py
    - add CHANGELOG.md, KNOWN_BUGS.md, expanded TOOL_REFERENCE.md + ARCHITECTURE.md

    Architecture reference: https://github.com/OthmanAdi/loophole

    Co-Authored-By: ...
    EOF
    )"
    ```
26. **Report back**:
    - The SHA of the commit.
    - The output of `python -m pytest tests/ -q --tb=line` (one line per failure, or "X passed in Ys").
    - The output of `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"`.
    - The output of `python -m ruff check ableton_mcp_server/ AbletonMCPServer_RemoteScript/`.
    - The output of `git status` (should be clean).
    - The list of files changed (from `git show --stat HEAD`).
    - **Explicitly** call out anything you did NOT do, anything you had to skip, anything that worked around the spec.

---

## 5. Conventions — non-negotiable

- **No new dependencies without approval**. Stick to `mcp`, `fastmcp`, `pydantic`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`. If you need something else, **stop and ask**.
- **No reformatting of unrelated files**. Touch only what the spec requires.
- **No `.ablx` files** in the repo. The Remote Script is the deliverable; packaging happens later by the maintainer.
- **All paths in Windows form** when reporting back (`C:\Users\Usuario\repos\...`), not WSL form.
- **The Remote Script folder is deployed by hand** (the maintainer copies `AbletonMCPServer_RemoteScript/` into Live's MIDI Remote Scripts directory, deletes `__pycache__`, restarts Live). Your commit must be **deploy-ready**: `python -c "import ast; ast.parse(...)"` passes, ruff passes, mypy passes, full test suite passes.
- **The maintainer tests manually**. The agent cannot simulate Live. Code that LOOKS right but FAILS in Live is unacceptable. Be conservative — every LOM access path should be one with empirical evidence (the canonical patterns in §3.4 are evidence-backed).
- **No push**. Local-only repo. `git push` is forbidden.
- **Git hygiene**: atomic commits only. Don't leave the working tree dirty at the end.
- **No emoji in code, comments, or commits.** Maintainer's house style.
- **The project is standalone**. Do not introduce any reference, dependency, or coupling to any other project. If you find a comment or import that mentions another project, treat it as accidental and remove it.

---

## 6. What the agent CAN'T do

- The agent can't open Live.
- The agent can't talk to the maintainer directly.
- The agent can't read the actual state of any specific user's Live Set.
- The agent can't test against a real Live session — only mocked Song objects in pytest.
- The agent can't infer requirements from any other project. This project is self-contained; the reference is Loophole's architecture, not any sibling project.
- The agent can't predict which Live API calls will be deterministic. The retry pattern in §3.4 is the canonical mitigation; new instances of the same category must use the same pattern.

---

## 7. Debug instrumentation helper

Include this in the rewritten Remote Script, **gated behind an env var** (`ABLETON_MCP_SERVER_VERBOSE=1`):

```python
import os
_VERBOSE = os.environ.get("ABLETON_MCP_SERVER_VERBOSE") == "1"


def _dbg(msg: str) -> None:
    if _VERBOSE:
        logger.info(f"[PROBE] {msg}")
```

Use it in `cmd_create_cue_point` like:

```python
_dbg(f"create_cue_point name={name!r} time={time} prev={prev_time}")
song.current_song_time = time
actual = song.current_song_time
_dbg(f"after_set asked={time} got={actual}")
```

The maintainer can then set the env var in Live's launch config, restart, reproduce a failure, and grep `[PROBE]` from the Live Log file. Log location depends on the Live install — search `C:\Users\Usuario\AppData\Roaming\Ableton\` for `Preferences\Log.txt`.

---

## 8. Acceptance checklist

Tick every box before reporting "done".

- [ ] `contracts.py` exists at repo root with the allowlist/blocklist/error codes.
- [ ] `AbletonMCPServer_RemoteScript/_contracts.py` is identical (byte-for-byte, modulo vendor header) to `contracts.py`.
- [ ] `ableton_mcp_server/write_guard.py` re-exports from `contracts.py`.
- [ ] `ableton_mcp_server/errors.py` defines the BridgeError hierarchy.
- [ ] `ableton_mcp_server/ids.py` defines the path-id scheme with parse/format.
- [ ] `ableton_mcp_server/models.py` defines Pydantic models for every tool's params.
- [ ] `manifest.json` and `pyproject.toml` both at `0.2.0`.
- [ ] `AbletonMCPServer_RemoteScript/__init__.py` uses `_contracts`, NOT inline constants.
- [ ] `cmd_create_cue_point` implements the retry-then-PlayheadNotMovedError pattern from §3.4.
- [ ] `cmd_bulk_create_cue_points` delegates to `cmd_create_cue_point` (no duplicated logic).
- [ ] `cmd_delete_cue_point` uses the toggle-after-move-playhead pattern, NOT `song.delete_cue_point()`.
- [ ] `cmd_set_current_song_time` exists and is wired into the dispatcher.
- [ ] `cmd_run_batch` exists and wraps in `begin_undo_step`/`end_undo_step`.
- [ ] `cmd_set_tempo`, `cmd_start_playback`, `cmd_stop_playback`, `cmd_set_loop`, `cmd_set_loop_start`, `cmd_set_loop_length` exist.
- [ ] `set_song_length` is removed everywhere — not in the allowlist, not a tool, not a handler.
- [ ] 35+ MCP tools exposed (22 original + 13 new).
- [ ] Every tool has a docstring + Pydantic input model.
- [ ] `pytest` passes, coverage ≥85%.
- [ ] `ruff check` passes.
- [ ] `mypy --strict` passes on the server package.
- [ ] `CHANGELOG.md`, `KNOWN_BUGS.md`, updated `TOOL_REFERENCE.md` + `ARCHITECTURE.md` exist.
- [ ] Working tree is clean after the commit.
- [ ] Report contains commit SHA, pytest output, tool count, ruff output, and the file list.
- [ ] No references to other projects, no extra dependencies, no scope creep.

If anything on this list is missing, the task is NOT done. Report blockers, don't ship a half-finished rewrite.

---

## 9. Reference architecture — Loophole

**Read this before writing any code**: https://github.com/OthmanAdi/loophole

Specifically:

- Root `README.md` — pitch, map, install, prior art
- `packages/core/README.md` — the `LiveBridge` port, DTOs, path-id scheme, error model
- `packages/mcp/README.md` — the MCP server shape, 12 tools, resources, prompts
- `packages/extension/README.md` — the `.ablx` shell that hosts the server in Live

Loophole runs on the **Ableton Extensions SDK** (a Node.js host). Our project runs on **MIDI Remote Scripts** (a Python host). The transport and host differ; the architecture (port + tools + path-ids + one-undo-per-write + Zod-validated inputs + transport-agnostic server) does not. Adapt the shape to our Python host. **Do not copy code** — read the patterns, internalize them, and rewrite in idiomatic Python with FastMCP instead of the official MCP SDK.

Loophole keeps the SDK **out of `core` and `mcp`** — only the `extension` package imports the SDK. We do the same: only `AbletonMCPServer_RemoteScript/` imports Live's Python LOM; `ableton_mcp_server/` stays LOM-free.

---

**Last updated**: 2026-07-09, end-of-session handoff. The non-deterministic transport setter pattern (Category A) is the most important thing in this document — apply it to every transport-state write. The project is standalone — do not couple it to anything else.