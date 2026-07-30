# Expand to 125 Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 60 approved core Ableton capabilities without adding a third bridge or any Max for Live, MIDI CC, OSC, ElevenLabs, or dashboard dependency.

**Architecture:** Keep TCP as the main-thread/undo path and WebSocket as the official Extensions SDK path. Add domain model, MCP wrapper, and Remote Script/Extension handler modules incrementally; after every domain commit, catalog, request models, registered functions, and wire allowlists must have the same progressive count.

**Tech Stack:** Python 3.10+, FastMCP, Pydantic 2, Ableton Python LOM, Ableton Extensions SDK 1.0.0 beta, TypeScript, JSONL TCP, JSON-RPC WebSocket, pytest, Ruff, mypy strict.

**Verified SDK source:** `AbletonMCPServer_Extension/vendor/ableton-extensions-sdk-1.0.0-beta.0.tgz`, declaration `package/dist/index.d.cts`. It verifies `Track.insertDevice/deleteDevice/duplicateDevice`, `RackDevice.insertChain`, `DrumRack.chains`, `Simpler.replaceSample`, `Song.create/delete/duplicateScene`, `Song.delete/duplicateTrack`, `Track.arrangementClips`, `Track.deleteClip`, `AudioTrack.createAudioClip`, and `MidiTrack.createMidiClip`. It does not expose writable warp markers or chain delete/duplicate.

---

## Progressive count contract

| Completed task | Added | Total |
|---|---:|---:|
| Certified baseline | 0 | 65 |
| Session/transport | 10 | 75 |
| Tracks/mixer/routing | 11 | 86 |
| Scenes | 5 | 91 |
| Session clips/MIDI | 10 | 101 |
| Arrangement/time | 8 | 109 |
| Devices/racks/samples | 9 | 118 |
| Automation | 5 | 123 |
| Browser | 2 | 125 |

At each row, these six sets must be identical: catalog names, request-model
names, FastMCP listing, `PUBLIC_TOOL_NAMES`, `PUBLIC_TOOL_FUNCTIONS`, and the
union of local/composed/wire-routed tools.

## Common response rules

- Every write validates the full request before its first mutation.
- Every mutation returns requested values and observed values/indices.
- TCP mutations run in the existing undo wrapper and verify on a later Live UI
  tick when the property is observable.
- Extension mutations use `context.withinTransaction` and await every SDK
  promise before responding.
- Missing documented host methods produce `CAPABILITY_UNAVAILABLE`.
- Wrong object classes produce `WRONG_TYPE`; stale indexes/paths produce
  `STALE_REFERENCE`; multiple Browser/routing matches produce `AMBIGUOUS_MATCH`.
- Reads may reconnect once. Mutations never replay after ambiguous connection
  loss.

### Task 1: Create modular expansion seams without changing 65 behavior

**Files:**
- Create: `ableton_mcp_server/model_base.py`
- Create: `ableton_mcp_server/tool_models/__init__.py`
- Create: `ableton_mcp_server/tools/__init__.py`
- Create: `AbletonMCPServer_RemoteScript/_errors.py`
- Create: `AbletonMCPServer_RemoteScript/_handler_utils.py`
- Create: `AbletonMCPServer_RemoteScript/handlers/__init__.py`
- Modify: `ableton_mcp_server/models.py:1-20,616-690`
- Modify: `ableton_mcp_server/server.py:1350-1365`
- Modify: `AbletonMCPServer_RemoteScript/__init__.py:82-126,2050-2320`
- Create: `tests/test_expansion_seams.py`

- [ ] **Step 1: Write a failing no-behavior-change seam test**

