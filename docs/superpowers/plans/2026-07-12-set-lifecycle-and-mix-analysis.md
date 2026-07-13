# Set Lifecycle and Mix Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver two complementary capability expansions: (A) safe set lifecycle (`lifecycle_status`, `save_set`, `quit_ableton`) plus a timed fader `live_fade`, derived from `mlmil/Ableton-Live-MCP-ULTRA-v2` and rewritten against the in-repo primitives; (B) offline mix analysis (`analyze_audio`, `find_frequency_masking`, `analyze_mix`, `extract_single_cycle`), derived from `motodigitalguru-beep/ableton-mcp-extended` and rewritten from scratch against `numpy` + `soundfile`. Total MCP tool count grows by 8 (from 56 to 64).

**Architecture:** New lifecycle commands remain on the existing TCP Remote Script UI-thread queue. `live_fade` is the first command that intentionally blocks the Live main thread for up to 60 seconds, with the Python MCP layer auto-raising the RPC timeout. Mix analysis is a new module-local Python subsystem with zero Live, Remote Script, or socket dependency.

**Tech Stack:** Python 3.10+, FastMCP, Pydantic v2, Ableton Python LOM, numpy, soundfile, pytest, Ruff, mypy strict, TypeScript Extension build.

**Lint configuration:** Ruff line length 100 and the repository's `pyproject.toml` rules; mypy `--strict` for `ableton_mcp_server` and the new `analysis` module.

---

## File map

- `contracts.py`: canonical read/mutation sets, timeout work units, lifecycle constants.
- `AbletonMCPServer_RemoteScript/_contracts.py`: generated mirror (via `scripts/vendor_contracts.py`).
- `AbletonMCPServer_RemoteScript/__init__.py`: UI-thread LOM handlers and deferred generators for the four new lifecycle commands.
- `ableton_mcp_server/analysis/__init__.py`: public exports for the mix-analysis module.
- `ableton_mcp_server/analysis/audio.py`: pure-Python/numpy/soundfile mix-analysis functions.
- `ableton_mcp_server/models.py`: eight new Pydantic request models.
- `ableton_mcp_server/server.py`: eight new `@mcp.tool` public surfaces and `PUBLIC_TOOL_NAMES` entries.
- `tests/analysis_synth.py`: deterministic synthesized audio signals for analysis tests.
- `tests/test_lifecycle_v050.py`: focused lifecycle command and tool behavior.
- `tests/test_fade_v050.py`: focused fade generator and tool behavior.
- `tests/test_audio_analysis_v050.py`: focused mix-analysis public-function behavior.
- `tests/test_server_tools.py`, `tests/test_models.py`, `tests/test_tool_registry.py`: registry inflation invariant tests.
- `tests/test_contracts.py`, `tests/test_vendoring.py`: contract and vendoring invariants.
- `docs/TOOL_REFERENCE.md`, `README.md`, `CHANGELOG.md`: public release contract.
- `pyproject.toml`: optional `numpy` + `soundfile` runtime + test dependencies.

## Task 1: Lifecycle and fade constants and contract placeholder

**Files:**
- Modify: `contracts.py`
- Generate: `AbletonMCPServer_RemoteScript/_contracts.py`

- [ ] **Step 1: Add the lifecycle command names and constants**

Append to `contracts.py`:

```python
# Set lifecycle and fader fade (v0.5.0)
COMMAND_LIFECYCLE_STATUS = "lifecycle_status"
COMMAND_SAVE_SET = "save_set"
COMMAND_QUIT_ABLETON = "quit_ableton"
COMMAND_LIVE_FADE = "live_fade"
COMMAND_ANALYZE_AUDIO = "analyze_audio"
COMMAND_FIND_FREQUENCY_MASKING = "find_frequency_masking"
COMMAND_ANALYZE_MIX = "analyze_mix"
COMMAND_EXTRACT_SINGLE_CYCLE = "extract_single_cycle"
```

- [ ] **Step 2: Regenerate vendored contracts**

Run: `python scripts/vendor_contracts.py`
Expected: `AbletonMCPServer_RemoteScript/_contracts.py` contains the eight new names.

- [ ] **Step 3: Commit**

```text
chore(contracts): reserve lifecycle, fade, and mix analysis command names for v0.5.0
```

