# Implementation Specs — Detailed designs for the v0.5.0 set-lifecycle and mix-analysis curated list

**Companion to:** `prompts/REQUEST-2026-07-12-borrow-set-lifecycle-and-mix-analysis.md`
**Author:** Worm (via Broc, deep-dive 2026-07-12)
**Status:** DESIGN — not implemented. Implementing agent reads, doesn't rewrite.

---

## How to use this file

This is **auxiliary spec material** for the implementing agent. The REQUEST.md is the contract; this file is the engineering handbook. Every entry has:

- **Source attribution** (commit SHA at time of reading + path within repo)
- **Their signature** (verbatim, so we know what they meant)
- **Our proposed signature** (in our snake_case + Pydantic + `@mcp.tool` style)
- **Pydantic model** (with validators when required)
- **Remote Script handler sketch** (Python generator pattern we use today)
- **Contract changes** (`contracts.py` allowlist + work-units + vendoring)
- **Tests required**
- **Risks specific to that feature**

If something here disagrees with REQUEST.md, REQUEST.md wins. If something here is missing, the implementing agent decides — and notes the decision in the PR.

---

## A. The dispatch pattern we already have

For reference — every new lifecycle/fade handler must follow this pattern. Code is in `AbletonMCPServer_RemoteScript/__init__.py`:

```python
def _dispatch_command_steps(song, application, normalized, params, undo_target):
    if normalized == "run_batch":
        return (yield from _run_batch_steps(song, application, params, undo_target))
    if normalized == "create_cue_point":
        return (yield from _create_cue_point_steps(song, params))
    # ... ~50 entries ...
```

**Handlers are SYNC functions** or **generator functions**, both with signature `(song, _application, params) -> dict` for sync, `(song, _application, params) -> Generator[None, None, dict]` for generator-style. Deferred verification is encapsulated in `_verified_*_steps` helpers and the `yield` keyword inside generators.

Sync example (existing `cmd_set_parameter_value` shape):

```python
def _set_parameter_value_steps(song, params):
    # ... validate, then write+readback with one yield ...
    yield
    return {"target": expected, "value": ..., "is_quantized": False}
```

Generator example (existing `start_playback` shape):

```python
if normalized == "start_playback":
    return (
        yield from _verified_boolean_steps(
            song,
            attribute="is_playing",
            expected=True,
            setter=song.start_playing,
            result_key="is_playing",
        )
    )
```

**Available reusable helpers** (do not reimplement):

| helper | what | reuse for |
|---|---|---|
| `_safe(getter, default)` | swallows `AttributeError`/`RuntimeError`/`TypeError` | attribute reads that may not exist in older Live |
| `_required(params, name)` | missing-key → `ERROR_INVALID_PARAMS` | all new commands |
| `_integer_param(params, name, minimum=0)` | type-checked int, ≥ minimum | all new commands |
| `_float_param(params, name, minimum, maximum=None, strictly_positive=False)` | `NaN`/inf → `ERROR_BAD_INPUT`, finite check, range check | all new commands |
| `_string_param(params, name)` | non-empty, stripped | all new commands |
| `_resolve_track_id(song, path_id)` | `(index, track)` tuple by session-local path-id | track commands |
| `_begin_undo(target)` / `_end_undo(target)` | raises `ERROR_LIVE_UNAVAILABLE` if host doesn't expose | already wrapped by `_command_steps` |

**Undo is automatic** when a command is in `ALLOWED_MUTATIONS`. `_command_steps` calls `_begin_undo(target)` before dispatch and `_end_undo(target)` in `finally`. Do **not** manually open/close undo in your handler — let the framework handle it.

**Existing `cmd_*` shape (canonical template):**

```python
def cmd_get_session_info(song, _application, _params) -> dict[str, Any]:
    return {
        "tempo": float(song.tempo),
        "signature_numerator": song.signature_numerator,
        "signature_denominator": song.signature_denominator,
        "is_playing": bool(_safe(lambda: song.is_playing, False)),
        "current_song_time": float(_safe(lambda: song.current_song_time, 0.0)),
    }
```

Three of the new commands (`lifecycle_status`, `save_set`, `create_audio_track`) fit this template as-is, with the small extension that the lifecycle pair returns structured GUI-workflow fallbacks instead of raising. `quit_ableton` is generator-style because it schedules a future tick. `live_fade` is the first generator that **deliberately blocks** the Live main thread for up to 60 seconds, requires new `LIVE_FADE_*` module constants, and requires `COMMAND_TIMEOUT_OVERRIDES["live_fade"] = 60.0`.

**Then in `server.py`:**

```python
@mcp.tool()
def save_set(require_api: bool = False) -> Any:
    return _remote("save_set", models.SaveSetRequest(require_api=require_api))
```

And in `PUBLIC_TOOL_NAMES`, and `models.py` (Pydantic). Every new tool follows this shape. Mechanical.

**For the four analysis tools**, the pattern is different — no bridge, no Remote Script, no Live. Each tool calls into `ableton_mcp_server.analysis.audio` and wraps the dict return with `_explicit_json_result`. The Pydantic models live in `models.py` to validate path arguments before they hit the audio module.

---

## B. Features in scope (v0.5.0 curated list, in detail)

---

### B1. `lifecycle_status()` — ML-1

**Source:** `mlmil/Ableton-Live-MCP-ULTRA-v2` @ main (commit `9469872`), `Ableton_Live_MCP/bridge.py:856` (`_rpc_lifecycle_status`), with upstream origin at `bschoepke/ableton-live-mcp`.

**Their signature (verbatim):**

```python
def _rpc_lifecycle_status(self, _params):
    status = self._lifecycle_api_status()
    status["gui_workflow"] = GUI_LIFECYCLE_WORKFLOW
    return status
```

Where `_lifecycle_api_status` builds `song_save_attrs`, `app_lifecycle_attrs`, `song_save_available`, `app_quit_available` from the Live Song and Application objects.

**Our signature (proposed — sync, follows `cmd_get_session_info` template):**

```python
@mcp.tool()
def lifecycle_status() -> Any:
    """Read Live save/quit API availability and return a GUI-workflow fallback.

    Side effects: none.
    Example: ``lifecycle_status()`` reports ``song_save_available`` and ``app_quit_available``.
    Edge cases: missing Live APIs degrade to ``False`` flags; never raises.
    """
    return _remote("lifecycle_status", models.GetLifecycleStatusRequest())
```

**Pydantic model:**

```python
class GetLifecycleStatusRequest(EmptyRequest):
    pass
```

**Remote Script handler (sync `cmd_*` shape):**