```python
def test_empty_expansion_seams_preserve_certified_baseline() -> None:
    from ableton_mcp_server.catalog import TOOL_CATALOG
    from ableton_mcp_server.models import TOOL_REQUEST_MODELS
    from ableton_mcp_server.server import PUBLIC_TOOL_FUNCTIONS, PUBLIC_TOOL_NAMES
    from ableton_mcp_server.tool_models import EXPANDED_TOOL_REQUEST_MODELS
    from ableton_mcp_server.tools import EXPANDED_PUBLIC_TOOL_FUNCTIONS

    assert EXPANDED_TOOL_REQUEST_MODELS == {}
    assert EXPANDED_PUBLIC_TOOL_FUNCTIONS == ()
    assert len(TOOL_CATALOG) == len(TOOL_REQUEST_MODELS) == 65
    assert len(PUBLIC_TOOL_NAMES) == len(PUBLIC_TOOL_FUNCTIONS) == 65
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_expansion_seams.py -q`

Expected: expansion packages do not exist.

- [ ] **Step 3: Move only shared Pydantic primitives**

```python
# ableton_mcp_server/model_base.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeBeat = Annotated[float, Field(ge=0, le=100000)]
PositiveBeat = Annotated[float, Field(gt=0, le=100000)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Import these names from `models.py`; do not duplicate their definitions.
Initialize `EXPANDED_TOOL_REQUEST_MODELS: dict[str, type[RequestModel]] = {}` and
`EXPANDED_PUBLIC_TOOL_FUNCTIONS: tuple[Callable[..., object], ...] = ()` in the
new package initializers. Update the existing maps/tuples by expansion.

- [ ] **Step 4: Move Remote Script error classes and add generic generator dispatch**

Move `RemoteError`, `PlayheadNotMovedError`, and `CueSnappedToGridError` verbatim
to `_errors.py`, import/re-export them from `__init__.py`, and place new selector
helpers in `_handler_utils.py`:

```python
def track_by_kind(song: Any, kind: str, index: int) -> Any:
    collections = {
        "track": list(song.tracks),
        "return": list(song.return_tracks),
        "main": [song.master_track],
    }
    if kind not in collections or index < 0 or index >= len(collections[kind]):
        raise RemoteError(ERROR_STALE_REFERENCE, "%s track %s is unavailable" % (kind, index))
    return collections[kind][index]


def observed_parameter_write_steps(parameter: Any, value: float):
    parameter.value = value
    yield
    observed = float(parameter.value)
    if abs(observed - value) > 0.0001:
        raise RemoteError(ERROR_VERIFICATION_FAILED, "parameter readback differs")
    return observed
```

In generic command dispatch, detect a returned generator with
`inspect.isgenerator(result)` and `yield from` it. Merge
`EXPANDED_COMMAND_HANDLERS` from `handlers/__init__.py` into the existing handler
map. The expansion map is empty in this task.

- [ ] **Step 5: Run GREEN and the certified regression suite**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_expansion_seams.py tests\test_models.py tests\test_server_tools.py tests\test_remote_errors.py -q
.\.venv-win\Scripts\python.exe -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript tests\test_expansion_seams.py
.\.venv-win\Scripts\python.exe -m mypy --strict ableton_mcp_server
```

Expected: all pass with the count still exactly 65.

- [ ] **Step 6: Commit**

```powershell
git add ableton_mcp_server/model_base.py ableton_mcp_server/tool_models ableton_mcp_server/tools ableton_mcp_server/models.py ableton_mcp_server/server.py AbletonMCPServer_RemoteScript/_errors.py AbletonMCPServer_RemoteScript/_handler_utils.py AbletonMCPServer_RemoteScript/handlers AbletonMCPServer_RemoteScript/__init__.py tests/test_expansion_seams.py
git commit -m "refactor: add domain expansion seams"
```

### Task 2: Add 10 session and transport tools

**Files:**
- Create: `ableton_mcp_server/tool_models/session.py`
- Create: `ableton_mcp_server/tools/session.py`
- Create: `AbletonMCPServer_RemoteScript/handlers/session.py`
- Create: `tests/test_session_expansion.py`
- Modify: package initializers, `catalog.py`, `contracts.py`, `server.py`
- Regenerate: `AbletonMCPServer_RemoteScript/_contracts.py`

**Exact contracts:**

