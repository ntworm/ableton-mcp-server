"""Ableton Live MIDI Remote Script for the Ableton MCP Server.

Socket work runs in background threads. Every Live Object Model access is
dispatched by :meth:`AbletonMCPServer.update_display` on Live's main thread.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import os
import queue
import re
import socket
import threading
import time
from collections.abc import Callable, Generator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from ._contracts import (
    ALLOWED_MUTATIONS,
    CUE_OPERATION_VERIFY_TICKS,
    CUE_TIME_TOLERANCE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ERROR_BAD_INPUT,
    ERROR_CUE_SNAPPED_TO_GRID,
    ERROR_INTERNAL_ERROR,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_PLAYHEAD_NOT_MOVED,
    ERROR_READ_ONLY_VIOLATION,
    ERROR_STALE_REFERENCE,
    ERROR_TIMEOUT,
    ERROR_TRACK_LIMIT_REACHED,
    ERROR_UNKNOWN_COMMAND,
    ERROR_WRONG_TYPE,
    PLAYHEAD_MOVE_RETRIES,
    READ_ONLY_COMMANDS,
    request_timeout_seconds,
)

# v0.5.0 — runtime identity tag surfaced in `get_bridge_status`.
# The base upstream did not ship one; v0.5.0 establishes the convention.
REMOTE_SCRIPT_RUNTIME_VERSION = "set-lifecycle-and-fade-1"

try:  # These modules only exist inside Ableton Live.
    import Live  # type: ignore[import-not-found]
    from ableton.v2.control_surface import ControlSurface  # type: ignore[import-not-found]
except ImportError:  # Local tests exercise the pure handlers without Live.
    Live = None  # type: ignore[assignment]

    class ControlSurface:  # type: ignore[no-redef]
        def __init__(self, c_instance: Any) -> None:
            self._c_instance = c_instance
            self.song = c_instance.song

        def update_display(self) -> None:
            return None

        def disconnect(self) -> None:
            return None

        def show_message(self, _message: str) -> None:
            return None


logger = logging.getLogger("AbletonMCPServer")
_VERBOSE = os.environ.get("ABLETON_MCP_SERVER_VERBOSE") == "1"
_MAX_FRAME_BYTES = 1024 * 1024


def _dbg(message: str) -> None:
    if _VERBOSE:
        logger.info("[MCP-Server] %s", message)


class RemoteError(Exception):
    """Structured error produced by a Remote Script handler."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint

    def to_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": str(self),
        }
        if self.hint:
            envelope["hint"] = self.hint
        return envelope


class PlayheadNotMovedError(RemoteError):
    def __init__(self, requested: float, actual: float, attempts: int) -> None:
        self.requested = requested
        self.actual = actual
        self.attempts = attempts
        super().__init__(
            ERROR_PLAYHEAD_NOT_MOVED,
            "Transport setter did not reach the requested value "
            "(asked=%s, got=%s after %s attempts)." % (requested, actual, attempts),
            "Live may be in a transitional state; retry after it settles.",
        )


class CueSnappedToGridError(RemoteError):
    def __init__(self, requested: float, actual: float) -> None:
        self.requested = requested
        self.actual = actual
        super().__init__(
            ERROR_CUE_SNAPPED_TO_GRID,
            "Live snapped the cue operation from requested %s to %s. "
            "The unintended grid operation was reversed." % (requested, actual),
            "Disable Arrangement Snap-to-Grid (Ctrl/Cmd+4) or use a grid-aligned time.",
        )


@dataclass(frozen=True)
class _FallbackMidiNoteSpecification:
    """Test-only stand-in for ``Live.Clip.MidiNoteSpecification``."""

    pitch: int
    start_time: float
    duration: float
    velocity: int
    mute: bool
    probability: float | None = None
    release_velocity: float | None = None
    velocity_deviation: float | None = None


def _midi_note_specification(**values: Any) -> Any:
    if Live is None:
        return _FallbackMidiNoteSpecification(**values)
    return Live.Clip.MidiNoteSpecification(**values)


def _safe(getter: Callable[[], Any], default: Any) -> Any:
    try:
        return getter()
    except (AttributeError, RuntimeError, TypeError):
        return default


def _required(params: dict[str, Any], name: str) -> Any:
    if name not in params:
        raise RemoteError(ERROR_INVALID_PARAMS, "Missing required parameter %r." % name)
    return params[name]


def _integer_param(params: dict[str, Any], name: str, minimum: int = 0) -> int:
    value = _required(params, name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r must be an integer >= %s." % (name, minimum),
        )
    return value


def _float_param(
    params: dict[str, Any],
    name: str,
    minimum: float = 0.0,
    maximum: float | None = None,
    strictly_positive: bool = False,
) -> float:
    raw = _required(params, name)
    if isinstance(raw, bool):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be numeric." % name)
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be numeric." % name) from error
    if not math.isfinite(value):
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be finite." % name)
    if strictly_positive and value <= minimum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be > %s." % (name, minimum))
    if not strictly_positive and value < minimum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be >= %s." % (name, minimum))
    if maximum is not None and value > maximum:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be <= %s." % (name, maximum))
    return value


def _string_param(params: dict[str, Any], name: str) -> str:
    value = _required(params, name)
    if not isinstance(value, str) or not value.strip():
        raise RemoteError(ERROR_BAD_INPUT, "Parameter %r must be a non-empty string." % name)
    return value.strip()


def _all_tracks(song: Any) -> list[Any]:
    return list(song.tracks) + list(song.return_tracks) + [song.master_track]


def _track_type(song: Any, track: Any) -> str:
    if track == song.master_track:
        return "master"
    if track in song.return_tracks:
        return "return"
    if bool(_safe(lambda: track.has_midi_input, False)):
        return "midi"
    return "audio"


def _track_at(song: Any, index: int) -> Any:
    tracks = _all_tracks(song)
    if index < 0 or index >= len(tracks):
        raise RemoteError(ERROR_INVALID_PARAMS, "Track index %s does not exist." % index)
    return tracks[index]


_TRACK_PATH_RE = re.compile(r"^track:(\d+)$")


def _resolve_track_id(song: Any, path_id: str) -> tuple[int, Any]:
    match = _TRACK_PATH_RE.fullmatch(path_id)
    if match is None:
        raise RemoteError(ERROR_BAD_INPUT, "Invalid track path-id %r." % path_id)
    index = int(match.group(1))
    tracks = _all_tracks(song)
    if index >= len(tracks):
        raise RemoteError(
            ERROR_STALE_REFERENCE,
            "Path-id %r no longer resolves to a track." % path_id,
            "Re-list tracks and use a fresh path-id.",
        )
    return index, tracks[index]


def _clip_slot(song: Any, track_index: int, clip_index: int) -> tuple[Any, Any]:
    track = _track_at(song, track_index)
    if _track_type(song, track) not in ("midi", "audio"):
        raise RemoteError(ERROR_WRONG_TYPE, "Track %s has no Session clip slots." % track_index)
    slots = _safe(lambda: track.clip_slots, None)
    if slots is None or clip_index < 0 or clip_index >= len(slots):
        raise RemoteError(ERROR_INVALID_PARAMS, "Clip slot %s does not exist." % clip_index)
    return track, slots[clip_index]


def _capture_parameter(parameter: Any, path_id: str) -> dict[str, Any]:
    return {
        "id": path_id,
        "name": str(_safe(lambda: parameter.name, "")),
        "value": float(_safe(lambda: parameter.value, 0.0)),
        "min": float(_safe(lambda: parameter.min, 0.0)),
        "max": float(_safe(lambda: parameter.max, 1.0)),
        "is_enabled": bool(_safe(lambda: parameter.is_enabled, True)),
        "is_quantized": bool(_safe(lambda: parameter.is_quantized, False)),
    }


def _capture_device(device: Any, track_index: int, device_index: int) -> dict[str, Any]:
    device_id = "track:%s/device:%s" % (track_index, device_index)
    parameters = [
        _capture_parameter(parameter, "%s/param:%s" % (device_id, parameter_index))
        for parameter_index, parameter in enumerate(_safe(lambda: device.parameters, []))
    ]
    return {
        "id": device_id,
        "name": str(_safe(lambda: device.name, "")),
        "class_name": str(_safe(lambda: device.class_name, "")),
        "is_active": bool(_safe(lambda: device.is_active, True)),
        "parameters": parameters,
    }


