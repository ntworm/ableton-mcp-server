"""Clip property, track creation, warp, device loading and lifecycle tools."""

from __future__ import annotations

import json
from typing import Any

from . import device_insert, models
from . import server as _s
from .server import (
    mcp,
)


@mcp.tool()
def set_clip_properties(
    track_index: int,
    clip_index: int,
    loop_start: float | None = None,
    loop_end: float | None = None,
    name: str | None = None,
) -> Any:
    """Set and verify selected Session clip loop bounds or name.

    Side effects: changes one clip in one Live undo step.
    Example: ``set_clip_properties(0, 1, loop_end=8, name="Verse")`` edits a clip.
    Edge cases: the final loop interval must remain positive and non-empty.
    """
    return _s._remote(
        "set_clip_properties",
        models.SetClipPropertiesRequest(
            track_index=track_index,
            clip_index=clip_index,
            loop_start=loop_start,
            loop_end=loop_end,
            name=name,
        ),
        exclude_none=True,
    )


@mcp.tool()
def create_clip_automation(
    track_index: int,
    clip_index: int,
    parameter_name: str,
    automation_points: list[dict[str, float]],
    device_index: int | None = None,
) -> Any:
    """Replace one Session clip parameter envelope with verified breakpoints.

    Side effects: clears and rewrites one clip envelope in one Live undo step.
    Example: ``create_clip_automation(0, 1, "volume", [{"time": 0, "value": 0.5}])``.
    Edge cases: requires Session-clip automation APIs and accepts at most 500
    points. A parameter name carried by several devices of the track returns
    ``AMBIGUOUS_MATCH``; pass ``device_index`` to choose one. Envelopes are
    stepped, so a smooth ramp needs dense points — or use
    ``create_clip_automation_curve`` and let the server expand it.
    """
    payload: dict[str, Any] = {
        "track_index": track_index,
        "clip_index": clip_index,
        "parameter_name": parameter_name,
        "automation_points": automation_points,
    }
    if device_index is not None:
        payload["device_index"] = device_index
    request = models.CreateClipAutomationRequest.model_validate(payload)
    return _s._remote("create_clip_automation", request, exclude_none=True)


# ---------------------------------------------------------------------------
# v0.3.0 — Composition Diagnostics
# ---------------------------------------------------------------------------


@mcp.tool()
def get_composition_structure() -> Any:
    """Retrieve the full track layout, scene count, and composition properties.

    Side effects: none.
    Example: ``get_composition_structure()`` returns tracks, scenes, unnamed tracks.
    Edge cases: large Sets produce correspondingly large JSON results.
    """
    return _s._remote("get_composition_structure", models.GetCompositionStructureRequest())


@mcp.tool()
def diagnose_midi_clip(
    track_index: int,
    clip_index: int,
    scale_root: str | None = None,
    scale_type: str | None = None,
) -> Any:
    """Scan a MIDI clip for overlapping notes, notes outside scale, and quantization issues.

    Side effects: none.
    Example: ``diagnose_midi_clip(0, 0, "C", "major")`` checks scale conformance.
    Edge cases: audio clips return ``WRONG_TYPE``; omitting scale skips pitch analysis.
    """
    return _s._remote(
        "diagnose_midi_clip",
        models.DiagnoseMidiClipRequest(
            track_index=track_index,
            clip_index=clip_index,
            scale_root=scale_root,
            scale_type=scale_type,
        ),
    )


# ---------------------------------------------------------------------------
# v0.3.0 — Guarded Creative Mutations
# ---------------------------------------------------------------------------


@mcp.tool()
def create_midi_track(name: str = "MIDI Track", index: int | None = None) -> Any:
    """Create a new MIDI track inside Ableton Live under safe constraints.

    Side effects: mutates the Set by adding a track in one undo step.
    Example: ``create_midi_track("Bass")`` appends a named MIDI track.
    Edge cases: fails with ``TRACK_LIMIT_REACHED`` when ≥ 96 tracks exist.
    """
    return _s._remote(
        "create_midi_track",
        models.CreateMidiTrackRequest(name=name, index=index),
    )


@mcp.tool()
def create_audio_track(index: int = -1, name: str | None = None) -> Any:
    """Create a new audio track in Ableton Live.

    Side effects: mutates the Set by adding an audio track in one undo step.
    Example: ``create_audio_track(name="vocals")`` appends a named audio track;
    ``create_audio_track(index=2)`` inserts at position 2.
    Edge cases: raises ``LIVE_UNAVAILABLE`` when the Live host does not
    expose ``Song.create_audio_track``. Note: this audio variant does not
    reuse the 96-track ``TRACK_LIMIT_REACHED`` guard — Live itself enforces
    the per-host track cap.
    """
    return _s._remote(
        "create_audio_track",
        models.CreateAudioTrackRequest(index=index, name=name),
    )