| Tool | Arguments | Result keys |
|---|---|---|
| `get_transport_state` | none | tempo, time, playing, metronome, record modes, punch, can_undo, can_redo |
| `set_metronome` | `enabled: bool` | metronome |
| `set_recording_state` | optional `arrangement_record`, `session_record`, `overdub`; at least one | requested/observed fields |
| `set_punch` | optional `punch_in`, `punch_out`, `count_in_duration: 0..3`; at least one | observed fields |
| `continue_playback` | none | is_playing, current_song_time |
| `tap_tempo` | none | tempo |
| `undo` | none | performed, can_undo, can_redo |
| `redo` | none | performed, can_undo, can_redo |
| `stop_all_clips` | none | stopped, playing_slot_indices |
| `re_enable_automation` | none | re_enabled |

- [ ] **Step 1: Write RED tests for models, readback, and unavailable methods**

Parameterize all ten names against the request-model map. Add focused handler
tests proving `set_recording_state` writes `record_mode`, `session_record`, and
`arrangement_overdub`; `set_punch` rejects an empty request before writing;
undo refuses when `can_undo` is false; and missing `re_enable_automation`
returns `CAPABILITY_UNAVAILABLE`.

```python
def test_recording_state_returns_observed_fields() -> None:
    result = execute_command(
        song, app, "set_recording_state",
        {"arrangement_record": True, "session_record": False, "overdub": True},
    )
    assert result["observed"] == {
        "arrangement_record": True,
        "session_record": False,
        "overdub": True,
    }
```

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_session_expansion.py -q`

Expected: commands/models are absent.

- [ ] **Step 3: Implement models, wrappers, and TCP handlers**

Use Pydantic `model_validator(mode="after")` for the two at-least-one-change
models. Handlers call only these verified Python LOM members:

```python
TRANSPORT_ATTRIBUTES = {
    "arrangement_record": "record_mode",
    "session_record": "session_record",
    "overdub": "arrangement_overdub",
    "punch_in": "punch_in",
    "punch_out": "punch_out",
    "count_in_duration": "count_in_duration",
}
```

Use the existing deferred boolean/numeric verification pattern. For method
commands, validate `callable(getattr(song, method, None))`, invoke once, yield
one UI tick, then return observed state. Wrappers call `_remote` with the exact
model dump and include full side-effect/example/edge-case docstrings.

- [ ] **Step 4: Register and verify progressive count 75**

Add reads to `READ_COMMANDS`, mutations to `ALLOWED_MUTATIONS`, update the
catalog and package maps/tuples, vendor contracts, then run:

```powershell
.\.venv-win\Scripts\python.exe scripts\vendor_contracts.py
.\.venv-win\Scripts\python.exe -m pytest tests\test_session_expansion.py tests\test_catalog.py tests\test_tool_registry.py tests\test_models.py -q
```

Expected: all pass; every count is exactly 75.

- [ ] **Step 5: Commit**

```powershell
git add contracts.py AbletonMCPServer_RemoteScript/_contracts.py AbletonMCPServer_RemoteScript/handlers/session.py ableton_mcp_server/tool_models/session.py ableton_mcp_server/tools/session.py ableton_mcp_server/tool_models/__init__.py ableton_mcp_server/tools/__init__.py ableton_mcp_server/catalog.py ableton_mcp_server/server.py tests/test_session_expansion.py
git commit -m "feat: add complete transport controls"
```

### Task 3: Add 11 track, mixer, and routing tools

**Files:**
- Create: `ableton_mcp_server/tool_models/tracks.py`
- Create: `ableton_mcp_server/tools/tracks.py`
- Create: `AbletonMCPServer_RemoteScript/handlers/tracks.py`
- Create: `tests/test_track_expansion.py`
- Modify/register the same catalog/contract/package files as Task 2

**Selector:** every tool accepts `track_kind: Literal["track", "return", "main"]`
and `track_index`; `main` requires index `0`. Structural tools narrow kinds as
shown below.

| Tool | Key arguments | Rules |
|---|---|---|
| `delete_track` | regular `track_index` | count decreases by one |
| `duplicate_track` | regular `track_index` | duplicate observed at index+1 |
| `create_return_track` | optional name | return count increases by one |
| `delete_return_track` | `return_index` | return count decreases by one |
| `get_mixer_state` | kind/index | parameter values, sends, mute/solo/arm where legal |
| `set_track_mixer` | kind/index; optional volume, pan, mute, solo, arm, crossfade_assign | validate all, then write/read back |
| `set_main_mixer` | optional volume, pan, crossfader, cue_volume | main only |
| `set_track_send` | kind/index, send_index, value | parameter bounds enforced |
| `set_track_monitoring` | regular index, `state: in|auto|off` | maps to 0/1/2 |
| `set_track_routing` | regular index; optional input/output type/channel | values must come from available routing reads |
| `get_playing_clips` | optional regular index | slot indices and clip names |

- [ ] **Step 1: Write RED tests**

Tests must recreate track proxies between count/readback, reject arming a return
or main track, reject an unavailable routing display name before any routing
write, apply routing types before channels, clamp no mixer values, and verify
send/main parameter readback.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_track_expansion.py -q`