def _capture_clip_slot(slot: Any, track_index: int, slot_index: int) -> dict[str, Any]:
    slot_id = "track:%s/clipslot:%s" % (track_index, slot_index)
    has_clip = bool(_safe(lambda: slot.has_clip, False))
    clip = _safe(lambda: slot.clip, None) if has_clip else None
    return {
        "id": slot_id,
        "clip_id": "%s/clip" % slot_id if clip is not None else None,
        "index": slot_index,
        "has_clip": clip is not None,
        "clip_name": str(_safe(lambda: clip.name, "")) if clip is not None else "",
        "length_beats": float(_safe(lambda: clip.length, 0.0)) if clip is not None else 0.0,
        "is_playing": bool(_safe(lambda: clip.is_playing, False)) if clip is not None else False,
        "is_midi_clip": bool(_safe(lambda: clip.is_midi_clip, False))
        if clip is not None
        else False,
    }


def _capture_routing(track: Any) -> dict[str, str]:
    def display(attribute: str) -> str:
        route = _safe(lambda: getattr(track, attribute), None)
        return str(_safe(lambda: route.display_name, "")) if route is not None else ""

    return {
        "input_routing": display("input_routing_type"),
        "input_sub_routing": display("input_routing_channel"),
        "output_routing": display("output_routing_type"),
        "output_sub_routing": display("output_routing_channel"),
    }


def _capture_track(song: Any, track: Any, index: int) -> dict[str, Any]:
    track_kind = _track_type(song, track)
    mixer = _safe(lambda: track.mixer_device, None)
    devices = []
    clip_slots = []
    if track_kind in ("midi", "audio"):
        devices = [
            _capture_device(device, index, device_index)
            for device_index, device in enumerate(_safe(lambda: track.devices, []))
        ]
        clip_slots = [
            _capture_clip_slot(slot, index, slot_index)
            for slot_index, slot in enumerate(_safe(lambda: track.clip_slots, []))
        ]
    return {
        "id": "track:%s" % index,
        "index": index,
        "name": str(_safe(lambda: track.name, "")),
        "type": track_kind,
        "color": int(_safe(lambda: track.color, 0)),
        "mute": bool(_safe(lambda: track.mute, False)),
        "solo": bool(_safe(lambda: track.solo, False)),
        "arm": bool(_safe(lambda: track.arm, False)),
        "volume": float(_safe(lambda: mixer.volume.value, 1.0)),
        "panning": float(_safe(lambda: mixer.panning.value, 0.0)),
        "sends": [
            float(_safe(lambda send=send: send.value, 0.0))
            for send in _safe(lambda: mixer.sends, [])
        ],
        "devices": devices,
        "clip_slots": clip_slots,
    }


def _note_value(note: Any, name: str, default: Any) -> Any:
    if isinstance(note, dict):
        return note.get(name, default)
    return _safe(lambda: getattr(note, name), default)


def cmd_get_session_info(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return {
        "tempo": float(song.tempo),
        "signature_numerator": int(song.signature_numerator),
        "signature_denominator": int(song.signature_denominator),
        "is_playing": bool(song.is_playing),
        "current_song_time": float(song.current_song_time),
    }


def cmd_get_track_list(
    song: Any, _application: Any, _params: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "track:%s" % index,
            "index": index,
            "name": str(_safe(lambda track=track: track.name, "")),
            "type": _track_type(song, track),
        }
        for index, track in enumerate(_all_tracks(song))
    ]