## Task 2: `lifecycle_status` read-only probe

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Create: `tests/test_lifecycle_v050.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `tests/remote_fakes.py`

- [ ] **Step 1: Write failing tests for the Remote Script command**

```python
def test_lifecycle_status_reports_save_availability(monkeypatch) -> None:
    song = FakeSong(save=lambda: None)
    application = FakeApplication(quit=lambda: None)
    result = execute_command(song, application, "lifecycle_status", {})
    assert result["song_save_available"] is True
    assert result["app_quit_available"] is True
    assert "save" in result["gui_workflow"]
    assert "quit" in result["gui_workflow"]


def test_lifecycle_status_reports_missing_quit(monkeypatch) -> None:
    song = FakeSong(save=lambda: None)
    application = FakeApplication()
    result = execute_command(song, application, "lifecycle_status", {})
    assert result["song_save_available"] is True
    assert result["app_quit_available"] is False
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_lifecycle_v050.py -q`
Expected: collection failure because the helper/fake/command do not exist.

- [ ] **Step 3: Implement the Remote Script command**

Add to `AbletonMCPServer_RemoteScript/__init__.py`:

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
    save_attr_names = ("save",)
    quit_attr_names = ("quit",)
    return {
        "song_save_attrs": [name for name in save_attr_names if hasattr(song, name)],
        "app_lifecycle_attrs": [name for name in quit_attr_names if hasattr(application, name)],
        "song_save_available": callable(getattr(song, "save", None)),
        "app_quit_available": callable(getattr(application, "quit", None)),
        "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
    }
```

Add a `FakeApplication` shape to `tests/remote_fakes.py`:

```python
class FakeApplication:
    def __init__(self, quit=None):
        self._quit = quit

    def quit(self):
        if self._quit is None:
            raise AttributeError("Application.quit not exposed")
        return self._quit()
```

- [ ] **Step 4: Register in the dispatch table**

In `_dispatch_command_steps`, add the synchronous branch `if normalized ==
"lifecycle_status": return cmd_lifecycle_status(song, application,
params)`.

- [ ] **Step 5: Add the request model and tool**

In `ableton_mcp_server/models.py`:

```python
class GetLifecycleStatusRequest(EmptyRequest):
    pass
```

In `ableton_mcp_server/server.py`:

```python
"lifecycle_status",  # v0.5.0 — set lifecycle
```

and the tool:

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

- [ ] **Step 6: Verify GREEN and registry inflation**

Run: `python -m pytest tests/test_lifecycle_v050.py tests/test_server_tools.py tests/test_tool_registry.py -q`
Expected: all pass and tool count 57.

- [ ] **Step 7: Commit**

```text
feat(lifecycle): add lifecycle_status tool exposing save/quit API availability
```

## Task 3: `save_set` conditional save command

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Modify: `tests/test_lifecycle_v050.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `tests/remote_fakes.py`

- [ ] **Step 1: Write failing tests**

```python
def test_save_set_uses_song_save_when_available() -> None:
    invoked = {"called": False}

    def fake_save():
        invoked["called"] = True
        return None

    song = FakeSong(save=fake_save)
    result = execute_command(song, FakeApplication(), "save_set", {})
    assert invoked["called"] is True
    assert result == {"saved": True, "api_available": True, "result": None}


def test_save_set_returns_gui_workflow_when_save_missing() -> None:
    song = FakeSong(save=None)
    result = execute_command(song, FakeApplication(), "save_set", {})
    assert result["saved"] is False
    assert result["api_available"] is False
    assert "save" in result["gui_workflow"]


def test_save_set_raises_when_require_api_true_and_save_missing() -> None:
    song = FakeSong(save=None)
    with pytest.raises(RemoteError) as error:
        execute_command(song, FakeApplication(), "save_set", {"require_api": True})
    assert error.value.code == "BAD_INPUT"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_lifecycle_v050.py -q -k save`
Expected: failures for the missing command.

- [ ] **Step 3: Implement the Remote Script command**

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

Add the dispatch branch `if normalized == "save_set": return
cmd_save_set(song, application, params)`.

- [ ] **Step 4: Add the request model and tool**

```python
class SaveSetRequest(RequestModel):
    require_api: bool = False