Expected: missing commands/models.

- [ ] **Step 3: Implement structural handlers by collection delta/index**

Use `song.delete_track(index)`, `song.duplicate_track(index)`,
`song.create_return_track()`, and `song.delete_return_track(index)` only after
`callable` capability checks. Never use proxy `id()`. For routing, resolve exact
display names in this order:

```python
input_type -> output_type -> refreshed input_channel -> refreshed output_channel
```

If `0` or more than `1` match is found, raise `BAD_INPUT` or
`AMBIGUOUS_MATCH` respectively. Mixer values outside the Live parameter's
`min/max` fail validation; they are not silently clamped.

- [ ] **Step 4: Register and verify progressive count 86**

Run focused tests, vendor contracts, catalog/model/registry tests, Ruff, and
mypy. Expected count: 86 everywhere.

- [ ] **Step 5: Commit**

```powershell
git add contracts.py AbletonMCPServer_RemoteScript/_contracts.py AbletonMCPServer_RemoteScript/handlers/tracks.py ableton_mcp_server/tool_models/tracks.py ableton_mcp_server/tools/tracks.py ableton_mcp_server/tool_models/__init__.py ableton_mcp_server/tools/__init__.py ableton_mcp_server/catalog.py ableton_mcp_server/server.py tests/test_track_expansion.py tests/remote_fakes.py
git commit -m "feat: add track mixer and routing control"
```

### Task 4: Add 5 scene tools

**Files:** domain files named `scenes.py` in tool models, tools, Remote Script handlers, and `tests/test_scene_expansion.py`; modify catalog/contracts/initializers/server.

| Tool | Arguments | Verification |
|---|---|---|
| `create_scene` | `index=-1`, optional name | count +1, observed index/name |
| `delete_scene` | scene index | count -1 |
| `duplicate_scene` | scene index | duplicate at index+1 |
| `set_scene_properties` | index; optional name, color index 0..69, tempo 20..999, signature numerator 1..16, denominator 1/2/4/8/16, follow_action_0/1 0..9, probability 0..1, positive follow time, enabled, linked | full prevalidation, readback |
| `capture_and_insert_scene` | none | method capability, count +1 |

- [ ] **Step 1: Write RED tests**