```python
GUI_LIFECYCLE_WORKFLOW = {
    "save": [
        "Open the File menu in the Live window.",
        "Click 'Save Live Set'. If the menu item is disabled, the set is already saved.",
    ],
    "quit": [
        "Save first through the File menu if the option is enabled.",
        "Open the Live application menu and click 'Quit Live'.",
    ],
    "notes": [
        "Locked or asleep displays block automated GUI workflows.",
    ],
}


def cmd_lifecycle_status(song, application, _params):
    return {
        "song_save_attrs": [name for name in ("save",) if hasattr(song, name)],
        "app_lifecycle_attrs": [name for name in ("quit",) if hasattr(application, name)],
        "song_save_available": callable(getattr(song, "save", None)),
        "app_quit_available": callable(getattr(application, "quit", None)),
        "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
    }
```

**Why no deferred verification:** read-only attribute probe. No LOM side effects. We deliberately keep this sync.

**Contract changes:**

- Add `"lifecycle_status"` to `READ_COMMANDS` (not `ALLOWED_MUTATIONS` — it has zero side effects).
- Re-run `scripts/vendor_contracts.py`.
- Register `cmd_lifecycle_status` in the dispatch table; bind it as a sync branch in `_dispatch_command_steps`.

**Tests required:**

- `tests/test_lifecycle_v050.py::test_lifecycle_status_reports_save_availability` — fake Live with both `save` and `quit` callable → `True` flags.
- `tests/test_lifecycle_v050.py::test_lifecycle_status_reports_missing_quit` — fake Live with `save` only → `app_quit_available: False`.
- `tests/test_lifecycle_v050.py::test_lifecycle_status_returns_gui_workflow` — `gui_workflow` has both `save` and `quit` keys.
- `tests/test_tool_registry.py` — count 57.

**Risks specific:**

- The upstream definition of `gui_workflow` is built around a macOS AppleScript-coupled GUI workflow (tested in their notes). Our WSL↔Windows setup **cannot** automate GUI clicks, so the GUI-workflow payload is informational only. Document this in the tool docstring.
- The constant `GUI_LIFECYCLE_WORKFLOW` belongs to the Remote Script module-level scope so it is part of the runtime identity payload.

---

### B2. `save_set(require_api: bool = False)` — ML-2

**Source:** `mlmil/Ableton-Live-MCP-ULTRA-v2` @ `9469872`, `Ableton_Live_MCP/bridge.py:861` (`_rpc_save_set`).

**Their signature (verbatim):**

```python
def _rpc_save_set(self, params):
    song = self.song()
    save = getattr(song, "save", None)
    if not callable(save):
        if params.get("require_api"):
            raise RuntimeError("Live Song object does not expose save(); use the GUI save workflow")
        return {
            "saved": False,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW["save"],
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    result = save()
    return {"saved": True, "api_available": True, "result": result}
```

**Our signature (proposed — sync, follows `cmd_*` template):**

```python
@mcp.tool()
def save_set(require_api: bool = False) -> Any:
    """Save the Live Set via Song.save() when exposed, otherwise return a GUI workflow.

    Side effects: invokes Song.save() in one undo step when available.
    Example: ``save_set(require_api=True)`` raises when the API is missing.
    Edge cases: missing API returns a structured GUI workflow response.
    """
    return _remote("save_set", models.SaveSetRequest(require_api=require_api))
```

**Pydantic model:**

```python
class SaveSetRequest(RequestModel):
    require_api: bool = False
```

**Remote Script handler (sync `cmd_*` shape):**

```python
def cmd_save_set(song, _application, params):
    save = getattr(song, "save", None)
    if not callable(save):
        if params.get("require_api"):
            raise RemoteError(
                "BAD_INPUT",
                "Live Song object does not expose save(); use the GUI save workflow",
            )
        return {
            "saved": False,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW["save"],
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    result = save()
    return {"saved": True, "api_available": True, "result": result}
```

**Why no deferred verification:** `Song.save()` is a void op. The next MCP round-trip pays the 1-tick cost. If real-world latency matters, the implementing agent may wrap as a generator and yield once — see the generator-variant pattern used for `clear_clip_notes`.

**Contract changes:**

- Add `"save_set"` to `ALLOWED_MUTATIONS` (it can be batched through `run_batch`).
- Re-run `scripts/vendor_contracts.py`.
- Register `cmd_save_set` in the dispatch table.

**Tests required:**

- `test_save_set_uses_song_save_when_available` — fake Live with callable `save` → handler invokes it; response has `saved: True`.
- `test_save_set_returns_gui_workflow_when_save_missing` — fake Live without `save`; response has `saved: False`, `api_available: False`, `gui_workflow` present.
- `test_save_set_raises_when_require_api_true_and_save_missing` — fake Live without `save`, `require_api: True` → `BAD_INPUT`.
- `tests/test_tool_registry.py` — count 58.

**Risks specific:**

- `Song.save()` triggers a synchronous disk write on the Live main thread. In large Sets this may exceed the default 20-second RPC timeout. The handler returns `{"saved": True, ...}` regardless. If the Live main thread crashes during save, the caller receives a `BridgeError`. Mitigation: the `require_api: True` flag is the agent's opt-in to fail fast when the API is missing; do not invent a different opt-in.
- `runtime`-host variation: `Song.save` may exist but raise `Live.LimitationError` if the Set is read-only. Document as known edge case; let the caller observe the bridge error.

---

### B3. `quit_ableton(save, force_without_save, quit_delay_ticks)` — ML-3

**Source:** `mlmil/Ableton-Live-MCP-ULTRA-v2` @ `9469872`, `Ableton_Live_MCP/bridge.py:876` (`_rpc_quit_ableton`).

**Their signature (verbatim):**

```python
def _rpc_quit_ableton(self, params):
    app = Live.Application.get_application()
    save_first = params.get("save", True)
    saved = None
    if save_first:
        save_result = self._rpc_save_set({})
        saved = bool(save_result.get("saved"))
        if not saved and not params.get("force_without_save"):
            return {
                "quit_requested": False,
                "saved_first": False,
                "reason": "save API unavailable; ...",
                "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
            }
    quit_fn = getattr(app, "quit", None)
    if not callable(quit_fn):
        return {
            "quit_requested": False,
            "saved_first": saved,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW["quit"],
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    delay = int(params.get("quit_delay_ticks") or 2)
    self.schedule_message(max(1, delay), quit_fn)
    return {"quit_requested": True, "saved_first": saved, "api_available": True, "scheduled": True}
```

**Our signature (proposed — generator-style because it schedules a future tick):**

