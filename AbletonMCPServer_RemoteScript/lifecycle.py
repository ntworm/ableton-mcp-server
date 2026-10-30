"""Set lifecycle status, saving, the guarded quit workflow and the volume fade."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import suppress
from typing import Any

from ._contracts import ERROR_BAD_INPUT, ERROR_INVALID_PARAMS, ERROR_WRONG_TYPE
from .common import RemoteError, _required, _safe

# v0.5.0 — Set lifecycle. Informational fallback for WSL↔Windows: our transport
# cannot automate GUI clicks, so ``gui_workflow`` is descriptive only. Steps are
# kept generic enough that they apply to both macOS AppleScript and Windows GUI
# pathways (the upstream notes use AppleScript-specific phrasing; we use plain
# menu references instead).
GUI_LIFECYCLE_WORKFLOW: dict[str, list[str]] = {
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

# v0.5.0 — Fader fade. Live's mixer volume parameter sits below unity (0.85)
# so that 100% on the user-facing fader maps to 0dB. Treat 0.85 as the canonical
# unity value for target_percent→value conversion.
LIVE_FADE_UNITY_VALUE = 0.8500000238418579
LIVE_FADE_MAX_DURATION = 60.0
LIVE_FADE_DEFAULT_STEPS = 40


def cmd_lifecycle_status(song: Any, application: Any, _params: dict[str, Any]) -> dict[str, Any]:
    save_attr_names = ("save",)
    quit_attr_names = ("quit",)
    return {
        "song_save_attrs": [name for name in save_attr_names if hasattr(song, name)],
        "app_lifecycle_attrs": [name for name in quit_attr_names if hasattr(application, name)],
        "song_save_available": callable(getattr(song, "save", None)),
        "app_quit_available": callable(getattr(application, "quit", None)),
        "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
    }


def cmd_save_set(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Save the Live Set through ``Song.save()`` when the host exposes it.

    When ``Song.save`` is missing on the host, fall back to a structured GUI
    workflow. Set ``require_api=True`` to make the handler raise a
    ``BAD_INPUT`` ``RemoteError`` instead of returning the fallback — useful
    for callers that want to fail fast.
    """

    save = getattr(song, "save", None)
    if not callable(save):
        if params.get("require_api"):
            raise RemoteError(
                ERROR_BAD_INPUT,
                "Live Song object does not expose save(); use the GUI save workflow",
            )
        return {
            "saved": False,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    result = save()
    return {"saved": True, "api_available": True, "result": result}


def quit_ableton_steps(
    song: Any,
    application: Any,
    control_surface: Any,
    params: dict[str, Any],
) -> dict[str, Any]:
    save_attr = getattr(song, "save", None)
    if params.get("save", True) and callable(save_attr):
        save_attr()
        saved = True
    elif params.get("save", True):
        saved = False
        if not params.get("force_without_save"):
            return {
                "quit_requested": False,
                "saved_first": False,
                "reason": (
                    "save API unavailable; pass force_without_save:true to quit anyway "
                    "or use the GUI workflow"
                ),
                "gui_workflow": GUI_LIFECYCLE_WORKFLOW,
            }
    else:
        saved = False
    quit_fn = getattr(application, "quit", None)
    if not callable(quit_fn):
        return {
            "quit_requested": False,
            "saved_first": saved,
            "api_available": False,
            "gui_workflow": GUI_LIFECYCLE_WORKFLOW["quit"],
            "gui_notes": GUI_LIFECYCLE_WORKFLOW["notes"],
        }
    if not hasattr(control_surface, "schedule_message"):
        return {
            "quit_requested": False,
            "saved_first": saved,
            "api_available": True,
            "reason": "Live control surface does not expose schedule_message",
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


def _fade_volume_param(track: Any) -> Any:
    """Return the mixer volume parameter of ``track``."""
    mixer = getattr(track, "mixer_device", None)
    if mixer is None:
        raise RemoteError(ERROR_WRONG_TYPE, "Track has no mixer_device")
    param = getattr(mixer, "volume", None)
    if param is None:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Track has no mixer_device.volume parameter",
        )
    return param


def _fade_target_value(params: dict[str, Any]) -> float:
    """Return the fade target value from ``target_value`` or ``target_percent``."""
    if params.get("target_value") is not None:
        return float(params["target_value"])
    if params.get("target_percent") is not None:
        percent = float(params["target_percent"])
        if percent < 0.0:
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "target_percent must be >= 0",
            )
        if percent > 100.0 and not params.get("allow_over_unity"):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "target_percent above 100 (unity) requires allow_over_unity:true",
            )
        return (percent / 100.0) * LIVE_FADE_UNITY_VALUE
    raise RemoteError(
        ERROR_INVALID_PARAMS,
        "Provide target_percent or target_value",
    )