Include reproxying scene collections, empty property request rejection, invalid
signature rejection before name/color writes, and `CAPABILITY_UNAVAILABLE` for
missing capture support.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_scene_expansion.py -q`

- [ ] **Step 3: Implement using Python LOM collection methods**

Use `create_scene(index)`, `delete_scene(index)`, `duplicate_scene(index)`, and
`capture_and_insert_scene()`. Set only host attributes proven by `hasattr`; if a
requested field is absent, fail before changing any other field.

- [ ] **Step 4: Register, verify count 91, and commit**

Expected: focused and invariant tests pass with exactly 91 tools.

Commit subject: `feat: add scene lifecycle and properties`.

### Task 5: Add 10 Session clip and MIDI editing tools

**Files:** domain files named `clips.py`; create `tests/test_clip_expansion.py`; modify catalog/contracts/initializers/server.

| Tool | Key arguments |
|---|---|
| `duplicate_session_clip` | source track/slot, target track/slot |
| `move_session_clip` | source track/slot, target track/slot |
| `stop_clip` | track/slot |
| `stop_track_clips` | track |
| `replace_clip_notes` | track/slot, complete note list |
| `remove_clip_notes` | track/slot, pitch/time rectangle |
| `transform_clip_notes` | track/slot; transpose -127..127, velocity scale/offset, time shift, duration scale, humanize amount and required seed |
| `quantize_clip_notes` | track/slot, Live quantization enum, amount 0..1 |
| `set_clip_loop_region` | track/slot, looping, loop_start, loop_end |
| `set_clip_launch` | track/slot; launch_mode, quantization, legato, follow_action_0/1 0..9, probability 0..1, positive follow time, enabled, linked, return_to_zero; at least one |

- [ ] **Step 1: Write RED tests**

Prove target slots must be empty, move does not delete source until duplication
is observed, audio clips return `WRONG_TYPE` for note tools, replacement
validates every new note before clearing old notes, humanization is deterministic
for the same seed, transformed pitch/velocity/time/duration stay in documented
bounds, and quantization invokes Live exactly once.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_clip_expansion.py -q`

- [ ] **Step 3: Implement atomic ordering and deterministic transforms**

Use `track.duplicate_clip_slot(source, target)` for same-track duplication; for
cross-track duplication, use the host's `duplicate_clip_to` only when callable,
otherwise return `CAPABILITY_UNAVAILABLE`. `move_session_clip` verifies the
target first, then deletes the source. Note transform uses
`random.Random(request.seed)` and constructs new `MidiNoteSpecification` values;
it never mutates a note object returned by Live.

Replacement order is:

```text
validate all notes -> capture old notes -> clear -> add new -> read back count
```

If add/readback fails, return `rolled_back:false` and the captured old-note
summary; do not claim automatic restoration.

- [ ] **Step 4: Register, verify count 101, and commit**

Run focused tests plus existing clip/transaction tests. Expected count: 101.

Commit subject: `feat: add deterministic Session clip editing`.

### Task 6: Add 8 Arrangement and time tools

**Files:** domain files named `arrangement.py`; create `tests/test_arrangement_expansion.py`; modify catalog/contracts/initializers/server.

| Tool | Key arguments/rules |
|---|---|
| `get_arrangement_clips` | track; stable per-request ordinal selectors |
| `get_arrangement_clip_info` | track, arrangement clip ordinal |
| `duplicate_clip_to_arrangement` | Session track/slot, start beat |
| `move_arrangement_clip` | track, ordinal, new start beat |
| `delete_arrangement_clip` | track, ordinal |
| `set_arrangement_clip_properties` | name/color/mute/loop/markers, full prevalidation |
| `insert_arrangement_time` | position, positive length; calls `insert_silence` |
| `delete_arrangement_time` | start, end with end>start; calls `delete_time(start, length)` |

- [ ] **Step 1: Write RED tests**