```python
@mcp.tool()
def quit_ableton(
    save: bool = True,
    force_without_save: bool = False,
    quit_delay_ticks: int = 2,
) -> Any:
    """Save the Live Set (when requested) then schedule Application.quit after a small UI delay.

    Side effects: invokes Song.save() and schedules Application.quit.
    Example: ``quit_ableton(quit_delay_ticks=5)`` waits five UI ticks.
    Edge cases: missing APIs return a structured GUI workflow refusal.
    """
    return _remote(
        "quit_ableton",
        models.QuitAbletonRequest(
            save=save,
            force_without_save=force_without_save,
            quit_delay_ticks=quit_delay_ticks,
        ),
    )
```

**Pydantic model:**

```python
class QuitAbletonRequest(RequestModel):
    save: bool = True
    force_without_save: bool = False
    quit_delay_ticks: Annotated[int, Field(ge=1, le=120)] = 2
```

**Remote Script handler (generator-style; uses `schedule_message`):**

```python
def quit_ableton_steps(song, application, control_surface, params):
    save_first = bool(params.get("save", True))
    saved = None
    if save_first:
        save_result = cmd_save_set(song, application, {})
        saved = bool(save_result.get("saved"))
        if not saved and not params.get("force_without_save"):
            return {
                "quit_requested": False,
                "saved_first": False,
                "reason": "save API unavailable; pass force_without_save:true to quit anyway or use the GUI workflow",
                "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
            }
    quit_fn = getattr(application, "quit", None)
    if not callable(quit_fn):
        return {
            "quit_requested": False,
            "saved_first": saved,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW["quit"],
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    delay = int(params.get("quit_delay_ticks") or 2)
    control_surface.schedule_message(max(1, delay), quit_fn)
    return {
        "quit_requested": True,
        "saved_first": saved,
        "api_available": True,
        "scheduled": True,
    }
```

The dispatch branch is:

```python
if normalized == "quit_ableton":
    return quit_ableton_steps(song, application, _resolve_undo_target(None), params)
```

**Why generator-style:** `schedule_message` lives on the ControlSurface. Wrapping in a generator matches the deferred-mutation convention used by `run_batch`. The handler also yields once between the save and the schedule so the `Song.save()` UI tick commits before `Application.quit` is scheduled.

**Contract changes:**

- Add `"quit_ableton"` to `ALLOWED_MUTATIONS` (it can be batched).
- Re-run `scripts/vendor_contracts.py`.
- Register `quit_ableton_steps` in the dispatch table.

**Tests required:**

- `test_quit_ableton_saves_first_then_schedules_quit` — both `save` and `quit` callable; assert both are invoked exactly once; assert `quit_requested: True` and `scheduled: True`.
- `test_quit_ableton_refuses_when_save_unavailable_and_force_false` — fake Live without `save`; default `force_without_save: False` → handler returns the structured refusal including `gui_workflow`.
- `test_quit_ableton_quits_when_save_unavailable_and_force_true` — fake Live without `save`; `force_without_save: True` → handler schedules `quit` regardless.
- `test_quit_ableton_refuses_when_quit_unavailable` — fake Live without `quit`; handler returns the `api_available: False` GUI workflow.
- `tests/test_tool_registry.py` — count 59.

**Risks specific:**

- The handler **deliberately schedules a process-exit**. There is no rollback. The MCP layer returns **before** Live actually quits, which is what we want — but a failed RPC response must not delay the schedule. We dispatch through the existing `_command_steps` so `_begin_undo` and `_end_undo` are still called. Note: an undo step is opened even though this command opens no Set edit; the cleanup cost is acceptable.
- `Application.quit` is undefined behavior when the bridge socket is still open. We rely on Live closing the socket after the schedule fires. Document that the MCP client may receive a connection-reset on its next request.

---

### B4. `live_fade(...)` — ML-4

**Source:** `mlmil/Ableton-Live-MCP-ULTRA-v2` @ `9469872`, `Ableton_Live_MCP/bridge.py:983` (`_rpc_fade`).

**Their signature (verbatim):**

```python
def _rpc_fade(self, params):
    track = self._resolve_track_param(params)
    mixer = getattr(track, "mixer_device", None)
    param = getattr(mixer, "volume", None)
    if param is None:
        raise RuntimeError("Track has no mixer_device.volume parameter")
    if params.get("target_value") is not None:
        target = float(params["target_value"])
    elif params.get("target_percent") is not None:
        percent = float(params["target_percent"])
        if percent < 0.0:
            raise ValueError("target_percent must be >= 0")
        if percent > 100.0 and not params.get("allow_over_unity"):
            raise ValueError("target_percent above 100 (unity) requires allow_over_unity:true")
        target = (percent / 100.0) * FADE_UNITY_VALUE
    else:
        raise ValueError("Provide target_percent or target_value")
    minimum = float(getattr(param, "min", 0.0))
    maximum = float(getattr(param, "max", 1.0))
    target = min(max(target, minimum), maximum)
    duration = float(params.get("duration") if params.get("duration") is not None else 10.0)
    if duration < 0.0 or duration > FADE_MAX_DURATION:
        raise ValueError("duration must be between 0 and %s seconds" % FADE_MAX_DURATION)
    steps = int(params.get("steps") if params.get("steps") is not None else FADE_DEFAULT_STEPS)
    if steps < 1:
        raise ValueError("steps must be >= 1")
    curve = params.get("curve") or "smoothstep"
    if curve not in ("smoothstep", "linear"):
        raise ValueError("curve must be smoothstep or linear")
    start = float(param.value)
    sleep_per_step = duration / steps
    for step in range(1, steps + 1):
        t = step / float(steps)
        shaped = t * t * (3.0 - 2.0 * t) if curve == "smoothstep" else t
        param.value = start + (target - start) * shaped
        if sleep_per_step > 0:
            time.sleep(sleep_per_step)
    final_value = float(param.value)
    return {
        "track": getattr(track, "name", ""),
        "curve": curve,
        "duration": duration,
        "steps": steps,
        "start_value": start,
        "target_value": target,
        "final_value": final_value,
        "final_percent": round(final_value / FADE_UNITY_VALUE * 100.0, 3),
    }
```