def cmd_get_track_state(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    index = _integer_param(params, "track_index")
    return _capture_track(song, _track_at(song, index), index)


def cmd_get_locators(song: Any, _application: Any, _params: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": str(_safe(lambda cue=cue: cue.name, "")), "time": float(cue.time)}
        for cue in song.cue_points
    ]


def cmd_get_control_surfaces(
    _song: Any, application: Any, _params: dict[str, Any]
) -> list[dict[str, str]]:
    return [
        {"name": type(surface).__name__, "type": "remote_script"}
        for surface in _safe(lambda: application.control_surfaces, [])
        if surface is not None
    ]


def _scene_summary(scene: Any, index: int) -> dict[str, Any]:
    slots = list(_safe(lambda: scene.clip_slots, []))
    return {
        "index": index,
        "name": str(_safe(lambda: scene.name, "")),
        "is_empty": not any(bool(_safe(lambda slot=slot: slot.has_clip, False)) for slot in slots),
    }


def cmd_get_scenes(song: Any, _application: Any, _params: dict[str, Any]) -> list[dict[str, Any]]:
    return [_scene_summary(scene, index) for index, scene in enumerate(song.scenes)]


def cmd_get_scene_state(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    index = _integer_param(params, "scene_index")
    if index >= len(song.scenes):
        raise RemoteError(ERROR_INVALID_PARAMS, "Scene index %s does not exist." % index)
    scene = song.scenes[index]
    slots = []
    for track_index, slot in enumerate(_safe(lambda: scene.clip_slots, [])):
        item = _capture_clip_slot(slot, track_index, index)
        item["track_id"] = "track:%s" % track_index
        slots.append(item)
    result = _scene_summary(scene, index)
    result["clip_slots"] = slots
    return result


def cmd_get_project_metadata(
    song: Any, _application: Any, _params: dict[str, Any]
) -> dict[str, Any]:
    return {
        "song_name": str(_safe(lambda: song.name, "")),
        "file_path": str(_safe(lambda: song.file_path, "")),
        "is_dirty": bool(_safe(lambda: song.is_dirty, False)),
    }


def cmd_get_loop_settings(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return {
        "loop": bool(song.loop),
        "loop_start": float(song.loop_start),
        "loop_length": float(song.loop_length),
    }


def cmd_get_selected_context(
    song: Any, _application: Any, _params: dict[str, Any]
) -> dict[str, Any]:
    selected_track = _safe(lambda: song.view.selected_track, None)
    selected_scene = _safe(lambda: song.view.selected_scene, None)
    tracks = _all_tracks(song)
    track_index = tracks.index(selected_track) if selected_track in tracks else -1
    scenes = list(song.scenes)
    scene_index = scenes.index(selected_scene) if selected_scene in scenes else -1
    selected_device = _safe(lambda: selected_track.view.selected_device, None)
    devices = list(_safe(lambda: selected_track.devices, [])) if selected_track is not None else []
    device_index = devices.index(selected_device) if selected_device in devices else -1
    return {
        "selected_track_id": "track:%s" % track_index if track_index >= 0 else None,
        "selected_track_index": track_index,
        "selected_track_name": str(_safe(lambda: selected_track.name, "")),
        "selected_scene_index": scene_index,
        "selected_device_id": (
            "track:%s/device:%s" % (track_index, device_index)
            if track_index >= 0 and device_index >= 0
            else None
        ),
        "selected_device_index": device_index,
        "selected_device_name": str(_safe(lambda: selected_device.name, "")),
    }


def cmd_get_clip_summary(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    if _track_type(song, track) not in ("midi", "audio"):
        raise RemoteError(ERROR_WRONG_TYPE, "Track has no Session clip slots.")
    return [
        _capture_clip_slot(slot, track_index, index)
        for index, slot in enumerate(_safe(lambda: track.clip_slots, []))
    ]


def cmd_get_clip_notes(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        return []
    if not bool(_safe(lambda: clip.is_midi_clip, False)):
        raise RemoteError(ERROR_WRONG_TYPE, "Clip is not a MIDI clip.")
    notes = clip.get_notes_extended(0, 128, -8192.0, 16384.0)
    return [
        {
            "pitch": int(_note_value(note, "pitch", 0)),
            "start_time": float(_note_value(note, "start_time", 0.0)),
            "duration": float(_note_value(note, "duration", 0.0)),
            "velocity": int(_note_value(note, "velocity", 100)),
            "mute": bool(_note_value(note, "mute", False)),
        }
        for note in notes
    ]


def cmd_get_clip_info(
    song: Any,
    _application: Any,
    params: dict[str, Any],
) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None) if bool(_safe(lambda: slot.has_clip, False)) else None
    if clip is None:
        return {"has_clip": False, "clip_id": None}
    is_midi = bool(_safe(lambda: clip.is_midi_clip, False))
    return {
        "has_clip": True,
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
        "name": str(_safe(lambda: clip.name, "")),
        "length": float(_safe(lambda: clip.length, 0.0)),
        "loop_start": float(_safe(lambda: clip.loop_start, 0.0)),
        "loop_end": float(_safe(lambda: clip.loop_end, _safe(lambda: clip.length, 0.0))),
        "color_index": int(_safe(lambda: clip.color_index, -1)),
        "is_triggered": bool(_safe(lambda: clip.is_triggered, False)),
        "is_playing": bool(_safe(lambda: clip.is_playing, False)),
        "is_midi_clip": is_midi,
        "is_audio_clip": bool(_safe(lambda: clip.is_audio_clip, not is_midi)),
        "muted": bool(_safe(lambda: clip.muted, False)),
        "signature_numerator": int(_safe(lambda: clip.signature_numerator, 4)),
        "signature_denominator": int(_safe(lambda: clip.signature_denominator, 4)),
    }


def cmd_get_device_list(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    return [
        _capture_device(device, track_index, index)
        for index, device in enumerate(_safe(lambda: track.devices, []))
    ]


def cmd_get_parameter_value(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    track = _track_at(song, track_index)
    devices = list(_safe(lambda: track.devices, []))
    if device_index >= len(devices):
        raise RemoteError(ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index)
    for parameter_index, parameter in enumerate(
        _safe(lambda: devices[device_index].parameters, [])
    ):
        if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
            return _capture_parameter(
                parameter,
                "track:%s/device:%s/param:%s" % (track_index, device_index, parameter_index),
            )
    raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r was not found." % parameter_name)


def _set_parameter_value_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    requested = _float_param(params, "value", -1000000.0, 1000000.0)
    track = _track_at(song, track_index)
    devices = list(_safe(lambda: track.devices, []))
    if device_index >= len(devices):
        raise RemoteError(ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index)
    parameters = list(_safe(lambda: devices[device_index].parameters, []))
    parameter = next(
        (
            item
            for item in parameters
            if str(_safe(lambda item=item: item.name, "")) == parameter_name
        ),
        None,
    )
    if parameter is None:
        names = [str(_safe(lambda item=item: item.name, "")) for item in parameters]
        suggestions = difflib.get_close_matches(parameter_name, names, n=3, cutoff=0.5)
        suffix = " Did you mean: %s?" % ", ".join(suggestions) if suggestions else ""
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r was not found.%s" % (parameter_name, suffix),
        )
    if not bool(_safe(lambda: parameter.is_enabled, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Parameter %r is disabled." % parameter_name)
    minimum = float(_safe(lambda: parameter.min, 0.0))
    maximum = float(_safe(lambda: parameter.max, 1.0))
    if requested < minimum or requested > maximum:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Value %s is outside [%s, %s] for parameter %r."
            % (requested, minimum, maximum, parameter_name),
        )
    is_quantized = bool(_safe(lambda: parameter.is_quantized, False))
    observed = float(_safe(lambda: parameter.value, minimum))
    for _attempt in range(2):
        parameter.value = requested
        yield
        observed = float(parameter.value)
        if is_quantized or abs(observed - requested) < 1e-6:
            return {
                "target": requested,
                "value": observed,
                "is_quantized": is_quantized,
            }
    raise RemoteError(
        ERROR_INTERNAL_ERROR,
        "Parameter %r did not converge: target=%s observed=%s delta=%s."
        % (parameter_name, requested, observed, abs(observed - requested)),
    )


def cmd_get_routing(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, str]:
    return _capture_routing(_track_at(song, _integer_param(params, "track_index")))


def cmd_get_browser_categories(_song: Any, application: Any, _params: dict[str, Any]) -> list[str]:
    browser = application.browser
    names = (
        "sounds",
        "drums",
        "instruments",
        "audio_effects",
        "midi_effects",
        "plugins",
        "samples",
        "clips",
        "packs",
        "user_library",
    )
    return [
        name.replace("_", " ").title()
        for name in names
        if _safe(lambda name=name: getattr(browser, name), None) is not None
    ]


def cmd_search_browser(
    _song: Any,
    application: Any,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _string_param(params, "query").casefold()
    raw_limit = params.get("limit", 50)
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'limit' must be an integer.")
    limit = max(1, min(200, raw_limit))
    category_filter = params.get("category_type")
    if category_filter is not None:
        if not isinstance(category_filter, str) or not category_filter.strip():
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'category_type' must be text.")
        category_filter = category_filter.strip().casefold().replace(" ", "_")
    category_names = (
        "sounds",
        "drums",
        "instruments",
        "audio_effects",
        "midi_effects",
        "plugins",
        "samples",
        "clips",
        "packs",
        "user_library",
    )
    if category_filter is not None and category_filter not in category_names:
        raise RemoteError(ERROR_INVALID_PARAMS, "Unknown browser category %r." % category_filter)
    selected = (category_filter,) if category_filter is not None else category_names
    results: list[dict[str, Any]] = []
    visited: set[int] = set()
    budget = 5000
    for category in selected:
        root = _safe(lambda category=category: getattr(application.browser, category), None)
        if root is None:
            continue
        root_name = str(_safe(lambda root=root: root.name, category.replace("_", " ").title()))
        stack = [(root, [root_name], 0)]
        while stack and len(results) < limit and len(visited) < budget:
            item, path, depth = stack.pop()
            identity = id(item)
            if identity in visited:
                continue
            visited.add(identity)
            name = str(_safe(lambda item=item: item.name, ""))
            if depth > 0 and query in name.casefold():
                results.append(
                    {
                        "name": name,
                        "uri": str(_safe(lambda item=item: item.uri, "")),
                        "category": category,
                        "path": path,
                        "is_loadable": bool(_safe(lambda item=item: item.is_loadable, False)),
                    }
                )
            if depth >= 5:
                continue
            children = list(_safe(lambda item=item: item.children, []))[:500]
            for child in reversed(children):
                child_name = str(_safe(lambda child=child: child.name, ""))
                stack.append((child, [*path, child_name], depth + 1))
        if len(results) >= limit or len(visited) >= budget:
            break
    return results


def cmd_get_song_length(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, float]:
    return {"song_length": float(song.song_length)}


def cmd_live_find_track(
    song: Any, application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    query = _string_param(params, "query").casefold()
    return [
        track
        for track in cmd_get_track_list(song, application, {})
        if query in str(track["name"]).casefold()
    ]


def cmd_list_device_params(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_id = _string_param(params, "track_id")
    track_index, track = _resolve_track_id(song, track_id)
    return [
        {
            "device_id": "track:%s/device:%s" % (track_index, device_index),
            "device_name": str(_safe(lambda device=device: device.name, "")),
            "parameters": [
                _capture_parameter(
                    parameter,
                    "track:%s/device:%s/param:%s" % (track_index, device_index, parameter_index),
                )
                for parameter_index, parameter in enumerate(
                    _safe(lambda device=device: device.parameters, [])
                )
            ],
        }
        for device_index, device in enumerate(_safe(lambda: track.devices, []))
    ]


def _capture_snapshot(song: Any, application: Any) -> dict[str, Any]:
    tracks = [_capture_track(song, track, index) for index, track in enumerate(_all_tracks(song))]
    browser_categories = cmd_get_browser_categories(song, application, {})
    version_parts = [application.get_major_version(), application.get_minor_version()]
    bugfix = _safe(lambda: application.get_bugfix_version(), None)
    if bugfix is not None:
        version_parts.append(bugfix)
    return {
        "schema_version": 1,
        "captured_at_unix_ms": int(time.time() * 1000),
        "live_version": ".".join(str(part) for part in version_parts),
        "tempo": float(song.tempo),
        "signature_numerator": int(song.signature_numerator),
        "signature_denominator": int(song.signature_denominator),
        "is_playing": bool(song.is_playing),
        "current_song_time": float(song.current_song_time),
        "tracks": tracks,
        "control_surfaces": cmd_get_control_surfaces(song, application, {}),
        "browser_categories_count": len(browser_categories),
        "locators": cmd_get_locators(song, application, {}),
        "scenes": cmd_get_scenes(song, application, {}),
        "selected_context": cmd_get_selected_context(song, application, {}),
        "project_metadata": cmd_get_project_metadata(song, application, {}),
        "loop_settings": cmd_get_loop_settings(song, application, {}),
    }


def cmd_take_snapshot(song: Any, application: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return _capture_snapshot(song, application)


def _no_quantization_value() -> Any:
    if Live is None:
        return 0
    return Live.Song.Quantization.q_no_q


def _verified_playhead_steps(
    song: Any,
    target: float,
    *,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Advance a verified playhead write across Live UI ticks."""

    previous_quantization = song.clip_trigger_quantization
    actual = float(_safe(lambda: song.current_song_time, -1.0))
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        for attempt in range(retries):
            song.current_song_time = target
            yield
            actual = float(song.current_song_time)
            _dbg(
                "transport attribute=current_song_time asked=%s got=%s tick_attempt=%s"
                % (target, actual, attempt + 1)
            )
            if abs(actual - target) < CUE_TIME_TOLERANCE:
                return {"current_song_time": actual}
        raise PlayheadNotMovedError(target, actual, retries)
    finally:
        song.clip_trigger_quantization = previous_quantization


def _verified_boolean_steps(
    song: Any,
    *,
    attribute: str,
    expected: bool,
    setter: Callable[[], None],
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, bool]]:
    """Apply and confirm a deferred boolean state change on later UI ticks."""

    actual = bool(_safe(lambda: getattr(song, attribute), not expected))
    for attempt in range(retries):
        setter()
        yield
        actual = bool(getattr(song, attribute))
        _dbg(
            "state attribute=%s asked=%s got=%s tick_attempt=%s"
            % (attribute, expected, actual, attempt + 1)
        )
        if actual is expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
    )


def _verified_numeric_steps(
    song: Any,
    *,
    attribute: str,
    expected: float,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Compatibility wrapper for verified numeric Song attributes."""

    return (
        yield from _verified_attribute_numeric_steps(
            song,
            attribute=attribute,
            expected=expected,
            result_key=result_key,
            retries=retries,
        )
    )


def _verified_attribute_numeric_steps(
    target: Any,
    *,
    attribute: str,
    expected: float,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, float]]:
    """Apply and confirm a numeric attribute change on later UI ticks."""

    actual = float(_safe(lambda: getattr(target, attribute), -1.0))
    for attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = float(getattr(target, attribute))
        _dbg(
            "state attribute=%s asked=%s got=%s tick_attempt=%s"
            % (attribute, expected, actual, attempt + 1)
        )
        if abs(actual - expected) < CUE_TIME_TOLERANCE:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
    )


def _verified_attribute_boolean_steps(
    target: Any,
    *,
    attribute: str,
    expected: bool,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, bool]]:
    """Apply and confirm a boolean attribute change on later UI ticks."""

    actual = bool(_safe(lambda: getattr(target, attribute), not expected))
    for _attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = bool(getattr(target, attribute))
        if actual is expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %s after %s UI ticks."
        % (attribute, expected, retries),
    )


def _verified_attribute_string_steps(
    target: Any,
    *,
    attribute: str,
    expected: str,
    result_key: str,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, dict[str, str]]:
    """Apply and confirm a string attribute change on later UI ticks."""

    actual = str(_safe(lambda: getattr(target, attribute), ""))
    for _attempt in range(retries):
        setattr(target, attribute, expected)
        yield
        actual = str(getattr(target, attribute))
        if actual == expected:
            return {result_key: actual}
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "State setter for %s did not reach %r after %s UI ticks."
        % (attribute, expected, retries),
    )


def _find_cue(song: Any, target_time: float) -> Any:
    for cue in song.cue_points:
        if abs(float(cue.time) - target_time) < CUE_TIME_TOLERANCE:
            return cue
    return None


def _cue_snapshot(song: Any) -> dict[float, str]:
    return {float(cue.time): str(_safe(lambda cue=cue: cue.name, "")) for cue in song.cue_points}


def _snapshot_has_time(snapshot: dict[float, str], target_time: float) -> bool:
    return any(abs(cue_time - target_time) < CUE_TIME_TOLERANCE for cue_time in snapshot)


def _cue_snapshot_delta(
    before: dict[float, str], after: dict[float, str]
) -> tuple[list[float], list[float]]:
    added = [time for time in after if not _snapshot_has_time(before, time)]
    removed = [time for time in before if not _snapshot_has_time(after, time)]
    return added, removed


def _wait_for_cue_state_steps(
    song: Any,
    target_time: float,
    *,
    should_exist: bool,
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, Any]:
    """Wait for Live to apply one cue toggle without toggling a second time."""

    cue = _find_cue(song, target_time)
    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        _dbg(
            "cue_state time=%s expected=%s observed=%s tick_attempt=%s"
            % (target_time, should_exist, cue is not None, attempt + 1)
        )
        if (cue is not None) is should_exist:
            return cue
    action = "create" if should_exist else "delete"
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not %s the cue near %s after %s UI ticks."
        % (action, target_time, ticks),
    )


def _reverse_snapped_cue_toggle_steps(
    song: Any,
    *,
    requested_time: float,
    before: dict[float, str],
    after: dict[float, str],
) -> Generator[None, None, None]:
    """Reverse the one off-grid toggle before reporting a typed failure."""

    added, removed = _cue_snapshot_delta(before, after)
    if len(added) == 1 and not removed:
        actual_time = added[0]
        yield from _verified_cue_position_steps(song, target=actual_time)
        song.set_or_delete_cue()
        yield from _wait_for_cue_state_steps(song, actual_time, should_exist=False)
        raise CueSnappedToGridError(requested_time, actual_time)
    if len(removed) == 1 and not added:
        actual_time = removed[0]
        original_name = before[actual_time]
        yield from _verified_cue_position_steps(song, target=actual_time)
        song.set_or_delete_cue()
        restored = yield from _wait_for_cue_state_steps(song, actual_time, should_exist=True)
        yield from _verified_cue_name_steps(restored, original_name)
        raise CueSnappedToGridError(requested_time, actual_time)
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "Cue state changed unexpectedly after an off-grid toggle; automatic reversal was not safe.",
        "Inspect Arrangement locators before retrying.",
    )


def _wait_for_created_cue_steps(
    song: Any,
    target_time: float,
    *,
    before: dict[float, str],
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, Any]:
    """Observe exact creation or reverse a grid-snapped toggle."""

    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        if cue is not None:
            return cue
        after = _cue_snapshot(song)
        added, removed = _cue_snapshot_delta(before, after)
        _dbg(
            "cue_create time=%s observed=False added=%r removed=%r tick_attempt=%s"
            % (target_time, added, removed, attempt + 1)
        )
        if added or removed:
            yield from _reverse_snapped_cue_toggle_steps(
                song,
                requested_time=target_time,
                before=before,
                after=after,
            )
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not create the cue near %s after %s UI ticks."
        % (target_time, ticks),
    )


def _wait_for_deleted_cue_steps(
    song: Any,
    target_time: float,
    *,
    before: dict[float, str],
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, None]:
    """Observe exact deletion or reverse a grid-snapped toggle."""

    for attempt in range(ticks):
        yield
        cue = _find_cue(song, target_time)
        after = _cue_snapshot(song)
        added, removed = _cue_snapshot_delta(before, after)
        if cue is None:
            unexpected_removed = [
                time for time in removed if abs(time - target_time) >= CUE_TIME_TOLERANCE
            ]
            if not added and not unexpected_removed:
                return
            raise RemoteError(
                ERROR_LIVE_UNAVAILABLE,
                "Cue deletion changed additional locator state; automatic reversal was not safe.",
                "Inspect Arrangement locators before retrying.",
            )
        _dbg(
            "cue_delete time=%s observed=False added=%r removed=%r tick_attempt=%s"
            % (target_time, added, removed, attempt + 1)
        )
        if added or removed:
            yield from _reverse_snapped_cue_toggle_steps(
                song,
                requested_time=target_time,
                before=before,
                after=after,
            )
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "set_or_delete_cue() did not delete the cue near %s after %s UI ticks."
        % (target_time, ticks),
    )


def _verified_cue_name_steps(
    cue: Any,
    name: str,
    *,
    ticks: int = CUE_OPERATION_VERIFY_TICKS,
) -> Generator[None, None, None]:
    """Confirm a cue rename before reporting creation success."""

    cue.name = name
    actual = str(_safe(lambda: cue.name, ""))
    if actual == name:
        return
    for attempt in range(ticks):
        yield
        actual = str(_safe(lambda: cue.name, ""))
        _dbg("cue_name asked=%r got=%r tick_attempt=%s" % (name, actual, attempt + 1))
        if actual == name:
            return
        cue.name = name
    raise RemoteError(
        ERROR_LIVE_UNAVAILABLE,
        "Cue near %s was created but its name did not reach %r after %s UI ticks."
        % (float(cue.time), name, ticks),
    )


def _verified_cue_position_steps(
    song: Any,
    *,
    target: float,
    retries: int = PLAYHEAD_MOVE_RETRIES,
) -> Generator[None, None, None]:
    """Move the Arrangement playback position used by cue toggling."""

    actual = float(song.current_song_time)
    if abs(actual - target) < CUE_TIME_TOLERANCE:
        return
    for attempt in range(retries):
        song.current_song_time = target
        yield
        actual = float(song.current_song_time)
        _dbg("cue_position asked=%s got=%s tick_attempt=%s" % (target, actual, attempt + 1))
        if abs(actual - target) < CUE_TIME_TOLERANCE:
            return
    raise PlayheadNotMovedError(target, actual, retries)


def _create_cue_at_cursor_steps(
    song: Any, name: str, target_time: float
) -> Generator[None, None, dict[str, Any]]:
    existing = _find_cue(song, target_time)
    if existing is not None:
        yield from _verified_cue_name_steps(existing, name)
        return {"name": name, "time": float(existing.time), "action": "renamed"}

    before = _cue_snapshot(song)
    yield from _verified_cue_position_steps(
        song,
        target=target_time,
    )
    song.set_or_delete_cue()
    created = yield from _wait_for_created_cue_steps(
        song,
        target_time,
        before=before,
    )
    yield from _verified_cue_name_steps(created, name)
    return {"name": name, "time": float(created.time), "action": "created"}


def _create_cue_point_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    name = _string_param(params, "name")
    target_time = _float_param(params, "time", 0.0, 100000.0)

    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        return (yield from _create_cue_at_cursor_steps(song, name, target_time))
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization


def _delete_cue_point_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    target_time = _float_param(params, "time", 0.0, 100000.0)
    cue = _find_cue(song, target_time)
    if cue is None:
        return {"deleted": False, "reason": "no cue at time"}
    cue_time = float(cue.time)
    before = _cue_snapshot(song)
    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        yield from _verified_cue_position_steps(
            song,
            target=cue_time,
        )
        song.set_or_delete_cue()
        yield from _wait_for_deleted_cue_steps(song, cue_time, before=before)
        return {"deleted": True, "time": cue_time}
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization


def _bulk_create_cue_points_steps(
    song: Any, params: dict[str, Any]
) -> Generator[None, None, dict[str, Any]]:
    items = _required(params, "items")
    if not isinstance(items, list) or not items:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'items' must be a non-empty list.")
    results = []
    previous_time = float(song.current_song_time)
    previous_quantization = song.clip_trigger_quantization
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                error = RemoteError(ERROR_INVALID_PARAMS, "Cue item must be an object.")
                results.append({"index": index, **error.to_envelope()})
                continue
            try:
                name = _string_param(item, "name")
                target_time = _float_param(item, "time", 0.0, 100000.0)
                result = yield from _create_cue_at_cursor_steps(song, name, target_time)
                results.append({"index": index, "status": "ok", "result": result})
            except RemoteError as error:
                results.append({"index": index, **error.to_envelope()})
    finally:
        yield from _verified_cue_position_steps(
            song,
            target=previous_time,
        )
        song.clip_trigger_quantization = previous_quantization
    return {"results": results}


def cmd_create_clip(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    length = _float_param(params, "length_beats", 0.0, 100000.0, strictly_positive=True)
    track, slot = _clip_slot(song, track_index, clip_index)
    if _track_type(song, track) != "midi":
        raise RemoteError(ERROR_WRONG_TYPE, "create_clip requires a MIDI track.")
    if bool(_safe(lambda: slot.has_clip, False)):
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is not empty.")
    slot.create_clip(length)
    return {
        "created": True,
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
        "length_beats": length,
    }


def cmd_fire_clip(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _track, slot = _clip_slot(song, track_index, clip_index)
    if not bool(_safe(lambda: slot.has_clip, False)):
        raise RemoteError(ERROR_BAD_INPUT, "Cannot fire an empty clip slot.")
    slot.fire()
    return {"fired": True, "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index)}


def cmd_delete_clip(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _track, slot = _clip_slot(song, track_index, clip_index)
    if not bool(_safe(lambda: slot.has_clip, False)):
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    slot.delete_clip()
    return {
        "deleted": True,
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }


def cmd_fire_scene(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    scene_index = _integer_param(params, "scene_index")
    scenes = list(_safe(lambda: song.scenes, []))
    if scene_index >= len(scenes):
        raise RemoteError(ERROR_INVALID_PARAMS, "Scene index %s does not exist." % scene_index)
    scene = scenes[scene_index]
    scene.fire()
    return {
        "fired": True,
        "scene_index": scene_index,
        "name": str(_safe(lambda: scene.name, "")),
    }


def _clear_clip_notes_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    if not bool(_safe(lambda: clip.is_midi_clip, False)):
        raise RemoteError(ERROR_WRONG_TYPE, "clear_clip_notes requires a MIDI clip.")
    before = len(list(clip.get_notes_extended(0, 128, -8192.0, 16384.0)))
    length = float(_safe(lambda: clip.length, 0.0))
    clip.remove_notes_extended(0, 128, 0.0, max(1.0, length + 1.0))
    yield
    after = len(list(clip.get_notes_extended(0, 128, -8192.0, 16384.0)))
    return {
        "cleared": True,
        "notes_removed": max(0, before - after),
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }


def _set_track_property_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    property_name = _string_param(params, "property")
    if property_name not in ("mute", "solo", "arm"):
        raise RemoteError(ERROR_BAD_INPUT, "Unsupported track property %r." % property_name)
    value = _required(params, "value")
    if not isinstance(value, bool):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'value' must be boolean.")
    track = _track_at(song, track_index)
    if property_name == "arm" and _track_type(song, track) not in ("midi", "audio"):
        raise RemoteError(ERROR_WRONG_TYPE, "Only MIDI and audio tracks can be armed.")
    observed = yield from _verified_attribute_boolean_steps(
        track,
        attribute=property_name,
        expected=value,
        result_key="value",
    )
    return {"property": property_name, "value": observed["value"]}


def _set_clip_properties_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    requested_names = [name for name in ("loop_start", "loop_end", "name") if name in params]
    if not requested_names:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "At least one of loop_start, loop_end, or name is required.",
        )
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    current_start = float(_safe(lambda: clip.loop_start, 0.0))
    current_end = float(_safe(lambda: clip.loop_end, _safe(lambda: clip.length, 0.0)))
    requested_start = (
        _float_param(params, "loop_start", 0.0, 100000.0)
        if "loop_start" in params
        else None
    )
    requested_end = (
        _float_param(params, "loop_end", 0.0, 100000.0)
        if "loop_end" in params
        else None
    )
    requested_name = _string_param(params, "name") if "name" in params else None
    final_start = requested_start if requested_start is not None else current_start
    final_end = requested_end if requested_end is not None else current_end
    if final_start >= final_end:
        raise RemoteError(ERROR_BAD_INPUT, "loop_start must be less than loop_end.")
    result: dict[str, Any] = {}
    numeric_order = ["loop_start", "loop_end"]
    if requested_start is not None and requested_end is not None and final_start >= current_end:
        numeric_order.reverse()
    for attribute in numeric_order:
        expected = requested_start if attribute == "loop_start" else requested_end
        if expected is None:
            continue
        observed = yield from _verified_attribute_numeric_steps(
            clip,
            attribute=attribute,
            expected=expected,
            result_key=attribute,
        )
        result.update(observed)
    if requested_name is not None:
        observed_name = yield from _verified_attribute_string_steps(
            clip,
            attribute="name",
            expected=requested_name,
            result_key="name",
        )
        result.update(observed_name)
    result["clip_id"] = "track:%s/clipslot:%s/clip" % (track_index, clip_index)
    return result


def _automation_parameter(track: Any, parameter_name: str) -> Any:
    normalized = parameter_name.casefold().replace(" ", "_")
    mixer = _safe(lambda: track.mixer_device, None)
    if normalized == "volume":
        return _safe(lambda: mixer.volume, None)
    if normalized in ("pan", "panning"):
        return _safe(lambda: mixer.panning, None)
    send_match = re.fullmatch(r"send_([a-h])", normalized)
    if send_match is not None:
        index = ord(send_match.group(1)) - ord("a")
        sends = list(_safe(lambda: mixer.sends, []))
        return sends[index] if index < len(sends) else None
    for device in _safe(lambda: track.devices, []):
        for parameter in _safe(lambda device=device: device.parameters, []):
            if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
                return parameter
    return None


def _create_clip_automation_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    parameter_name = _string_param(params, "parameter_name")
    raw_points = _required(params, "automation_points")
    if not isinstance(raw_points, list) or not raw_points or len(raw_points) > 500:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "automation_points must contain between 1 and 500 points.",
        )
    track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    if not bool(_safe(lambda: clip.is_session_clip, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Automation is limited to Session clips.")
    parameter = _automation_parameter(track, parameter_name)
    if parameter is None:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r was not found." % parameter_name)
    if not bool(_safe(lambda: parameter.is_enabled, True)):
        raise RemoteError(ERROR_WRONG_TYPE, "Parameter %r is disabled." % parameter_name)
    minimum = float(_safe(lambda: parameter.min, 0.0))
    maximum = float(_safe(lambda: parameter.max, 1.0))
    points: list[tuple[float, float]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Each automation point must be an object.")
        point_time = _float_param(raw_point, "time", 0.0, 100000.0)
        value = _float_param(raw_point, "value", -1000000.0, 1000000.0)
        if value < minimum or value > maximum:
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Automation value %s is outside [%s, %s] for parameter %r."
                % (value, minimum, maximum, parameter_name),
            )
        points.append((point_time, value))
    points.sort(key=lambda point: point[0])
    envelope_getter = _safe(lambda: clip.automation_envelope_for_parameter, None)
    clear_envelope = _safe(lambda: clip.clear_envelope, None)
    if not callable(envelope_getter) or not callable(clear_envelope):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose the clip automation envelope API.",
        )
    clear_envelope(parameter)
    envelope = envelope_getter(parameter)
    insert_step = _safe(lambda: envelope.insert_step, None)
    if not callable(insert_step):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose automation envelope insertion.",
        )
    for point_time, value in points:
        insert_step(point_time, 0.0, value)
    yield
    if not bool(_safe(lambda: clip.has_envelopes, False)):
        raise RemoteError(ERROR_LIVE_UNAVAILABLE, "Clip automation write was not observed.")
    return {
        "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
        "points_written": len(points),
        "times": [point_time for point_time, _value in points],
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }


def cmd_add_notes_to_clip(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    raw_notes = _required(params, "notes")
    if not isinstance(raw_notes, list) or not raw_notes:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'notes' must be a non-empty list.")
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None or not bool(_safe(lambda: clip.is_midi_clip, False)):
        raise RemoteError(ERROR_WRONG_TYPE, "add_notes_to_clip requires a MIDI clip.")
    notes = []
    for raw_note in raw_notes:
        if not isinstance(raw_note, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Each note must be an object.")
        pitch = _integer_param(raw_note, "pitch")
        velocity = int(raw_note.get("velocity", 100))
        if pitch > 127 or velocity < 1 or velocity > 127:
            raise RemoteError(ERROR_BAD_INPUT, "MIDI pitch and velocity must be in range.")
        note_values: dict[str, Any] = {
            "pitch": pitch,
            "start_time": _float_param(raw_note, "start_time", 0.0, 100000.0),
            "duration": _float_param(
                raw_note,
                "duration",
                0.0,
                100000.0,
                strictly_positive=True,
            ),
            "velocity": velocity,
            "mute": bool(raw_note.get("mute", False)),
        }
        extended_ranges = {
            "probability": (0.0, 1.0),
            "release_velocity": (0.0, 127.0),
            "velocity_deviation": (-127.0, 127.0),
        }
        for field_name, (minimum, maximum) in extended_ranges.items():
            if field_name in raw_note and raw_note[field_name] is not None:
                note_values[field_name] = _float_param(
                    raw_note,
                    field_name,
                    minimum,
                    maximum,
                )
        try:
            note = _midi_note_specification(**note_values)
        except (AttributeError, TypeError) as error:
            raise RemoteError(
                ERROR_LIVE_UNAVAILABLE,
                "Live runtime does not support the requested MIDI note expression fields.",
            ) from error
        notes.append(note)
    note_ids = clip.add_new_notes(tuple(notes))
    return {
        "added": len(notes),
        "note_ids": [int(note_id) for note_id in note_ids],
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }


# ---------------------------------------------------------------------------
# v0.3.0 — Composition Diagnostics
# ---------------------------------------------------------------------------

_SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": list(range(12)),
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ENHARMONIC = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _note_name_to_number(name):
    # type: (str) -> int
    resolved = _ENHARMONIC.get(name, name)
    return _NOTE_NAMES.index(resolved)


def cmd_get_composition_structure(
    song,
    _application,
    _params,
):
    # type: (Any, Any, dict[str, Any]) -> dict[str, Any]
    tracks = []
    unnamed_tracks = []
    for index, track in enumerate(_all_tracks(song)):
        kind = _track_type(song, track)
        name = str(_safe(lambda track=track: track.name, ""))
        has_clips = False
        clip_count = 0
        if kind in ("midi", "audio"):
            for slot in _safe(lambda track=track: track.clip_slots, []):
                if bool(_safe(lambda slot=slot: slot.has_clip, False)):
                    has_clips = True
                    clip_count += 1
        entry = {
            "id": "track:%s" % index,
            "index": index,
            "name": name,
            "type": kind,
            "color": int(_safe(lambda track=track: track.color, 0)),
            "has_clips": has_clips,
            "clip_count": clip_count,
            "device_count": len(list(_safe(lambda track=track: track.devices, []))),
        }
        tracks.append(entry)
        default_names = ("", "MIDI", "Audio", "Master", "A-Return", "B-Return")
        if not name or name.startswith("Track ") or name in default_names:
            unnamed_tracks.append("track:%s" % index)

    return {
        "tracks": tracks,
        "track_count": len(tracks),
        "scenes_count": len(list(song.scenes)),
        "tempo": float(song.tempo),
        "unnamed_tracks": unnamed_tracks,
        "unnamed_tracks_count": len(unnamed_tracks),
    }


def cmd_diagnose_midi_clip(
    song,
    _application,
    params,
):
    # type: (Any, Any, dict[str, Any]) -> dict[str, Any]
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    scale_root = params.get("scale_root")  # optional
    scale_type = params.get("scale_type")  # optional

    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        return {
            "has_overlaps": False,
            "overlaps_count": 0,
            "notes_outside_scale": [],
            "timing_drift_detected": False,
            "recommendations": ["Clip slot is empty."],
            "note_count": 0,
        }

    if not bool(_safe(lambda: clip.is_midi_clip, False)):
        raise RemoteError(ERROR_WRONG_TYPE, "Clip is not a MIDI clip.")

    raw_notes = clip.get_notes_extended(0, 128, -8192.0, 16384.0)
    notes = []
    for note in raw_notes:
        notes.append(
            {
                "pitch": int(_note_value(note, "pitch", 0)),
                "start_time": float(_note_value(note, "start_time", 0.0)),
                "duration": float(_note_value(note, "duration", 0.0)),
                "velocity": int(_note_value(note, "velocity", 100)),
                "mute": bool(_note_value(note, "mute", False)),
            }
        )

    # --- Overlap Detection ---
    overlaps_count = 0
    by_pitch = {}  # type: dict[int, list[dict[str, Any]]]
    for note in notes:
        by_pitch.setdefault(note["pitch"], []).append(note)
    for pitch_notes in by_pitch.values():
        sorted_notes = sorted(pitch_notes, key=lambda n: n["start_time"])
        for i in range(len(sorted_notes) - 1):
            cur = sorted_notes[i]
            nxt = sorted_notes[i + 1]
            if nxt["start_time"] < cur["start_time"] + cur["duration"]:
                overlaps_count += 1

    # --- Scale Conformance ---
    notes_outside_scale = []  # type: list[dict[str, Any]]
    if scale_root and scale_type:
        try:
            root_num = _note_name_to_number(scale_root)
        except (ValueError, IndexError):
            root_num = None
        intervals = _SCALE_INTERVALS.get(scale_type.lower())
        if root_num is not None and intervals is not None:
            scale_pitches = set((root_num + i) % 12 for i in intervals)
            for note in notes:
                pc = note["pitch"] % 12
                if pc not in scale_pitches:
                    notes_outside_scale.append(
                        {
                            "pitch": note["pitch"],
                            "start_time": note["start_time"],
                            "note_name": _NOTE_NAMES[pc],
                        }
                    )

    # --- Timing Drift Detection ---
    timing_drift_detected = False
    grid_values = [0.25, 0.5, 1.0]  # 1/16, 1/8, 1/4 beats
    drift_threshold = 0.01
    if notes:
        drift_count = 0
        for note in notes:
            t = note["start_time"]
            aligned_to_any = False
            for grid in grid_values:
                remainder = t % grid
                if remainder < drift_threshold or (grid - remainder) < drift_threshold:
                    aligned_to_any = True
                    break
            if not aligned_to_any:
                drift_count += 1
        timing_drift_detected = drift_count > len(notes) * 0.15

    # --- Recommendations ---
    recommendations = []
    if overlaps_count > 0:
        recommendations.append(
            "%s overlapping note pair(s) found. Consider quantizing or removing duplicates."
            % overlaps_count
        )
    if notes_outside_scale:
        recommendations.append(
            "%s note(s) outside the %s %s scale."
            % (len(notes_outside_scale), scale_root, scale_type)
        )
    if timing_drift_detected:
        recommendations.append(
            "Timing drift detected; some notes are not aligned to standard grid values."
        )
    if not recommendations:
        recommendations.append("No issues found.")

    return {
        "note_count": len(notes),
        "has_overlaps": overlaps_count > 0,
        "overlaps_count": overlaps_count,
        "notes_outside_scale": notes_outside_scale,
        "timing_drift_detected": timing_drift_detected,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# v0.3.0 — Guarded Creative Mutations
# ---------------------------------------------------------------------------

_MAX_TRACKS = 96


def cmd_create_midi_track(
    song,
    _application,
    params,
):
    # type: (Any, Any, dict[str, Any]) -> dict[str, Any]
    name = params.get("name", "MIDI Track")
    index = params.get("index")  # None means append
    current_count = len(list(song.tracks))
    if current_count >= _MAX_TRACKS:
        raise RemoteError(
            ERROR_TRACK_LIMIT_REACHED,
            "Cannot create track: set already has %s tracks (limit=%s)."
            % (current_count, _MAX_TRACKS),
            "Remove unused tracks before creating new ones.",
        )
    insert_at = index if index is not None else -1
    song.create_midi_track(insert_at)
    new_track = song.tracks[-1] if insert_at == -1 else song.tracks[insert_at]
    if name:
        new_track.name = str(name)
    new_index = list(song.tracks).index(new_track)
    return {
        "status": "created",
        "track_id": "track:%s" % new_index,
        "track_index": new_index,
        "name": str(new_track.name),
    }


def cmd_rename_track(
    song,
    _application,
    params,
):
    # type: (Any, Any, dict[str, Any]) -> dict[str, Any]
    track_index = _integer_param(params, "track_index")
    new_name = _string_param(params, "new_name")
    track = _track_at(song, track_index)
    old_name = str(_safe(lambda: track.name, ""))
    track.name = new_name
    return {
        "track_id": "track:%s" % track_index,
        "old_name": old_name,
        "new_name": str(track.name),
    }


CommandHandler = Callable[[Any, Any, dict[str, Any]], Any]

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


def live_fade_steps(
    song: Any,
    _application: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Interpolate one track's volume to a target value over ``duration`` seconds.

    The first command in our bridge that deliberately blocks the Live main
    thread. ``duration`` is bounded at :data:`LIVE_FADE_MAX_DURATION` and each
    step yields to give Live's UI a chance to schedule other work.
    """

    track_index = _required(params, "track_index")
    track = song.tracks[int(track_index)]
    mixer = getattr(track, "mixer_device", None)
    if mixer is None:
        raise RemoteError(ERROR_WRONG_TYPE, "Track has no mixer_device")
    param = getattr(mixer, "volume", None)
    if param is None:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Track has no mixer_device.volume parameter",
        )
    if params.get("target_value") is not None:
        target = float(params["target_value"])
    elif params.get("target_percent") is not None:
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
        target = (percent / 100.0) * LIVE_FADE_UNITY_VALUE
    else:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Provide target_percent or target_value",
        )
    minimum = float(getattr(param, "min", 0.0))
    maximum = float(getattr(param, "max", 1.0))
    target = max(minimum, min(target, maximum))
    duration_raw = params.get("duration")
    duration = float(10.0 if duration_raw is None else duration_raw)
    if duration < 0.0 or duration > LIVE_FADE_MAX_DURATION:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "duration must be between 0 and %s seconds" % LIVE_FADE_MAX_DURATION,
        )
    steps_raw = params.get("steps")
    steps = int(LIVE_FADE_DEFAULT_STEPS if steps_raw is None else steps_raw)
    if steps < 1:
        raise RemoteError(ERROR_INVALID_PARAMS, "steps must be >= 1")
    curve = params.get("curve") or "smoothstep"
    if curve not in ("smoothstep", "linear"):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "curve must be smoothstep or linear",
        )
    start = float(param.value)
    for step in range(1, steps + 1):
        t = step / float(steps)
        shaped = t * t * (3.0 - 2.0 * t) if curve == "smoothstep" else t
        param.value = start + (target - start) * shaped
        # Yield once per step so the Live UI tick loop can schedule other work
        # (and so the socket reader can drain incoming MCP requests) between
        # volume writes. We deliberately do NOT call ``time.sleep`` here —
        # blocking the Live main thread is forbidden by an AST invariant in
        # ``tests/test_transport_retry.py``. The RPC timeout override in
        # ``COMMAND_TIMEOUT_OVERRIDES`` leaves room for long multi-step faders,
        # but the work itself stays responsive.
        yield
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


COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "get_session_info": cmd_get_session_info,
    "get_track_list": cmd_get_track_list,
    "get_track_state": cmd_get_track_state,
    "get_locators": cmd_get_locators,
    "take_snapshot": cmd_take_snapshot,
    "get_control_surfaces": cmd_get_control_surfaces,
    "get_scenes": cmd_get_scenes,
    "get_scene_state": cmd_get_scene_state,
    "get_project_metadata": cmd_get_project_metadata,
    "get_loop_settings": cmd_get_loop_settings,
    "get_selected_context": cmd_get_selected_context,
    "get_clip_summary": cmd_get_clip_summary,
    "get_clip_notes": cmd_get_clip_notes,
    "get_clip_info": cmd_get_clip_info,
    "get_device_list": cmd_get_device_list,
    "get_parameter_value": cmd_get_parameter_value,
    "get_routing": cmd_get_routing,
    "get_browser_categories": cmd_get_browser_categories,
    "search_browser": cmd_search_browser,
    "get_song_length": cmd_get_song_length,
    "live_find_track": cmd_live_find_track,
    "list_device_params": cmd_list_device_params,
    "create_clip": cmd_create_clip,
    "fire_clip": cmd_fire_clip,
    "delete_clip": cmd_delete_clip,
    "fire_scene": cmd_fire_scene,
    "add_notes_to_clip": cmd_add_notes_to_clip,
    # v0.3.0
    "get_composition_structure": cmd_get_composition_structure,
    "diagnose_midi_clip": cmd_diagnose_midi_clip,
    "create_midi_track": cmd_create_midi_track,
    "rename_track": cmd_rename_track,
    # v0.5.0 — set lifecycle
    "lifecycle_status": cmd_lifecycle_status,
    "save_set": cmd_save_set,
    "quit_ableton": quit_ableton_steps,
    "live_fade": live_fade_steps,
}


def _begin_undo(target: Any) -> None:
    method = _safe(lambda: target.begin_undo_step, None)
    if not callable(method):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose begin_undo_step on the selected undo target.",
        )
    method()


def _end_undo(target: Any) -> None:
    method = _safe(lambda: target.end_undo_step, None)
    if not callable(method):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose end_undo_step on the selected undo target.",
        )
    method()


def _run_batch_steps(
    song: Any,
    application: Any,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, dict[str, Any]]:
    commands = _required(params, "commands")
    if not isinstance(commands, list) or not commands:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'commands' must be a non-empty list.")
    results = []
    completed = 0
    aborted_at = None
    for index, command in enumerate(commands):
        try:
            if not isinstance(command, dict):
                raise RemoteError(ERROR_INVALID_PARAMS, "Batch command must be an object.")
            command_type = command.get("type")
            command_params = command.get("params", {})
            if command_type == "run_batch":
                raise RemoteError(ERROR_BAD_INPUT, "run_batch cannot contain run_batch.")
            if command_type not in ALLOWED_MUTATIONS:
                raise RemoteError(
                    ERROR_READ_ONLY_VIOLATION,
                    "Batch command %r is not an allowed mutation." % command_type,
                )
            if not isinstance(command_params, dict):
                raise RemoteError(ERROR_INVALID_PARAMS, "Batch command params must be an object.")
            result = yield from _command_steps(
                song,
                application,
                str(command_type),
                command_params,
                manage_undo=False,
                undo_target=undo_target,
                control_surface=control_surface,
            )
            results.append({"index": index, "status": "ok", "result": result})
            completed += 1
        except RemoteError as error:
            results.append({"index": index, **error.to_envelope()})
            aborted_at = index
            break
        except Exception as error:
            wrapped = RemoteError(ERROR_INTERNAL_ERROR, str(error))
            results.append({"index": index, **wrapped.to_envelope()})
            aborted_at = index
            break
    return {
        "results": results,
        "completed": completed,
        "aborted_at": aborted_at,
        "rolled_back": False,
    }


def _dispatch_command_steps(
    song: Any,
    application: Any,
    normalized: str,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    if normalized == "run_batch":
        return (
            yield from _run_batch_steps(
                song, application, params, undo_target, control_surface
            )
        )
    if normalized == "quit_ableton":
        # Give Live's UI thread one cycle before scheduling application quit.
        yield
    if normalized == "create_cue_point":
        return (yield from _create_cue_point_steps(song, params))
    if normalized == "bulk_create_cue_points":
        return (yield from _bulk_create_cue_points_steps(song, params))
    if normalized == "delete_cue_point":
        return (yield from _delete_cue_point_steps(song, params))
    if normalized == "set_current_song_time":
        target = _float_param(params, "time", 0.0, 100000.0)
        return (yield from _verified_playhead_steps(song, target))
    if normalized == "set_tempo":
        tempo = _float_param(params, "tempo", 20.0, 999.0)
        return (
            yield from _verified_numeric_steps(
                song,
                attribute="tempo",
                expected=tempo,
                result_key="tempo",
            )
        )
    if normalized == "set_parameter_value":
        return (yield from _set_parameter_value_steps(song, params))
    if normalized == "clear_clip_notes":
        return (yield from _clear_clip_notes_steps(song, params))
    if normalized == "set_track_property":
        return (yield from _set_track_property_steps(song, params))
    if normalized == "set_clip_properties":
        return (yield from _set_clip_properties_steps(song, params))
    if normalized == "create_clip_automation":
        return (yield from _create_clip_automation_steps(song, params))
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
    if normalized == "stop_playback":
        return (
            yield from _verified_boolean_steps(
                song,
                attribute="is_playing",
                expected=False,
                setter=song.stop_playing,
                result_key="is_playing",
            )
        )
    if normalized == "set_loop_start":
        start = _float_param(params, "start_beat", 0.0, 100000.0)
        return (
            yield from _verified_numeric_steps(
                song,
                attribute="loop_start",
                expected=start,
                result_key="loop_start",
            )
        )
    if normalized == "set_loop_length":
        length = _float_param(params, "length_beats", 0.0, 100000.0, strictly_positive=True)
        return (
            yield from _verified_numeric_steps(
                song,
                attribute="loop_length",
                expected=length,
                result_key="loop_length",
            )
        )
    if normalized == "set_loop":
        enabled = _required(params, "enabled")
        if not isinstance(enabled, bool):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'enabled' must be boolean.")
        return (
            yield from _verified_boolean_steps(
                song,
                attribute="loop",
                expected=enabled,
                setter=lambda: setattr(song, "loop", enabled),
                result_key="loop",
            )
        )
    handler = COMMAND_HANDLERS.get(normalized)
    if handler is None:
        raise RemoteError(ERROR_UNKNOWN_COMMAND, "Unknown command %r." % normalized)
    if normalized == "quit_ableton":
        return handler(song, application, control_surface, params)
    if normalized == "live_fade":
        # ``live_fade_steps`` is a generator that yields between volume
        # writes; ``yield from`` keeps the Live main thread pumping while it
        # sleeps through its ``duration`` seconds of interpolation work.
        return (yield from handler(song, application, params))
    return handler(song, application, params)


def _command_steps(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    *,
    manage_undo: bool,
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    normalized = command.strip().lower()
    if normalized in READ_ONLY_COMMANDS:
        raise RemoteError(
            ERROR_READ_ONLY_VIOLATION,
            "Command %r is blocked: creative mutation is not available." % command,
        )
    if not isinstance(params, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
    owns_undo = normalized in ALLOWED_MUTATIONS and manage_undo
    if owns_undo:
        _begin_undo(undo_target)
    try:
        return (
            yield from _dispatch_command_steps(
                song,
                application,
                normalized,
                params,
                undo_target,
                control_surface,
            )
        )
    finally:
        if owns_undo:
            _end_undo(undo_target)


def execute_command(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    *,
    manage_undo: bool = True,
    undo_target: Any = None,
) -> Any:
    """Synchronously drive a command for unit tests and immediate host callers."""

    target = undo_target if undo_target is not None else application
    steps = _command_steps(
        song,
        application,
        command,
        params,
        manage_undo=manage_undo,
        undo_target=target,
    )
    while True:
        try:
            next(steps)
        except StopIteration as completed:
            return completed.value


def _request_steps(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    undo_target: Any,
    control_surface: Any = None,
) -> Generator[None, None, Any]:
    """Build one request execution that may span multiple Live UI ticks."""

    return (
        yield from _command_steps(
            song,
            application,
            command,
            params,
            manage_undo=True,
            undo_target=undo_target,
            control_surface=control_surface,
        )
    )


@dataclass
class QueuedRequest:
    command: str
    params: dict[str, Any]
    response_queue: queue.Queue[dict[str, Any]]


@dataclass
class ActiveRequest:
    request: QueuedRequest
    steps: Generator[None, None, Any]


class RequestProcessor:
    """Owns the UI-thread queue; socket threads only call :meth:`enqueue`."""

    def __init__(
        self,
        song: Any,
        application: Any,
        undo_target: Any = None,
        control_surface: Any = None,
    ) -> None:
        self.song = song
        self.application = application
        self.undo_target = undo_target if undo_target is not None else application
        self.control_surface = control_surface
        self.request_queue: queue.Queue[QueuedRequest] = queue.Queue()
        self.active_request: ActiveRequest | None = None

    def enqueue(self, request: QueuedRequest) -> None:
        self.request_queue.put(request)

    def process_pending(self, max_requests: int = 16) -> int:
        processed = 0
        while processed < max_requests:
            if self.active_request is None:
                try:
                    request = self.request_queue.get_nowait()
                except queue.Empty:
                    break
                self.active_request = ActiveRequest(
                    request,
                    _request_steps(
                        self.song,
                        self.application,
                        request.command,
                        request.params,
                        self.undo_target,
                        self.control_surface,
                    ),
                )
            active = self.active_request
            try:
                next(active.steps)
                break
            except StopIteration as completed:
                response = {"status": "ok", "result": completed.value}
            except RemoteError as error:
                response = error.to_envelope()
            except Exception as error:
                logger.exception("Unhandled Remote Script error for %s", active.request.command)
                response = RemoteError(ERROR_LIVE_UNAVAILABLE, str(error)).to_envelope()
            active.request.response_queue.put(response)
            self.active_request = None
            processed += 1
        return processed


class JsonlSocketServer:
    """Loopback-only JSONL listener that performs no Live API access."""

    def __init__(self, processor: RequestProcessor) -> None:
        self.processor = processor
        self.shutdown_event = threading.Event()
        self.server_socket: socket.socket | None = None
        self.thread = threading.Thread(
            target=self._serve, daemon=True, name="AbletonMCPServerSocket"
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.shutdown_event.set()
        if self.server_socket is not None:
            with suppress(OSError):
                self.server_socket.close()
        self.thread.join(timeout=1.0)

    def _serve(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket = server
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((DEFAULT_HOST, DEFAULT_PORT))
            server.listen(5)
            server.settimeout(0.5)
        except OSError as error:
            logger.error("Could not bind %s:%s: %s", DEFAULT_HOST, DEFAULT_PORT, error)
            return
        while not self.shutdown_event.is_set():
            try:
                connection, _address = server.accept()
                threading.Thread(
                    target=self._serve_client,
                    args=(connection,),
                    daemon=True,
                    name="AbletonMCPServerClient",
                ).start()
            except TimeoutError:
                continue
            except OSError:
                if not self.shutdown_event.is_set():
                    logger.exception("Socket accept failed")
                break

    def _serve_client(self, connection: socket.socket) -> None:
        buffer = bytearray()
        connection.settimeout(1.0)
        try:
            while not self.shutdown_event.is_set():
                try:
                    chunk = connection.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_FRAME_BYTES:
                    raise RemoteError(ERROR_INVALID_PARAMS, "JSONL frame exceeds 1 MiB.")
                while b"\n" in buffer:
                    line_end = buffer.index(b"\n")
                    frame = bytes(buffer[:line_end])
                    del buffer[: line_end + 1]
                    if not frame.strip():
                        continue
                    response = self._handle_frame(frame)
                    connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except RemoteError as error:
            connection.sendall((json.dumps(error.to_envelope()) + "\n").encode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            response = RemoteError(ERROR_INVALID_PARAMS, str(error)).to_envelope()
            with suppress(OSError):
                connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
        finally:
            with suppress(OSError):
                connection.close()

    def _handle_frame(self, frame: bytes) -> dict[str, Any]:
        request = json.loads(frame.decode("utf-8"))
        if not isinstance(request, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Request must be a JSON object.")
        command = request.get("type")
        params = request.get("params", {})
        if not isinstance(command, str) or not command.strip():
            raise RemoteError(ERROR_INVALID_PARAMS, "Request type must be a non-empty string.")
        if not isinstance(params, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
        if command.strip().lower() in READ_ONLY_COMMANDS:
            return RemoteError(
                ERROR_READ_ONLY_VIOLATION,
                "Command %r is blocked: creative mutation is not available." % command,
            ).to_envelope()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self.processor.enqueue(QueuedRequest(command, params, response_queue))
        try:
            return response_queue.get(timeout=request_timeout_seconds(command, params))
        except queue.Empty:
            return RemoteError(
                ERROR_TIMEOUT,
                "Command execution timed out waiting for Live's UI thread.",
            ).to_envelope()


def _resolve_undo_target(*candidates: Any) -> Any:
    for candidate in candidates:
        if candidate is None:
            continue
        if callable(
            _safe(lambda candidate=candidate: candidate.begin_undo_step, None)
        ) and callable(_safe(lambda candidate=candidate: candidate.end_undo_step, None)):
            return candidate
    return candidates[-1]


class AbletonMCPServer(ControlSurface):
    def __init__(self, c_instance: Any) -> None:
        super().__init__(c_instance)
        application = (
            Live.Application.get_application() if Live is not None else c_instance.application
        )
        song = self.song() if callable(self.song) else self.song
        undo_target = _resolve_undo_target(c_instance, self, application, song)
        self._processor = RequestProcessor(song, application, undo_target, self)
        self._socket_server = JsonlSocketServer(self._processor)
        self._socket_server.start()
        _dbg("startup endpoint=127.0.0.1:9888")
        self.show_message("AbletonMCPServer: Active on 127.0.0.1:9888")

    def update_display(self) -> None:
        super().update_display()
        self._processor.process_pending()

    def disconnect(self) -> None:
        self._socket_server.stop()
        super().disconnect()


def create_instance(c_instance: Any) -> AbletonMCPServer:
    return AbletonMCPServer(c_instance)