Test reproxying `arrangement_clips`, stale ordinals, exact `delete_time` length,
single-call duplication, observed move, and validation before a destructive time
edit. Assert Arrangement time tools are cataloged `DESTRUCTIVE` and excluded
from default acceptance profiles.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_arrangement_expansion.py -q`

- [ ] **Step 3: Implement with capability checks and one undo step**

Use `song.duplicate_clip_to_arrangement(clip, start)`, writable
`clip.start_time`, `track.delete_clip(clip)`, `song.insert_silence(position,
length)`, and `song.delete_time(start, length)` only after callable/attribute
checks. Re-enumerate and return the post-edit ordinal/path after every mutation.

- [ ] **Step 4: Register, verify count 109, and commit**

Expected count: 109. Commit subject:
`feat: add guarded Arrangement editing`.

### Task 7: Add 9 device, rack, and sample tools

**Files:**
- Create: `ableton_mcp_server/tool_models/devices.py`
- Create: `ableton_mcp_server/tools/devices.py`
- Create: `AbletonMCPServer_RemoteScript/handlers/devices.py`
- Create: `AbletonMCPServer_Extension/src/handlers/devices.ts`
- Create: `AbletonMCPServer_Extension/src/rpc.ts`
- Create: `tests/test_device_expansion.py`
- Modify: `AbletonMCPServer_Extension/src/index.ts`, catalog/contracts/initializers/server

| Tool | Route | Contract |
|---|---|---|
| `delete_device` | WS | track kind/index, device index; await count -1 |
| `duplicate_device` | WS | track kind/index, device index; returned duplicate index |
| `set_device_enabled` | TCP | exact `Device On` parameter, boolean readback |
| `get_rack_chains` | WS | positive RackDevice cast, chain/device/mixer summary |
| `create_rack_chain` | WS | rack selector, insertion index; `insertChain` |
| `delete_rack_chain` | TCP | capability-gated `delete_chain(index)` |
| `duplicate_rack_chain` | TCP | capability-gated `duplicate_chain(index)` |
| `get_drum_pad` | TCP | Drum Rack selector and MIDI note 0..127 |
| `replace_simpler_sample` | WS | Simpler selector, absolute existing audio path |

- [ ] **Step 1: Write RED Python and TypeScript contract tests**

Assert SDK CRUD is awaited, wrong classes produce `WRONG_TYPE`, index counts are
read after mutation, chain delete/duplicate never use nonexistent SDK methods,
and Simpler returns the observed sample path. Add a TypeScript `node:test` test
with fake SDK objects and a Python WS routing test.

- [ ] **Step 2: Run RED**

Run Python focused tests and `npm test` after adding a package script
`"test": "tsx --test src/**/*.test.ts"`. Expected: handlers/routes absent.

- [ ] **Step 3: Split the Extension dispatcher and implement verified SDK APIs**

Create a typed method map:

```typescript
export type RpcHandler = (params: Record<string, unknown>) => Promise<unknown>;

export const DEVICE_HANDLERS: Record<string, RpcHandler> = {
  delete_device: handleDeleteDevice,
  duplicate_device: handleDuplicateDevice,
  get_rack_chains: handleGetRackChains,
  create_rack_chain: handleCreateRackChain,
  replace_simpler_sample: handleReplaceSimplerSample,
};
```

Resolve SDK subclasses through `context.getObjectFromHandle(handle, Class)` and
convert failed casts to `RpcDomainError("WRONG_TYPE", ...)`. Bind the
WebSocketServer explicitly to `{ host: "127.0.0.1", port: 9889 }` while touching
the dispatcher.

- [ ] **Step 4: Implement TCP-only device/rack fallbacks**

`set_device_enabled` resolves the exact parameter whose normalized name is
`device on`; rack chain delete/duplicate call only positively discovered host
methods and otherwise raise `CAPABILITY_UNAVAILABLE`. `get_drum_pad` uses
`device.drum_pads[note]` and returns mute/solo/name/chains when exposed.

- [ ] **Step 5: Register, verify count 118, build, and commit**

Run Python tests, npm test/build, catalog/registry checks. Expected count: 118.

Commit subject: `feat: add device rack and Simpler control`.

### Task 8: Add 5 automation tools

**Files:** domain files named `automation.py`; create `tests/test_automation_expansion.py`; modify catalog/contracts/initializers/server.

| Tool | Contract |
|---|---|
| `get_clip_automation` | track index, clip index, typed parameter selector, `sample_count: 2..2048 = 128`; sampled `{time,value}` points |
| `clear_clip_automation` | track index, clip index, typed parameter selector; clear exact envelope and verify absent/flat |
| `list_automated_parameters` | track index, clip index; mixer/device parameter paths with envelopes |
| `create_arrangement_automation` | track index, typed parameter selector, non-empty sorted `{time,value}` points all within one real Arrangement clip |
| `clear_arrangement_automation` | track index, typed parameter selector, nonnegative start, end greater than start, both within one real Arrangement clip |

- [ ] **Step 1: Write RED tests**

Cover mixer aliases and exact device paths, sorted points, disabled/out-of-range
parameters, no Arrangement clip, a range spanning two clips, missing envelope
APIs, and readback. No test may substitute a Session clip when Arrangement was
requested.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_automation_expansion.py -q`