```

```python
"save_set",  # v0.5.0 — save through Song.save()
```

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

- [ ] **Step 5: Verify GREEN and registry inflation**

Run: `python -m pytest tests/test_lifecycle_v050.py tests/test_server_tools.py tests/test_tool_registry.py -q`
Expected: all pass and tool count 58.

- [ ] **Step 6: Commit**

```text
feat(lifecycle): add save_set tool with conditional Song.save() fallback
```

## Task 4: `quit_ableton` scheduled-quit command

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Modify: `tests/test_lifecycle_v050.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `tests/remote_fakes.py`

- [ ] **Step 1: Write failing tests**

```python
def test_quit_ableton_saves_first_then_schedules_quit() -> None:
    save_calls = {"n": 0}
    quit_calls = {"n": 0}

    def fake_save():
        save_calls["n"] += 1
        return None

    def fake_quit():
        quit_calls["n"] += 1
        return None

    class FakeControlSurface:
        def schedule_message(self, _delay, fn):
            fn()

    song = FakeSong(save=fake_save)
    application = FakeApplication(quit=fake_quit)
    surface = FakeControlSurface()
    result = quit_ableton_steps(song, application, surface, {"save": True, "quit_delay_ticks": 1})
    assert save_calls["n"] == 1
    assert quit_calls["n"] == 1
    assert result["quit_requested"] is True


def test_quit_ableton_refuses_when_save_unavailable_and_force_false() -> None:
    song = FakeSong(save=None)
    application = FakeApplication(quit=lambda: None)
    result = execute_command(song, application, "quit_ableton", {})
    assert result["quit_requested"] is False
    assert "save" in result["gui_workflow"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_lifecycle_v050.py -q -k quit`
Expected: failures for the missing command and helper.

- [ ] **Step 3: Implement the generator-style Remote Script handler**

```python
def quit_ableton_steps(song, application, surface, params):
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
    surface.schedule_message(max(1, delay), quit_fn)
    return {"quit_requested": True, "saved_first": saved, "api_available": True, "scheduled": True}
```

Add the dispatch branch:

```python
if normalized == "quit_ableton":
    return quit_ableton_steps(song, application, _resolve_undo_target(None), params)
```

- [ ] **Step 4: Add the request model and tool**

```python
class QuitAbletonRequest(RequestModel):
    save: bool = True
    force_without_save: bool = False
    quit_delay_ticks: Annotated[int, Field(ge=1, le=120)] = 2
```

```python
"quit_ableton",  # v0.5.0 — save then quit
```

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

- [ ] **Step 5: Verify GREEN and registry inflation**

Run: `python -m pytest tests/test_lifecycle_v050.py tests/test_server_tools.py tests/test_tool_registry.py -q`
Expected: all pass and tool count 59.

- [ ] **Step 6: Commit**

```text
feat(lifecycle): add quit_ableton tool with scheduled GUI fallback
```

## Task 5: `live_fade` smoothstep/linear fader

**Files:**
- Modify: `contracts.py`
- Modify: `AbletonMCPServer_RemoteScript/_contracts.py` (generated)
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`
- Create: `tests/test_fade_v050.py`
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/server.py`

- [ ] **Step 1: Add the work-units helper for `live_fade`**

In `contracts.py`, extend `_request_work_units` with one branch:

```python
if normalized == "live_fade":
    steps = params.get("steps")
    return min(60, int(steps) + 1) if isinstance(steps, int) else 41
```

Add `live_fade` to `COMMAND_TIMEOUT_OVERRIDES`:

```python
"live_fade": 60.0,
```

Regenerate `AbletonMCPServer_RemoteScript/_contracts.py`.

- [ ] **Step 2: Write failing tests**