def _fade_duration(params: dict[str, Any]) -> float:
    """Return the fade duration in seconds."""
    duration_raw = params.get("duration")
    duration = float(10.0 if duration_raw is None else duration_raw)
    if duration < 0.0 or duration > LIVE_FADE_MAX_DURATION:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "duration must be between 0 and %s seconds" % LIVE_FADE_MAX_DURATION,
        )
    return duration


def _fade_steps(params: dict[str, Any]) -> int:
    """Return the number of fade steps."""
    steps_raw = params.get("steps")
    steps = int(LIVE_FADE_DEFAULT_STEPS if steps_raw is None else steps_raw)
    if steps < 1:
        raise RemoteError(ERROR_INVALID_PARAMS, "steps must be >= 1")
    return steps


def _fade_curve(params: dict[str, Any]) -> str:
    """Return the fade curve name."""
    curve = params.get("curve") or "smoothstep"
    if curve not in ("smoothstep", "linear"):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "curve must be smoothstep or linear",
        )
    return curve


def _fade_write_values(
    param: Any,
    start: float,
    target: float,
    curve: str,
    duration: float,
    steps: int,
    effective_clock: Callable[[], float],
) -> Generator[None, None, None]:
    """Write the fade values to ``param``, yielding between the writes."""
    if duration == 0.0:
        # ``duration=0`` short-circuits: still write the target value so the
        # documented contract holds, but never wait.
        t = 1.0
        shaped = t * t * (3.0 - 2.0 * t) if curve == "smoothstep" else t
        param.value = start + (target - start) * shaped
        yield
    else:
        step_interval = duration / float(steps)
        for step in range(1, steps + 1):
            # Wait until the monotonic clock has advanced to this step's
            # deadline before writing the new value. Writes therefore land at
            # ``step * step_interval`` (i.e. ``0.25 / 0.50 / 0.75 / 1.00`` for
            # ``steps=4, duration=1``) — never earlier. We never call
            # ``time.sleep``; we yield so Live's ``update_display`` tick loop
            # runs other work. Blocking the Live main thread is forbidden by
            # an AST invariant in ``tests/test_transport_retry.py``. The RPC
            # timeout override in ``COMMAND_TIMEOUT_OVERRIDES`` leaves room
            # for long multi-step faders, but the work itself stays
            # responsive.
            deadline = effective_clock() + step_interval
            while effective_clock() < deadline:
                yield
            t = step / float(steps)
            shaped = t * t * (3.0 - 2.0 * t) if curve == "smoothstep" else t
            param.value = start + (target - start) * shaped


def _fade_result(
    track: Any, param: Any, curve: str, duration: float, steps: int, start: float, target: float
) -> dict[str, Any]:
    """Build the result of one fade."""
    final_value = float(param.value)
    result: dict[str, Any] = {
        "track": str(_safe(lambda: track.name, "")),
        "curve": curve,
        "duration": duration,
        "steps": steps,
        "start_value": start,
        "target_value": target,
        "final_value": final_value,
        "final_percent": round(final_value / LIVE_FADE_UNITY_VALUE * 100.0, 3),
    }
    with suppress(Exception):
        result["display"] = param.str_for_value(param.value)
    return result


def live_fade_steps(
    song: Any,
    _application: Any,
    params: dict[str, Any],
    *,
    clock: Callable[[], float] | None = None,
) -> Generator[None, None, dict[str, Any]]:
    """Interpolate one track's volume to a target value over ``duration`` seconds.

    The fade distributes its steps across the requested ``duration`` of
    monotonic-clock time and yields between writes so the Live UI tick
    (``update_display``) can keep scheduling other work. We deliberately do
    *not* call :func:`time.sleep` — sleeping on the Live main thread would
    freeze the GUI. Instead each step waits until its monotonic deadline
    before requesting the next ``yield``. ``duration=0`` short-circuits the
    wait entirely and finishes in a single Live tick.

    ``clock`` is injectable for tests; it defaults to :func:`time.monotonic`
    so production behaviour is unchanged. ``steps=1`` with ``duration>0``
    still waits the requested duration before finishing — it writes the
    target once and yields until the deadline.
    """

    track_index = _required(params, "track_index")
    track = song.tracks[int(track_index)]
    param = _fade_volume_param(track)
    target = _fade_target_value(params)
    minimum = float(getattr(param, "min", 0.0))
    maximum = float(getattr(param, "max", 1.0))
    target = max(minimum, min(target, maximum))
    duration = _fade_duration(params)
    steps = _fade_steps(params)
    curve = _fade_curve(params)
    start = float(param.value)
    effective_clock: Callable[[], float] = clock or time.monotonic
    yield from _fade_write_values(
        param,
        start,
        target,
        curve,
        duration,
        steps,
        effective_clock,
    )
    return _fade_result(track, param, curve, duration, steps, start, target)