- [ ] **Step 3: Implement against real clip envelopes only**

Reuse the existing `_automation_parameter` resolution. Select the Arrangement
clip whose `[start_time, end_time)` contains every point/range. Use
`automation_envelope_for_parameter`/`create_automation_envelope` only when the
host exposes it; otherwise return `CAPABILITY_UNAVAILABLE`. Clamp nothing:
reject a point outside parameter bounds before clearing/inserting.

- [ ] **Step 4: Register, verify count 123, and commit**

Run new and existing automation tests plus invariants. Expected count: 123.

Commit subject: `feat: add readable and Arrangement automation`.

### Task 9: Add 2 Browser lifecycle tools

**Files:** domain files named `browser.py`; create `tests/test_browser_expansion.py`; modify catalog/contracts/initializers/server.

| Tool | Arguments | Behavior |
|---|---|---|
| `load_browser_item` | exact URI, target track kind/index, optional device index | resolve bounded exact URI, reject ambiguity, select explicit target, load once, verify device/clip delta |
| `preview_browser_item` | `action: start|stop`, URI required for start | `preview_item(item)` or `stop_preview()` exactly once |

- [ ] **Step 1: Write RED tests**

Use a Browser tree with duplicate display names and distinct URIs. Prove loading
never chooses by name, preview stop needs no URI, missing host methods are
`CAPABILITY_UNAVAILABLE`, and a load acknowledgement without target delta is
`VERIFICATION_FAILED`.