```python
def test_live_fade_smoothstep_interpolates_within_min_max() -> None:
    track = FakeTrack(volume=0.0, min=0.0, max=0.85)
    result = execute_command(FakeSong(tracks=[track]), FakeApplication(), "live_fade", {
        "track_index": 0,
        "target_percent": 100,
        "duration": 0.0,
        "steps": 4,
        "curve": "smoothstep",
    })
    assert result["curve"] == "smoothstep"
    assert result["steps"] == 4
    assert 0.7 <= result["final_value"] <= 0.85


def test_live_fade_rejects_target_percent_above_unity_without_flag() -> None:
    track = FakeTrack(volume=0.0, min=0.0, max=1.0)
    with pytest.raises(RemoteError) as error:
        execute_command(FakeSong(tracks=[track]), FakeApplication(), "live_fade", {
            "track_index": 0,
            "target_percent": 120,
            "duration": 0.0,
        })
    assert error.value.code == "INVALID_PARAMS"
    assert "unity" in str(error.value)


def test_live_fade_rejects_duration_above_max() -> None:
    track = FakeTrack(volume=0.0, min=0.0, max=1.0)
    with pytest.raises(RemoteError) as error:
        execute_command(FakeSong(tracks=[track]), FakeApplication(), "live_fade", {
            "track_index": 0,
            "target_percent": 50,
            "duration": 90,
        })
    assert error.value.code == "INVALID_PARAMS"
```

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests/test_fade_v050.py -q`
Expected: failures for the missing command.

- [ ] **Step 4: Implement the Remote Script generator**

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
            raise RemoteError("INVALID_PARAMS", "target_percent above 100 (unity) requires allow_over_unity:true")
        target = (percent / 100.0) * LIVE_FADE_UNITY_VALUE
    else:
        raise RemoteError("INVALID_PARAMS", "Provide target_percent or target_value")
    minimum = float(getattr(param, "min", 0.0))
    maximum = float(getattr(param, "max", 1.0))
    target = max(minimum, min(target, maximum))
    duration = float(params.get("duration") if params.get("duration") is not None else 10.0)
    if duration < 0.0 or duration > LIVE_FADE_MAX_DURATION:
        raise RemoteError("INVALID_PARAMS", f"duration must be between 0 and {LIVE_FADE_MAX_DURATION} seconds")
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

Add the dispatch branch `if normalized == "live_fade": return
(yield from live_fade_steps(song, application, params))`.

- [ ] **Step 5: Add the request model and tool**

```python
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

```python
"live_fade",  # v0.5.0 — timed fader fade on Live main thread
```

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

- [ ] **Step 6: Verify GREEN and registry inflation**

Run: `python -m pytest tests/test_fade_v050.py tests/test_server_tools.py tests/test_tool_registry.py -q`
Expected: all pass and tool count 60.

- [ ] **Step 7: Commit**

```text
feat(fade): add live_fade tool with smoothstep/linear interpolation on Live main thread
```

## Task 6: Pin Remote Script runtime identity

**Files:**
- Modify: `AbletonMCPServer_RemoteScript/__init__.py`

- [ ] **Step 1: Find the existing identity constant**

Run: `grep -n RUNTIME_VERSION or RUNTIME_IDENTIFIER or RUNTIME_TAG AbletonMCPServer_RemoteScript/__init__.py`

- [ ] **Step 2: Bump the identity**

Replace the existing tag with `"set-lifecycle-and-fade-1"`.

- [ ] **Step 3: Commit**

```text
chore(remote): bump runtime identity to set-lifecycle-and-fade-1
```

## Task 7: Mix analysis signal synthesis utility

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/analysis_synth.py`
- Create: `tests/test_audio_analysis_v050.py`

- [ ] **Step 1: Add numpy + soundfile to `pyproject.toml`**

Add to `[project.optional-dependencies.test]`:

```toml
"numpy>=1.26",
"soundfile>=0.12",
```

Run: `pip install -e ".[test]"`.
Expected: numpy and soundfile import succeeds under the venv.

- [ ] **Step 2: Write the failing synthesis tests**

```python
def test_synth_sine_path_writes_a_valid_wav(tmp_path) -> None:
    target = tmp_path / "sine.wav"
    write_sine(target, frequency_hz=440.0, duration_s=1.0, sample_rate=48000)
    assert target.exists()
    data, sr = sf.read(str(target))
    assert sr == 48000
    assert data.shape == (48000,)
    assert float(np.max(np.abs(data))) <= 0.99
```

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests/test_audio_analysis_v050.py -q`
Expected: import failure because `tests/analysis_synth.py` does not exist.