@mcp.tool()
def rename_track(track_index: int, new_name: str) -> Any:
    """Rename a track in the Live Set.

    Side effects: mutates the track name in one undo step.
    Example: ``rename_track(0, "Drums")`` renames the first track.
    Edge cases: an out-of-range index returns ``INVALID_PARAMS``.
    """
    return _s._remote(
        "rename_track",
        models.RenameTrackRequest(track_index=track_index, new_name=new_name),
    )


# ---------------------------------------------------------------------------
# v0.3.0 — WebSocket Bridge: Warp & Devices
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_warp_state(track_index: int, clip_index: int) -> str:
    """Retrieve warping status, warp mode, and warp markers of an audio clip.

    Side effects: none. Routed via the Extension Host WebSocket bridge.
    Example: ``get_warp_state(1, 0)`` reads warp data from track 1, clip 0.
    Edge cases: requires the AbletonMCPServer Extension to be installed.
    """
    models.GetWarpStateRequest(track_index=track_index, clip_index=clip_index)
    result = await _s._remote_ws(
        "get_warp_state",
        {"track_index": track_index, "clip_index": clip_index},
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def set_warp_state(
    track_index: int,
    clip_index: int,
    warping: bool | None = None,
    warp_mode: str | None = None,
) -> str:
    """Modify warp parameters on an audio clip.

    Side effects: mutates warp state via the Extension Host.
    Example: ``set_warp_state(1, 0, warping=True, warp_mode="complex")``
    Edge cases: requires the AbletonMCPServer Extension to be installed.
    """
    request = models.SetWarpStateRequest(
        track_index=track_index,
        clip_index=clip_index,
        warping=warping,
        warp_mode=warp_mode,
    )
    result = await _s._remote_ws(
        "set_warp_state",
        request.model_dump(mode="json", exclude_none=True),
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def load_device_to_track(
    track_index: int,
    device_name: str | None = None,
    device_uri: str | None = None,
) -> str:
    """Load a built-in Live device where the track's chain accepts it.

    Side effects: reads the chain and Browser, then inserts via the Extension Host: MIDI
    effects after the MIDI effects, an instrument before the audio effects, audio last.
    Example: ``load_device_to_track(1, device_name="Arpeggiator")``; ``device_uri`` is deprecated.
    Edge cases: a second instrument is refused with ``BAD_INPUT``; Live refuses unknown names
    and instruments or MIDI effects on audio tracks (Known Bugs, R).
    """
    request = models.LoadDeviceToTrackRequest(
        track_index=track_index,
        device_name=device_name,
        device_uri=device_uri,
    )
    params = device_insert.insert_params(
        _s.get_client().call, request.track_index, request.resolved_name
    )
    result = await _s._remote_ws("load_device_to_track", params)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# v0.5.0 — Set Lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def lifecycle_status() -> Any:
    """Read Live save/quit API availability and return a GUI-workflow fallback.

    Side effects: none.
    Example: ``lifecycle_status()`` reports ``song_save_available`` and ``app_quit_available``.
    Edge cases: missing Live APIs degrade to ``False`` flags; never raises.
    """
    return _s._remote("lifecycle_status", models.GetLifecycleStatusRequest())


@mcp.tool()
def save_set(require_api: bool = False) -> Any:
    """Save the Live Set via Song.save() when exposed, otherwise return a GUI workflow.

    Side effects: invokes Song.save() in one undo step when available.
    Example: ``save_set(require_api=True)`` raises when the API is missing.
    Edge cases: missing API returns a structured GUI workflow response.
    """
    return _s._remote("save_set", models.SaveSetRequest(require_api=require_api))


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
    return _s._remote(
        "quit_ableton",
        models.QuitAbletonRequest(
            save=save,
            force_without_save=force_without_save,
            quit_delay_ticks=quit_delay_ticks,
        ),
    )


@mcp.tool()
def live_fade(
    track_index: int,
    target_percent: float | None = None,
    target_value: float | None = None,
    duration: float = 10.0,
    steps: int = 40,
    curve: str = "smoothstep",
    allow_over_unity: bool = False,
) -> Any:
    """Interpolate one track's mixer volume to a target value over ``duration`` seconds.

    Side effects: blocks the Live main thread for up to ``duration`` seconds plus
    steps; first such command in our bridge. Writes ``mixer_device.volume`` in
    one undo step.
    Example: ``live_fade(track_index=0, target_percent=0)`` ramps the first
    track to silence; ``live_fade(track_index=0, target_percent=120,
    allow_over_unity=True)`` exceeds unity and **may clip**.
    Edge cases: rejects ``duration`` above 60 seconds and ``target_percent``
    above 100 without ``allow_over_unity``. Provide exactly one of
    ``target_percent`` or ``target_value``.
    """
    return _s._remote(
        "live_fade",
        models.LiveFadeRequest(
            track_index=track_index,
            target_percent=target_percent,
            target_value=target_value,
            duration=duration,
            steps=steps,
            curve=curve,  # type: ignore[arg-type]
            allow_over_unity=allow_over_unity,
        ),
    )