- [ ] **Step 2: Run RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests\test_browser_expansion.py -q`

- [ ] **Step 3: Implement bounded exact-URI resolution**

Reuse Task 5 of Slice 1 traversal keys and the same depth/node budgets. Before
`browser.load_item`, set only the explicitly requested selected track/device.
Capture devices and clip slots before/after and report the observed delta.
Preview start resolves the URI; preview stop calls `browser.stop_preview()`.

- [ ] **Step 4: Register and verify final count 125**

Run vendor, focused, full catalog/model/registry tests. Expected: exactly 125 in
all six surfaces from the progressive count contract.

- [ ] **Step 5: Commit**

Commit subject: `feat: add exact Browser load and preview lifecycle`.

### Task 10: Finish modularization, full gates, and Live capability profiles

**Files:**
- Create: `ableton_mcp_server/tools/baseline.py` only if a wrapper has no natural domain module
- Modify: `ableton_mcp_server/server.py`
- Modify: `ableton_mcp_server/acceptance.py`
- Modify: `ableton_mcp_server/certification.py`
- Modify: `ableton_mcp_server/cli.py`
- Modify: `tests/test_acceptance.py`, `tests/test_server_tools.py`

- [ ] **Step 1: Write a failing small-composition-root test**

Parse `server.py` with `ast` and assert it defines only `main` plus compatibility
re-exports, contains no `@mcp.tool` decorators, and is under 250 physical lines.
Assert every function in `PUBLIC_TOOL_FUNCTIONS` has exactly one catalog entry,
request model, registered MCP tool, and contract route/local classification.

- [ ] **Step 2: Run RED**

Expected: current 1,300+ line server violates the composition-root assertion.

- [ ] **Step 3: Move the original 65 wrappers by domain without rewriting behavior**

Use the same top-level function plus `PUBLIC_FUNCTIONS` tuple pattern as the new
modules. Domain ownership is:

```text
session: session/transport/lifecycle/cues
tracks: track reads/creation/rename/routing/fade
scenes: scene reads/fire
clips: clip reads/mutations/MIDI/composition diagnostics
devices: device/parameter/warp/load
diagnostics: bridge/log/control-surface/snapshot/diff/batch
developer: scaffold/build
analysis: four offline analysis wrappers
```

`server.py` imports domain `register_all(mcp)`, re-exports public functions for
one compatibility cycle, assembles `PUBLIC_TOOL_FUNCTIONS`, and calls `mcp.run()`.
Update test patch targets to the module that owns the wrapper; do not retain two
registered copies.

- [ ] **Step 4: Add acceptance profiles and fixture cleanup**

Profiles are `read`, `session`, `mixer`, `arrangement`, `device`, `browser`, and
`destructive`. Each uses names prefixed `__MCP_ACCEPTANCE__`, records post-write
readback, and independently verifies cleanup. Arrangement time delete and
`quit_ableton` require `--profile destructive` plus dedicated flags.

If cleanup fails, set overall status `failed`, list exact selectors, and do not
continue to another mutating profile.

- [ ] **Step 5: Run all automated gates**

```powershell
$py = ".\.venv-win\Scripts\python.exe"
& $py scripts\vendor_contracts.py
& $py -m pytest -q --tb=line
& $py scripts\coverage_check.py
& $py -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests
& $py -m mypy --strict ableton_mcp_server
Push-Location AbletonMCPServer_Extension
npm test
npm run build:prod
npm audit --audit-level=high
Pop-Location
git diff --check
```

Expected: all pass; count 125; no generated-contract drift.

- [ ] **Step 6: Reinstall and run guarded Live profiles**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
.\.venv-win\Scripts\ableton-mcp.exe acceptance `
  --confirm-project-name TESTE_CODEX `
  --profile read --profile session --profile mixer `
  --profile arrangement --profile device --profile browser --json
```

Expected: all non-destructive profiles pass, every exercised mutation has
observed readback, and cleanup reports no leftover acceptance object.

- [ ] **Step 7: Commit**

Commit subject: `refactor: complete modular 125-tool surface`.

## Self-Review

Spec coverage: Tasks 2–9 implement the exact 60 approved names by domain; Task 1
creates safe module seams; Task 10 satisfies composition-root, certification,
cleanup, and full-gate requirements.

Execution Consistency Audit evidence:

- PASS Test/implementation trace: each domain table defines arguments/results and each RED step names the observable handler behavior satisfied in the matching implementation step.
- PASS Per-task command executability: progressive tests run only after that task creates/imports its domain modules; the final CLI profiles are added before invocation.
- PASS File usage audit: every model module feeds the expanded model map, every tool module feeds registration/function tuples, and every handler module feeds the Remote Script or Extension dispatcher.
- PASS Spec lifecycle audit: send/readback/cleanup order is explicit; mutation connection loss never retries; move operations delete sources only after target observation.
- PASS Time source audit: no persistent timestamp is introduced; beat positions are Live beat-time floats, while certification timestamps remain outside this slice.
- PASS State scope audit: transform RNG is per request; Browser traversal state is per request; Extension context/server remain process-lifetime singletons already owned by the extension runtime.
- PASS Environment audit: Extension server is explicitly bound to desktop-only `127.0.0.1:9889`; TCP remains `127.0.0.1:9888`.
- N/A Browser event audit: Browser tools address Ableton content items, not web events.
- PASS Lint/import audit: Python snippets use 3.10-compatible syntax and domain modules run Ruff/mypy; TypeScript APIs come from the vendored declarations and run typecheck/tests/build.
- PASS Non-obvious API audit: official Extension calls are listed from the vendored `.d.cts`; Python-only methods are capability-checked and return `CAPABILITY_UNAVAILABLE` rather than being assumed.