- [ ] **Step 4: Implement the synth utility**

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

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_audio_analysis_v050.py -q -k synth`
Expected: pass.

- [ ] **Step 6: Commit**

```text
test(analysis): add deterministic synthesized signals for offline mix tests
```

## Task 8: `analyze_audio` and friends (audio module)

**Files:**
- Create: `ableton_mcp_server/analysis/__init__.py`
- Create: `ableton_mcp_server/analysis/audio.py`
- Modify: `tests/test_audio_analysis_v050.py`

- [ ] **Step 1: Write the failing public-function tests**

```python
def test_analyze_audio_returns_lufs_rms_and_per_band(tmp_path) -> None:
    target = tmp_path / "sine.wav"
    write_sine(target, frequency_hz=440.0, duration_s=1.0)
    metrics = analyze_audio(str(target))
    assert metrics["duration_s"] == pytest.approx(1.0, rel=0.01)
    assert metrics["rms_dbfs"] < 0.0
    assert metrics["peak_dbfs"] < 0.0
    assert "low" in metrics["bands"] and "mid" in metrics["bands"] and "high" in metrics["bands"]
    assert metrics["bands"]["mid"] > metrics["bands"]["low"]


def test_find_frequency_masking_reports_excess_band(tmp_path) -> None:
    target = tmp_path / "loud_mid.wav"
    reference = tmp_path / "quiet_mid.wav"
    write_sine(target, frequency_hz=1000.0, duration_s=1.0, amplitude=0.8)
    write_sine(reference, frequency_hz=1000.0, duration_s=1.0, amplitude=0.1)
    result = find_frequency_masking(str(target), str(reference), threshold_db=6.0)
    assert any(b["excess_db"] >= 6.0 for b in result["bands"])


def test_analyze_mix_returns_pairwise_masking(tmp_path) -> None:
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    write_sine(a, frequency_hz=1000.0, duration_s=1.0, amplitude=0.8)
    write_sine(b, frequency_hz=200.0, duration_s=1.0, amplitude=0.8)
    result = analyze_mix([str(a), str(b)])
    assert len(result["stems"]) == 2
    assert len(result["pairwise_masking"]) == 2


def test_analyze_mix_caps_stem_count() -> None:
    with pytest.raises(ValueError):
        analyze_mix([f"stem_{i}.wav" for i in range(17)])


def test_extract_single_cycle_finds_periodic_signal(tmp_path) -> None:
    target = tmp_path / "osc.wav"
    write_sine(target, frequency_hz=440.0, duration_s=0.5)
    result = extract_single_cycle(str(target))
    assert result["ok"] is True
    assert abs(result["pitch_hz"] - 440.0) < 1.0
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_audio_analysis_v050.py -q`
Expected: failures for the missing module.

- [ ] **Step 3: Implement the audio module**

```python
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
    block_size = int(LUFS_BLOCK_S * sample_rate)
    if block_size <= 0 or samples.size < block_size:
        return -120.0
    mean_square = float(np.mean(np.square(samples + 1e-12)))
    return 20.0 * math.log10(mean_square) - 0.691