**Our signature (proposed — generator-style because it deliberately blocks Live's main thread):**

```python
@mcp.tool()
def live_fade(
    track_index: int,
    target_percent: float | None = None,
    target_value: float | None = None,
    duration: float = 10.0,
    steps: int = 40,
    curve: Literal["smoothstep", "linear"] = "smoothstep",
    allow_over_unity: bool = False,
) -> Any:
    """Step a track's mixer volume through a smoothstep or linear fade over ``duration`` seconds.

    Side effects: blocks the Live main thread for up to ``duration`` seconds plus steps.
    Example: ``live_fade(track_index=0, target_percent=0)`` ramps the first track to silence.
    Edge cases: rejects duration above 60 seconds and percent above 100 without ``allow_over_unity``.
    """
    return _remote(
        "live_fade",
        models.LiveFadeRequest(
            track_index=track_index,
            target_percent=target_percent,
            target_value=target_value,
            duration=duration,
            steps=steps,
            curve=curve,
            allow_over_unity=allow_over_unity,
        ),
    )
```

**Pydantic model (with `model_validator` for exactly-one target):**

```python
LIVE_FADE_MAX_DURATION = 60.0
LIVE_FADE_DEFAULT_STEPS = 40


class LiveFadeRequest(RequestModel):
    track_index: NonNegativeInt
    target_percent: Annotated[float, Field(ge=0, le=200)] | None = None
    target_value: Annotated[float, Field(ge=0, le=1)] | None = None
    duration: Annotated[float, Field(ge=0, le=LIVE_FADE_MAX_DURATION)] = 10.0
    steps: Annotated[int, Field(ge=1, le=500)] = LIVE_FADE_DEFAULT_STEPS
    curve: Literal["smoothstep", "linear"] = "smoothstep"
    allow_over_unity: bool = False

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "LiveFadeRequest":
        if (self.target_percent is None) == (self.target_value is None):
            raise ValueError("Provide exactly one of target_percent or target_value")
        return self
```

**Remote Script generator (module-level constants live alongside):**

```python
LIVE_FADE_UNITY_VALUE = 0.8500000238418579
LIVE_FADE_MAX_DURATION = 60.0
LIVE_FADE_DEFAULT_STEPS = 40


def live_fade_steps(song, _application, params):
    track_index = _required(params, "track_index")
    track = song.tracks[int(track_index)]
    mixer = getattr(track, "mixer_device", None)
    if mixer is None:
        raise RemoteError("WRONG_TYPE", "Track has no mixer_device")
    param = getattr(mixer, "volume", None)
    if param is None:
        raise RemoteError("WRONG_TYPE", "Track has no mixer_device.volume parameter")
    if params.get("target_value") is not None:
        target = float(params["target_value"])
    elif params.get("target_percent") is not None:
        percent = float(params["target_percent"])
        if percent < 0.0:
            raise RemoteError("INVALID_PARAMS", "target_percent must be >= 0")
        if percent > 100.0 and not params.get("allow_over_unity"):
            raise RemoteError(
                "INVALID_PARAMS",
                "target_percent above 100 (unity) requires allow_over_unity:true",
            )
        target = (percent / 100.0) * LIVE_FADE_UNITY_VALUE
    else:
        raise RemoteError("INVALID_PARAMS", "Provide target_percent or target_value")
    minimum = float(getattr(param, "min", 0.0))
    maximum = float(getattr(param, "max", 1.0))
    target = max(minimum, min(target, maximum))
    duration = float(params.get("duration") if params.get("duration") is not None else 10.0)
    if duration < 0.0 or duration > LIVE_FADE_MAX_DURATION:
        raise RemoteError(
            "INVALID_PARAMS",
            f"duration must be between 0 and {LIVE_FADE_MAX_DURATION} seconds",
        )
    steps = int(params.get("steps") if params.get("steps") is not None else LIVE_FADE_DEFAULT_STEPS)
    if steps < 1:
        raise RemoteError("INVALID_PARAMS", "steps must be >= 1")
    curve = params.get("curve") or "smoothstep"
    if curve not in ("smoothstep", "linear"):
        raise RemoteError("INVALID_PARAMS", "curve must be smoothstep or linear")
    start = float(param.value)
    sleep_per_step = duration / steps if steps > 0 else 0.0
    for step in range(1, steps + 1):
        t = step / float(steps)
        shaped = t * t * (3.0 - 2.0 * t) if curve == "smoothstep" else t
        param.value = start + (target - start) * shaped
        if sleep_per_step > 0:
            yield
            time.sleep(sleep_per_step)
    final_value = float(param.value)
    result = {
        "track": getattr(track, "name", ""),
        "curve": curve,
        "duration": duration,
        "steps": steps,
        "start_value": start,
        "target_value": target,
        "final_value": final_value,
        "final_percent": round(final_value / LIVE_FADE_UNITY_VALUE * 100.0, 3),
    }
    try:
        result["display"] = param.str_for_value(param.value)
    except Exception:
        pass
    return result
```

The dispatch branch is:

```python
if normalized == "live_fade":
    return (yield from live_fade_steps(song, application, params))
```

**Contract changes:**

- Add `live_fade` to `COMMAND_TIMEOUT_OVERRIDES` with value `60.0` so the dispatcher always leaves room.
- Extend `_request_work_units` with a `live_fade` branch that scales with `steps`.
- Add `"live_fade"` to `ALLOWED_MUTATIONS` (it modifies fader values; allow it through `run_batch`).
- Re-run `scripts/vendor_contracts.py`.

**Tests required:**

- `test_live_fade_smoothstep_interpolates_within_min_max` — verify the final fader value lands between start and target within tolerance.
- `test_live_fade_linear_interpolates_within_min_max` — same with `curve: "linear"`.
- `test_live_fade_rejects_target_percent_above_unity_without_flag` — `target_percent: 120`, default `allow_over_unity: False` → `INVALID_PARAMS` and the message contains "unity".
- `test_live_fade_rejects_duration_above_max` — `duration: 90` → `INVALID_PARAMS`.
- `test_live_fade_rejects_zero_steps` — `steps: 0` → `INVALID_PARAMS`.
- `test_live_fade_rejects_invalid_curve` — `curve: "gibberish"` → `INVALID_PARAMS`.
- `tests/test_tool_registry.py` — count 60.

**Risks specific:**

- **First command that blocks the Live main thread for up to 60 seconds.** The Python MCP layer must auto-raise the RPC timeout to `duration + 10.0` so the dispatcher cannot leak requests past the fade. Surface this in the tool docstring.
- **No selective undo**: a fader fade is one continuous user-initiated action. Live does not have a built-in per-step undo. The single undo step covers the entire fade. Document this.
- **No heartbeat**: the RPC server cannot send progress events while the fade is running. The MCP client waits silently. Documented.
- `LIVE_FADE_UNITY_VALUE = 0.8500000238418579` is a magic number lifted verbatim from upstream. It is the Live-12 unity value; do not paraphrase without regression-testing against a real Live Set.

---

### B5. `create_audio_track(index, name)` — ML-5 subset

**Source:** `mlmil/Ableton-Live-MCP-ULTRA-v2` @ `9469872`, `Ableton_Live_MCP/bridge.py:949` (`_rpc_create_audio_track`). We already have `create_midi_track` in v0.4.0 — `create_audio_track` is the symmetric audio-side tool.

**Their signature (verbatim):**

```python
def _rpc_create_audio_track(self, params):
    return self._create_track("create_audio_track", params)


def _create_track(self, method_name, params):
    song = self.song()
    fn = getattr(song, method_name, None)
    if not callable(fn):
        raise RuntimeError("Live Song object does not expose %s()" % method_name)
    index = int(params.get("index") if params.get("index") is not None else -1)
    before_ids = set(id(track) for track in song.tracks)
    fn(index)
    created = None
    created_index = None
    for position, track in enumerate(song.tracks):
        if id(track) not in before_ids:
            created = track
            created_index = position
            break
    result = {"track_count": len(song.tracks), "requested_index": index}
    if created is not None:
        if params.get("name"):
            created.name = str(params["name"])
        summary = self._object_summary(created, False)
        summary["name"] = getattr(created, "name", "")
        result["track"] = summary
        result["track_index"] = created_index
    return result
```

**Our signature (proposed — sync, mirrors existing `create_midi_track`):**

```python
@mcp.tool()
def create_audio_track(index: int = -1, name: str | None = None) -> Any:
    """Create a new audio track in the Set, optionally at a specific position with a name."""
    return _remote("create_audio_track", models.CreateAudioTrackRequest(index=index, name=name))
```

**Pydantic model:**

```python
class CreateAudioTrackRequest(RequestModel):
    index: int = -1
    name: str | None = Field(default=None, max_length=120)


class CreateMidiTrackRequest(CreateAudioTrackRequest):
    """Inherited from v0.4.0. Kept here so the symmetry is explicit."""
    pass
```

**Remote Script handler (sync; mirrors existing `create_midi_track` with method_name substitution):**

```python
def cmd_create_audio_track(song, _application, params):
    return _create_track_helper(song, "create_audio_track", params)


def _create_track_helper(song, method_name, params):
    fn = getattr(song, method_name, None)
    if not callable(fn):
        raise RemoteError(
            "LIVE_UNAVAILABLE",
            f"Live Song object does not expose {method_name}()",
        )
    index = int(params.get("index") if params.get("index") is not None else -1)
    before_ids = set(id(track) for track in song.tracks)
    fn(index)
    created = None
    created_index = None
    for position, track in enumerate(song.tracks):
        if id(track) not in before_ids:
            created = track
            created_index = position
            break
    result = {"track_count": len(song.tracks), "requested_index": index}
    if created is not None:
        if params.get("name"):
            created.name = str(params["name"])
        result["track"] = {
            "index": created_index,
            "name": getattr(created, "name", ""),
        }
        result["track_index"] = created_index
    return result
```

Existing `cmd_create_midi_track` is refactored to delegate to `_create_track_helper(song, "create_midi_track", params)`. Backward compatibility holds because the existing public tool and request model are unchanged.

**Contract changes:**

- Add `"create_audio_track"` to `ALLOWED_MUTATIONS`.
- Re-run `scripts/vendor_contracts.py`.

**Tests required:**

- `test_create_audio_track_appends_with_index_minus_one` — fake song without preset audio tracks; `index=-1`; handler creates one audio track at the tail.
- `test_create_audio_track_inserts_at_index` — `index=2`; verify the new track is at position 2.
- `test_create_audio_track_renames_when_name_provided` — `name="vocals"`; verify the track name is set.
- `test_create_audio_track_raises_when_live_unavailable` — fake song without `create_audio_track` callable → `LIVE_UNAVAILABLE`.
- `tests/test_tool_registry.py` — count 61.

**Risks specific:**

- Live introduces audio tracks with default input/output routing (mono in / stereo out). The tool does not allow callers to set routing; documenting this is sufficient because routing stays in `set_track_property` semantics that we already have for mute/solo/arm.
- Refactoring existing `cmd_create_midi_track` must not break `tests/test_midi_track_creation.py`. Run that suite as a regression gate.

---

### B6. Module: `ableton_mcp_server.analysis.audio` — MD-1

**Source:** `motodigitalguru-beep/ableton-mcp-extended` @ `89617ab7ab0a8421e98ba70cbb43f3ee89cda0d3`, `ableton_mcp_extended/audio_analysis.py`.

**Their signature (verbatim, paraphrased for size):**

```python
def analyze_audio(path: str) -> dict:
    samples, sr = sf.read(path)
    mono = samples.mean(axis=1) if samples.ndim > 1 else samples
    rms_db = 20 * np.log10(np.sqrt(np.mean(mono ** 2)) + 1e-9)
    peak_db = 20 * np.log10(np.max(np.abs(mono)) + 1e-9)
    lufs = _lufs_i(mono, sr)
    bands = _bands(mono, sr)
    return {
        "duration_s": float(mono.size / sr),
        "sample_rate": sr,
        "lufs_i": lufs,
        "rms_dbfs": rms_db,
        "peak_dbfs": peak_db,
        "bands": bands,
    }
```

**Our signature (proposed — pure-Python, no bridge):**

```python
def analyze_audio(path: str) -> dict[str, Any]:
    """Compute LUFS-I, true-peak, RMS, and per-band energy summary for a local audio file.

    Side effects: reads the file from disk.
    Edge cases: unsupported encodings return a structured ``{"ok": False, "reason": ...}`` payload.
    """
```

The wrapper in `server.py`:

```python
@mcp.tool()
def analyze_audio(path: str) -> dict[str, Any]:
    """..."""
    return _explicit_json_result(ableton_mcp_server.analysis.analyze_audio(path))
```

**Module layout:**

```python
# ableton_mcp_server/analysis/__init__.py
from .audio import (
    analyze_audio,
    find_frequency_masking,
    analyze_mix,
    extract_single_cycle,
)
__all__ = [
    "analyze_audio",
    "find_frequency_masking",
    "analyze_mix",
    "extract_single_cycle",
]
```

```python
# ableton_mcp_server/analysis/audio.py
"""Offline mix analysis utilities.

This module is dependency-free of Live, the Remote Script, or the bridge. It
reads local audio files through ``soundfile`` and computes LUFS-I
approximations, true-peak, RMS, per-band energy summaries, masking scores,
and single-cycle wavetable candidates. All public functions return plain
dicts; the MCP layer wraps them in tools.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import soundfile as sf

LUFS_BLOCK_S = 0.4
LOW_HZ = 250.0
HIGH_HZ = 4000.0
MAX_STEMS = 16
SINGLE_CYCLE_DEFAULT_FRAME = 2048
SINGLE_CYCLE_PROBE_S = 5.0


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, always_2d=False)
    if isinstance(data, np.ndarray) and data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.float64), int(sr)


def _rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples + 1e-12))))
    return 20.0 * math.log10(rms) if rms > 0 else -120.0


def _true_peak_dbfs(samples: np.ndarray) -> float:
    oversampled = np.repeat(samples, 4)
    peak = float(np.max(np.abs(oversampled)))
    return 20.0 * math.log10(peak) if peak > 0 else -120.0


def _lufs_i_approx(samples: np.ndarray, sample_rate: int) -> float:
    mean_square = float(np.mean(np.square(samples + 1e-12)))
    return 20.0 * math.log10(mean_square) - 0.691


def _bands(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    low_mask = freqs < LOW_HZ
    mid_mask = (freqs >= LOW_HZ) & (freqs < HIGH_HZ)
    high_mask = freqs >= HIGH_HZ
    low = float(np.mean(spectrum[low_mask] ** 2)) if np.any(low_mask) else 0.0
    mid = float(np.mean(spectrum[mid_mask] ** 2)) if np.any(mid_mask) else 0.0
    high = float(np.mean(spectrum[high_mask] ** 2)) if np.any(high_mask) else 0.0
    return {
        "low_db": 10.0 * math.log10(low + 1e-12),
        "mid_db": 10.0 * math.log10(mid + 1e-12),
        "high_db": 10.0 * math.log10(high + 1e-12),
    }


def analyze_audio(path: str) -> dict[str, Any]:
    samples, sample_rate = _load_mono(path)
    return {
        "duration_s": float(samples.size / sample_rate),
        "sample_rate": sample_rate,
        "lufs_i": _lufs_i_approx(samples, sample_rate),
        "rms_dbfs": _rms_dbfs(samples),
        "peak_dbfs": _true_peak_dbfs(samples),
        "bands": _bands(samples, sample_rate),
    }


def _band_mask(freqs, target_db, reference_db, low_hz, high_hz, threshold_db):
    mask = (freqs >= low_hz) & (freqs < high_hz)
    if not np.any(mask):
        return {
            "start_hz": low_hz,
            "end_hz": high_hz,
            "target_db": -120.0,
            "reference_db": -120.0,
            "excess_db": None,
        }
    target_band = float(np.mean(target_db[mask]))
    reference_band = float(np.mean(reference_db[mask]))
    excess = target_band - reference_band
    return {
        "start_hz": low_hz,
        "end_hz": high_hz,
        "target_db": target_band,
        "reference_db": reference_band,
        "excess_db": excess if excess >= threshold_db else None,
    }


def find_frequency_masking(
    target_path: str,
    reference_path: str,
    threshold_db: float = 6.0,
) -> dict[str, Any]:
    target, sr_t = _load_mono(target_path)
    reference, sr_r = _load_mono(reference_path)
    if sr_t != sr_r:
        raise ValueError("sample rate mismatch between target and reference")
    spec_t = np.abs(np.fft.rfft(target))
    spec_r = np.abs(np.fft.rfft(reference))
    freqs = np.fft.rfftfreq(target.size, d=1.0 / sr_t)
    log_t = 20.0 * np.log10(spec_t + 1e-12)
    log_r = 20.0 * np.log10(spec_r + 1e-12)
    bands = [
        _band_mask(freqs, log_t, log_r, 0.0, LOW_HZ, threshold_db),
        _band_mask(freqs, log_t, log_r, LOW_HZ, HIGH_HZ, threshold_db),
        _band_mask(freqs, log_t, log_r, HIGH_HZ, sr_t / 2, threshold_db),
    ]
    excess = [b["excess_db"] for b in bands if b["excess_db"] is not None]
    return {"bands": bands, "score": float(max(excess) if excess else 0.0)}


def analyze_mix(stems: Sequence[str]) -> dict[str, Any]:
    if len(stems) > MAX_STEMS:
        raise ValueError(f"too many stems (>{MAX_STEMS}); split the request")
    stem_metrics = [{"name": stem, **analyze_audio(stem)} for stem in stems]
    pairwise = []
    for i, stem_a in enumerate(stems):
        for stem_b in stems[i + 1 :]:
            result = find_frequency_masking(stem_a, stem_b, threshold_db=3.0)
            pairwise.append(
                {"target": stem_a, "reference": stem_b, "score": result["score"]}
            )
    return {
        "stems": stem_metrics,
        "pairwise_masking": pairwise,
        "max_stems": MAX_STEMS,
    }


def extract_single_cycle(path: str, frame_size: int = SINGLE_CYCLE_DEFAULT_FRAME) -> dict[str, Any]:
    samples, sample_rate = _load_mono(path)
    probe_samples = min(int(SINGLE_CYCLE_PROBE_S * sample_rate), samples.size)
    head = samples[:probe_samples]
    if head.size < frame_size:
        return {"ok": False, "reason": "file shorter than frame_size"}
    autocorr = np.correlate(head, head, mode="full")
    autocorr = autocorr[autocorr.size // 2 :]
    peak = int(np.argmax(autocorr[1:frame_size]) + 1)
    if peak <= 0:
        return {"ok": False, "reason": "no clear periodicity"}
    pitch_hz = sample_rate / peak
    cycle = samples[:peak].astype(np.float32)
    return {
        "ok": True,
        "frame_size": frame_size,
        "cycle_samples": int(peak),
        "pitch_hz": float(pitch_hz),
        "cycle": cycle.tolist(),
    }
```

**Pydantic model and tool for `analyze_audio`:**

```python
class AnalyzeAudioRequest(RequestModel):
    path: str = Field(min_length=1)
```

```python
@mcp.tool()
def analyze_audio(path: str) -> dict[str, Any]:
    """Compute LUFS-I, true-peak, RMS, and per-band energy summary for a local audio file."""
    return _explicit_json_result(ableton_mcp_server.analysis.analyze_audio(path))
```

**Contract changes:** none. These tools live on the Python MCP layer and never cross the bridge.

**Tests required (in `tests/test_audio_analysis_v050.py`):**

- `test_analyze_audio_returns_lufs_rms_and_per_band` — synth a 440 Hz sine, verify `lufs_i < 0`, `rms_dbfs < 0`, `bands.mid_db > bands.low_db`.
- `test_analyze_audio_rejects_missing_file` — path that doesn't exist → structured `{"ok": False, "reason": ...}` envelope (the wrapper catches and returns).
- `tests/test_tool_registry.py` — count 62.

**Risks specific:**

- LUFS-I is an approximation. Our formula uses mean-square per 400 ms block with K-weighted headroom; not EBU R128 compliant. Document in docstring.
- True-peak is computed by 4× oversample, not the full 48-tap polyphase ITU-R filter. Acceptable for an offline hint, not a final delivery.

---

### B7. `find_frequency_masking(target_path, reference_path, threshold_db)` — MD-2

**Source:** `motodigitalguru-beep/ableton-mcp-extended`, `ableton_mcp_extended/audio_analysis.py:find_frequency_masking`.

**Their signature (verbatim):**

```python
def find_frequency_masking(target: str, reference: str, threshold_db: float = 6.0) -> dict:
    # ... reads both files, runs 1024-pt STFT, returns bands that exceed threshold ...
```

**Our signature (proposed):**

```python
@mcp.tool()
def find_frequency_masking(
    target_path: str,
    reference_path: str,
    threshold_db: float = 6.0,
) -> dict[str, Any]:
    """Identify frequency bands where ``target_path`` exceeds ``reference_path`` by ``threshold_db`` dB or more."""
    return _explicit_json_result(
        ableton_mcp_server.analysis.find_frequency_masking(
            target_path=target_path,
            reference_path=reference_path,
            threshold_db=threshold_db,
        )
    )
```

**Pydantic model:**

```python
class FindFrequencyMaskingRequest(RequestModel):
    target_path: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    threshold_db: float = 6.0

    @model_validator(mode="after")
    def _paths_differ(self) -> "FindFrequencyMaskingRequest":
        if self.target_path == self.reference_path:
            raise ValueError("target_path and reference_path must differ")
        return self
```

**Module function:** defined in B6 above.

**Tests required:**

- `test_find_frequency_masking_reports_excess_band` — synth loud 1 kHz target against quiet 1 kHz reference; assert a band reports `excess_db >= 6.0`.
- `test_find_frequency_masking_returns_empty_when_no_excess` — equal-amplitude pair; assert `score == 0.0` and no band has `excess_db`.
- `test_find_frequency_masking_rejects_same_paths` — Pydantic validator raises on equal paths.
- `test_find_frequency_masking_rejects_mismatched_sample_rates` — 44.1 k target vs 48 k reference → `ValueError`.
- `tests/test_tool_registry.py` — count 63.

**Risks specific:**

- The tool does not write to Live. The agent must apply EQ through `set_parameter_value` after reading suggestions.

---

### B8. `analyze_mix(stems: list[str])` — MD-3

**Source:** `motodigitalguru-beep/ableton-mcp-extended`, `ableton_mcp_extended/audio_analysis.py:analyze_mix`.

**Their signature (verbatim, paraphrased):**

```python
def analyze_mix(stems: list[str]) -> dict:
    # ... per-stem analyze_audio; pair-wise masking; no documented cap ...
```

**Our signature (proposed):**

```python
@mcp.tool()
def analyze_mix(stems: list[str]) -> dict[str, Any]:
    """Run per-stem analysis and pair-wise masking across up to 16 local audio files."""
    return _explicit_json_result(ableton_mcp_server.analysis.analyze_mix(stems=stems))
```

**Pydantic model:**

```python
class AnalyzeMixRequest(RequestModel):
    stems: Annotated[list[str], Field(min_length=1, max_length=16)]
```

**Module function:** defined in B6 above. `MAX_STEMS = 16` is hard-coded in the module; document as the policy cap.

**Tests required:**

- `test_analyze_mix_returns_pairwise_masking` — synth two distinct stems at high amplitude; verify `pairwise_masking` has one entry.
- `test_analyze_mix_caps_stem_count` — 17 paths → `ValueError`.
- `test_analyze_mix_rejects_empty_list` — Pydantic validator raises on `stems=[]`.
- `tests/test_tool_registry.py` — count 64.

**Risks specific:**

- Pair-wise masking is O(N²). With 16 stems that's 120 pairs and acceptable for offline analysis; document the cost in the docstring.

---

### B9. `extract_single_cycle(path, frame_size)` — MD-4

**Source:** `motodigitalguru-beep/ableton-mcp-extended`, `ableton_mcp_extended/audio_analysis.py:extract_single_cycle`.

**Their signature (verbatim, paraphrased):**

```python
def extract_single_cycle(path: str, frame_size: int = 2048) -> dict:
    # ... autocorrelation of the first frame_size samples; returns cycle + pitch ...
```

**Our signature (proposed):**

```python
@mcp.tool()
def extract_single_cycle(path: str, frame_size: int = 2048) -> dict[str, Any]:
    """Find a candidate single-cycle loop in a local audio file plus its detected pitch."""
    return _explicit_json_result(
        ableton_mcp_server.analysis.extract_single_cycle(path=path, frame_size=frame_size)
    )
```

**Pydantic model:**

```python
class ExtractSingleCycleRequest(RequestModel):
    path: str = Field(min_length=1)
    frame_size: Annotated[int, Field(ge=64, le=65536)] = 2048
```

**Module function:** defined in B6 above. Probe scope is the first 5 seconds of audio.

**Tests required:**

- `test_extract_single_cycle_finds_periodic_signal` — synth 440 Hz sine; verify `ok: True`, `pitch_hz ≈ 440`.
- `test_extract_single_cycle_returns_failure_when_aperiodic` — synth white noise; verify `ok: False`, `reason` populated.
- `test_extract_single_cycle_rejects_short_file` — file shorter than `frame_size` → `ok: False, reason: "file shorter than frame_size"`.
- `tests/test_tool_registry.py` — count 65.

**Risks specific:**

- Autocorrelation on the first 5 seconds is heuristic; sounds with strong vibrato or LFO modulation may return the LFO period, not the fundamental. Document in the docstring. Future versions may bias by energy envelope; out of scope here.

---

## C. Auxiliary contract changes (apply across the whole release)

The following items live in `contracts.py` and must be regenerated by `scripts/vendor_contracts.py` after edits:

### C1. Add command names

```python
# Set lifecycle and fader fade (v0.5.0)
COMMAND_LIFECYCLE_STATUS = "lifecycle_status"
COMMAND_SAVE_SET = "save_set"
COMMAND_QUIT_ABLETON = "quit_ableton"
COMMAND_LIVE_FADE = "live_fade"
COMMAND_CREATE_AUDIO_TRACK = "create_audio_track"
```

Analysis tools do not need constants here — they are local to the Python MCP layer.

### C2. Extend `_request_work_units`

```python
def _request_work_units(command_name: str, params: object) -> int:
    if not isinstance(params, dict):
        return 1
    normalized = command_name.strip().lower()
    if normalized == "bulk_create_cue_points":
        # ... existing ...
    if normalized == "live_fade":
        steps = params.get("steps")
        return min(60, int(steps) + 1) if isinstance(steps, int) else 41
    # ... existing ...
    return 1
```

### C3. Extend `COMMAND_TIMEOUT_OVERRIDES`

```python
COMMAND_TIMEOUT_OVERRIDES = {
    "load_device_to_track": 30.0,
    "search_browser": 30.0,
    "create_clip_automation": 20.0,
    "live_fade": 60.0,
}
```

### C4. Extend allowlists

`READ_COMMANDS` gains `"lifecycle_status"`. `ALLOWED_MUTATIONS` gains `"save_set"`, `"quit_ableton"`, `"live_fade"`, `"create_audio_track"`. Add an entry for each in the dispatch table of `_dispatch_command_steps`.

### C5. Regenerate vendored contracts

Run: `python scripts/vendor_contracts.py`

Expected: `AbletonMCPServer_RemoteScript/_contracts.py` ends with the new entries. The generated file must not have any other content changes; if it does, the contracts drift test fails.

---

## D. Runtime identity bump

Per the existing pattern in `AbletonMCPServer_RemoteScript/__init__.py`, the runtime identity constant (`REMOTE_SCRIPT_RUNTIME_VERSION` or similar) must bump to reflect the new capability set. The pre-bump tag is the v0.4.0 tag (`capability-expansion-1`-class of identity); the post-bump tag is **`set-lifecycle-and-fade-1`**.

Find the existing constant:

```bash
grep -nE 'RUNTIME_VERSION|RUNTIME_IDENTIFIER|RUNTIME_TAG' AbletonMCPServer_RemoteScript/__init__.py
```

Then increment. This is a single-line commit `chore(remote): bump runtime identity to set-lifecycle-and-fade-1`.

---

## E. Test infrastructure

Add `tests/analysis_synth.py` with two deterministic helpers:

```python
"""Deterministic synthesized signals for offline mix-analysis tests."""

from __future__ import annotations

import numpy as np
import soundfile as sf


def write_sine(path, *, frequency_hz: float, duration_s: float, sample_rate: int = 48000, amplitude: float = 0.5) -> None:
    samples = int(duration_s * sample_rate)
    t = np.linspace(0.0, duration_s, samples, endpoint=False)
    signal = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    sf.write(str(path), signal.astype(np.float32), sample_rate)


def write_kick(path, *, duration_s: float = 0.5, sample_rate: int = 48000) -> None:
    samples = int(duration_s * sample_rate)
    t = np.linspace(0.0, duration_s, samples, endpoint=False)
    pitch = 60.0 * np.exp(-t * 8.0)
    signal = 0.7 * np.sin(2.0 * np.pi * pitch * t) * np.exp(-t * 4.0)
    sf.write(str(path), signal.astype(np.float32), sample_rate)
```

Add `numpy` and `soundfile` to `pyproject.toml`:

```toml
[project.optional-dependencies.test]
numpy = ">=1.26"
soundfile = ">=0.12"
```

Then `pip install -e ".[test]"` regenerates the venv.

---

## F. Public doc updates

### F1. `docs/TOOL_REFERENCE.md`

Add a new section under the existing tool listing:

```
## Set Lifecycle

### `lifecycle_status()`
...

### `save_set(require_api)`
...

### `quit_ableton(save, force_without_save, quit_delay_ticks)`
...

## Fader Automation

### `live_fade(track_index, target_percent, target_value, duration, steps, curve, allow_over_unity)`
...

## Offline Mix Analysis

### `analyze_audio(path)`
...

### `find_frequency_masking(target_path, reference_path, threshold_db)`
...

### `analyze_mix(stems)`
...

### `extract_single_cycle(path, frame_size)`
...
```

For each entry, document parameters, return shape, side effects, one worked example, and the related MIX-analysis caveat ("MCP layer wraps without bridge; safe to call from any client, including offline-only contexts").

### F2. `README.md`

Add the new capability in the existing capabilities bullet list:

```markdown
- **v0.5.0 lifecycle and offline mix:** `lifecycle_status`, `save_set`, `quit_ableton`, `live_fade` for end-to-end scripted control of Live, plus offline `analyze_audio`, `find_frequency_masking`, `analyze_mix`, `extract_single_cycle` for `numpy`-powered mix feedback without leaving the MCP session.
```

Update the tool count to `65`.

### F3. `CHANGELOG.md`

```markdown
## v0.5.0 — set lifecycle, fader fade, and offline mix analysis

Adds four set lifecycle tools (`lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`)
plus one audio-track creation tool (`create_audio_track`) and four offline
mix-analysis tools (`analyze_audio`, `find_frequency_masking`, `analyze_mix`,
`extract_single_cycle`). Lifecycle commands derived from
`mlmil/Ableton-Live-MCP-ULTRA-v2` and rewritten against the in-repo
primitives. Mix analysis rewritten from scratch against `numpy` and
`soundfile`. No vendored code. Public MCP tool count grows from 56 to 65.
```

The CHANGELOG entry **must** mention both upstream projects for attribution.

---

## G. Release gate

In order, before presenting for review:

1. `python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests`
2. `python -m mypy --strict ableton_mcp_server ableton_mcp_server/analysis`
3. `python scripts/vendor_contracts.py` (drift test follows)
4. `python -m pytest -q --tb=line`
5. `python -m pytest tests/test_tool_registry.py -q` (must yield 65)
6. `python -m pytest tests/test_vendoring.py -q` (must yield "no drift")
7. `npm --prefix AbletonMCPServer_Extension run build` (Extension build)
8. Owner-side: open a disposable Set, manually exercise each new lifecycle command, verify the fade blocks and completes, verify `auto_fix_masking` is **not** exposed.

---

## H. Out-of-band notes for the reviewer

- The Remote Script runtime identity bumps once per release; subsequent lifecycle/fade changes reuse `set-lifecycle-and-fade-1` until the next release. Document this convention in the PR description.
- Mix analysis never crosses the Live boundary; the only side effects are filesystem reads and `numpy` operations. The MCP layer wraps each tool with `_explicit_json_result` so the response envelope matches other read-only tools.
- `live_fade` **deliberately blocks** the Live main thread for up to 60 seconds. This is documented in three places: the tool docstring, the CHANGELOG entry, and the PR description. If future maintainers want to make this non-blocking, they should consider a `Live.Listener`-based scheduler; out of scope here.
- Real-Live acceptance for the lifecycle, fade, and audio-track tools against a disposable Set remains an owner-run step. Offline tests do not claim Live connectivity, undo behavior, or main-thread scheduling.
- A future "live-side audio inspection" PR may add `capture_track_to_wav` and `configure_sidechain`; this release explicitly defers them.
- If a future user complains that `auto_fix_masking` is missing, point them to this SPEC and REQUEST; the explicit non-goal is intentional.