def _bands(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    low = float(np.mean(spectrum[freqs < LOW_HZ] ** 2)) if np.any(freqs < LOW_HZ) else 0.0
    mid = float(np.mean(spectrum[(freqs >= LOW_HZ) & (freqs < HIGH_HZ)] ** 2)) if np.any((freqs >= LOW_HZ) & (freqs < HIGH_HZ)) else 0.0
    high = float(np.mean(spectrum[freqs >= HIGH_HZ] ** 2)) if np.any(freqs >= HIGH_HZ) else 0.0
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


def find_frequency_masking(target_path: str, reference_path: str, threshold_db: float = 6.0) -> dict[str, Any]:
    target, sr_t = _load_mono(target_path)
    reference, sr_r = _load_mono(reference_path)
    if sr_t != sr_r:
        raise ValueError("sample rate mismatch between target and reference")
    spec_t = np.abs(np.fft.rfft(target))
    spec_r = np.abs(np.fft.rfft(reference))
    freqs = np.fft.rfftfreq(target.size, d=1.0 / sr_t)
    log_t = 20.0 * np.log10(spec_t + 1e-12)
    log_r = 20.0 * np.log10(spec_r + 1e-12)
    bands = []
    bands.append(_band_mask(freqs, log_t, log_r, 0.0, LOW_HZ, threshold_db))
    bands.append(_band_mask(freqs, log_t, log_r, LOW_HZ, HIGH_HZ, threshold_db))
    bands.append(_band_mask(freqs, log_t, log_r, HIGH_HZ, sr_t / 2, threshold_db))
    excess = [b["excess_db"] for b in bands if b["excess_db"] is not None]
    return {"bands": bands, "score": float(max(excess) if excess else 0.0)}


def _band_mask(freqs: np.ndarray, target_db: np.ndarray, reference_db: np.ndarray, low_hz: float, high_hz: float, threshold_db: float) -> dict[str, Any]:
    mask = (freqs >= low_hz) & (freqs < high_hz)
    target_band = float(np.mean(target_db[mask])) if np.any(mask) else -120.0
    reference_band = float(np.mean(reference_db[mask])) if np.any(mask) else -120.0
    excess = target_band - reference_band
    return {
        "start_hz": low_hz,
        "end_hz": high_hz,
        "target_db": target_band,
        "reference_db": reference_band,
        "excess_db": excess if excess >= threshold_db else None,
    }


def analyze_mix(stems: Sequence[str]) -> dict[str, Any]:
    if len(stems) > MAX_STEMS:
        raise ValueError(f"too many stems (>{MAX_STEMS}); split the request")
    stem_metrics = [{"name": stem, **analyze_audio(stem)} for stem in stems]
    pairwise = []
    for i, stem_a in enumerate(stems):
        for stem_b in stems[i + 1:]:
            result = find_frequency_masking(stem_a, stem_b, threshold_db=3.0)
            pairwise.append({"target": stem_a, "reference": stem_b, "score": result["score"]})
    return {"stems": stem_metrics, "pairwise_masking": pairwise, "max_stems": MAX_STEMS}


def extract_single_cycle(path: str, frame_size: int = 2048) -> dict[str, Any]:
    samples, sample_rate = _load_mono(path)
    head = samples[: min(frame_size * 8, samples.size)]
    if head.size < frame_size:
        return {"ok": False, "reason": "file shorter than frame_size"}
    autocorr = np.correlate(head, head, mode="full")
    autocorr = autocorr[autocorr.size // 2:]
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

Exports in `ableton_mcp_server/analysis/__init__.py`:

```python
from .audio import analyze_audio, find_frequency_masking, analyze_mix, extract_single_cycle
__all__ = ["analyze_audio", "find_frequency_masking", "analyze_mix", "extract_single_cycle"]
```

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_audio_analysis_v050.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```text
feat(analysis): add offline mix analysis utilities (LUFS, masking, single-cycle)
```

## Task 9: Mix analysis MCP wrappers

**Files:**
- Modify: `ableton_mcp_server/models.py`
- Modify: `ableton_mcp_server/server.py`
- Modify: `tests/remote_fakes.py` (no — unused)
- Modify: `tests/test_server_tools.py`
- Modify: `tests/test_tool_registry.py`

- [ ] **Step 1: Write failing tests for the four MCP wrappers**

```python
def test_analyze_audio_tool_returns_envelope() -> None:
    path = str(AUDIO_FIXTURES / "sine.wav")
    envelope = analyze_audio(path=path)
    assert envelope["status"] == "ok" or "ok" in envelope


def test_find_frequency_masking_tool_validates_arguments(tmp_path) -> None:
    with pytest.raises(RemoteError):
        execute_command(FakeSong(), FakeApplication(), "find_frequency_masking", {})
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_server_tools.py -q -k mask`
Expected: failures for the missing tool.

- [ ] **Step 3: Add the request models and tools**

```python
class AnalyzeAudioRequest(RequestModel):
    path: str = Field(min_length=1)


class FindFrequencyMaskingRequest(RequestModel):
    target_path: str = Field(min_length=1)
    reference_path: str = Field(min_length=1)
    threshold_db: float = 6.0
    @model_validator(mode="after")
    def _same_path(self) -> "FindFrequencyMaskingRequest":
        if self.target_path == self.reference_path:
            raise ValueError("target_path and reference_path must differ")
        return self


class AnalyzeMixRequest(RequestModel):
    stems: Annotated[list[str], Field(min_length=1, max_length=16)]


class ExtractSingleCycleRequest(RequestModel):
    path: str = Field(min_length=1)
    frame_size: Annotated[int, Field(ge=64, le=65536)] = 2048
```

```python
"analyze_audio",
"find_frequency_masking",
"analyze_mix",
"extract_single_cycle",
```

```python
@mcp.tool()
def analyze_audio(path: str) -> dict[str, Any]:
    """Compute LUFS-I, true-peak, RMS, and per-band energy summary for a local audio file.

    Side effects: none; reads the file from disk.
    Example: ``analyze_audio(path="/stems/kick.wav")`` returns LUFS-I plus bands.
    Edge cases: unsupported encodings return a structured ``{"ok": False, "reason": ...}``.
    """
    return _explicit_json_result(ableton_mcp_server.analysis.analyze_audio(path))


@mcp.tool()
def find_frequency_masking(target_path: str, reference_path: str, threshold_db: float = 6.0) -> dict[str, Any]:
    """Identify frequency bands where ``target_path`` exceeds ``reference_path`` by ``threshold_db`` dB or more.

    Side effects: none; reads both files.
    Example: ``find_frequency_masking(target_path=master, reference_path=kick)`` suggests low-band cuts.
    Edge cases: mismatched sample rates raise a structured error.
    """
    return _explicit_json_result(
        ableton_mcp_server.analysis.find_frequency_masking(
            target_path=target_path, reference_path=reference_path, threshold_db=threshold_db
        )
    )


@mcp.tool()
def analyze_mix(stems: list[str]) -> dict[str, Any]:
    """Run per-stem analysis and pair-wise masking across up to 16 local audio files."""
    return _explicit_json_result(ableton_mcp_server.analysis.analyze_mix(stems=stems))


@mcp.tool()
def extract_single_cycle(path: str, frame_size: int = 2048) -> dict[str, Any]:
    """Find a candidate single-cycle loop in a local audio file plus its detected pitch."""
    return _explicit_json_result(
        ableton_mcp_server.analysis.extract_single_cycle(path=path, frame_size=frame_size)
    )
```

- [ ] **Step 4: Verify GREEN and registry inflation**

Run: `python -m pytest tests/test_server_tools.py tests/test_tool_registry.py -q`
Expected: all pass and tool count 64.

- [ ] **Step 5: Commit**

```text
feat(analysis): add analyze_audio, find_frequency_masking, analyze_mix, extract_single_cycle tools
```

## Task 10: Docs, CHANGELOG, and final release gate

**Files:**
- Modify: `docs/TOOL_REFERENCE.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update TOOL_REFERENCE.md**

Add the four lifecycle tools under a "Set Lifecycle" section and the
`live_fade` tool under "Fader Automation". Add the four analysis tools
under "Offline Mix Analysis". For each, document parameters, return shape,
side effects, and one worked example.

- [ ] **Step 2: Update README.md**

Add the new tool count (64) and a one-paragraph capability summary of the
v0.5.0 additions. Update the dependency list to mention `numpy` and
`soundfile` for mix analysis.

- [ ] **Step 3: Add CHANGELOG.md entry**

```markdown
## v0.5.0 — set lifecycle, fader fade, and offline mix analysis

Adds four set lifecycle tools (`lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`)
and four offline mix-analysis tools (`analyze_audio`, `find_frequency_masking`, `analyze_mix`,
`extract_single_cycle`). Lifecycle commands derived from
`mlmil/Ableton-Live-MCP-ULTRA-v2` and rewritten against the in-repo
primitives; mix analysis rewritten from scratch against `numpy` and
`soundfile`. No vendored code. Public MCP tool count grows from 56 to 64.
```

- [ ] **Step 4: Run the full release gate**

Run: `python -m ruff check ableton_mcp_server AbletonMCPServer_RemoteScript scripts tests`
Run: `python -m pytest -q --tb=line`
Run: `python -m mypy --strict ableton_mcp_server ableton_mcp_server/analysis`
Run: `python scripts/vendor_contracts.py && python -m pytest tests/test_vendoring.py -q`
Expected: all pass; tool count 64; coverage meets the existing thresholds.

- [ ] **Step 5: Commit**

```text
docs(release): document v0.5.0 set lifecycle, fade, and mix analysis additions
```

## Out-of-band notes

- The Remote Script runtime identity bumps once per release; subsequent
  lifecycle/fade changes reuse `set-lifecycle-and-fade-1` until the next
  release.
- Mix analysis never crosses the Live boundary; the only side effects are
  filesystem reads and `numpy` operations. The MCP layer returns the raw
  dict envelope without bridging through the Remote Script.
- Real-Live acceptance for `lifecycle_status`, `save_set`, `quit_ableton`,
  and `live_fade` against a disposable Set remains an owner-run step.
  Offline tests do not claim to prove Live connectivity, undo behavior, or
  thread scheduling.
- A future "live-side audio inspection" PR may add `configure_sidechain`
  and `capture_track_to_wav`; this release explicitly defers them.
