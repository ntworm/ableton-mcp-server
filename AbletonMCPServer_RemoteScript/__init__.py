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
    CAPABILITY_EVIDENCE,
    CUE_OPERATION_VERIFY_TICKS,
    CUE_TIME_TOLERANCE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ERROR_AMBIGUOUS_MATCH,
    ERROR_BAD_INPUT,
    ERROR_CAPABILITY_UNAVAILABLE,
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
    ERROR_VERIFICATION_FAILED,
    ERROR_WRONG_TYPE,
    LIVE_COLOR_INDEX_MAX,
    LIVE_COLOR_INDEX_MIN,
    LIVE_COLOR_RGB_MAX,
    LIVE_COLOR_RGB_MIN,
    PLAYHEAD_MOVE_RETRIES,
    PLUGIN_NOT_CONFIGURED,
    PLUGIN_NOT_CONFIGURED_HINT,
    READ_ONLY_COMMANDS,
    UNSUPPORTED_CAPABILITIES,
    is_plugin_device_class,
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

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        # Machine-readable payload for errors that carry more than prose.
        # ``CAPABILITY_UNAVAILABLE`` uses it for the API evidence behind the
        # refusal and for the request the caller made.
        self.details = details

    def to_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "status": "error",
            "code": self.code,
            "message": str(self),
        }
        if self.hint:
            envelope["hint"] = self.hint
        if self.details:
            envelope["details"] = self.details
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


def _optional_int(value: Any) -> int | None:
    """Coerce a LOM integer property to ``int``, or ``None`` when absent.

    ``bool`` is excluded on purpose: it is an ``int`` subclass in Python, and
    a host that answered ``True`` for ``color_index`` would otherwise be
    reported as colour ``1``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    """Coerce a LOM numeric property to ``float``, or ``None`` when absent.

    Beat times arrive as floats but a host that has no value answers ``None``,
    and ``bool`` is refused for the same reason as in ``_optional_int``.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


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
    """Return the routing kind of a track: master, return, midi, or audio.

    A Group Track has no MIDI input and therefore lands on ``audio`` here.
    That is deliberate: ``type`` describes what the track carries, and the
    value set is part of the wire contract (``_clip_slot`` and the acceptance
    cleanup both branch on it). Group membership is reported separately by
    :func:`_track_hierarchy` through ``is_group_track`` / ``is_grouped``;
    callers must never infer "this is a group" from ``type == "audio"``.
    """

    if track == song.master_track:
        return "master"
    if track in song.return_tracks:
        return "return"
    if bool(_safe(lambda: track.has_midi_input, False)):
        return "midi"
    return "audio"


def _group_track_index(song: Any, track: Any) -> int | None:
    """Return the session index of ``track.group_track``, or ``None``.

    ``Track.group_track`` is read-only and Live returns ``id 0`` (a falsy
    object, not ``None``) for an ungrouped track. We therefore resolve the
    parent through the same ``_all_tracks`` ordering used by every path-id so
    the value a client gets back is directly usable as ``track_index``.
    """

    parent = _safe(lambda: track.group_track, None)
    if parent is None:
        return None
    for index, candidate in enumerate(_all_tracks(song)):
        if candidate == parent:
            return index
    return None


def _track_hierarchy(song: Any, track: Any) -> dict[str, Any]:
    """Capture the LOM grouping and colour fields shared by track reads.

    Every field is read through ``_safe`` because return and master tracks do
    not expose the full Track surface, and older Live builds may omit
    individual properties. A property Live does not expose is reported as
    ``None`` (or ``False`` for the booleans) rather than being invented.
    """

    color_index = _optional_int(_safe(lambda: track.color_index, None))
    fold_state = _optional_int(_safe(lambda: track.fold_state, None))
    group_index = _group_track_index(song, track)
    return {
        "color": int(_safe(lambda: track.color, 0)),
        "color_index": color_index,
        "is_group_track": bool(_safe(lambda: track.is_foldable, False)),
        "is_grouped": bool(_safe(lambda: track.is_grouped, False)),
        "group_track_index": group_index,
        "group_track_id": "track:%s" % group_index if group_index is not None else None,
        "is_visible": bool(_safe(lambda: track.is_visible, True)),
        "fold_state": fold_state,
    }


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


def _configured_parameter_count(parameters: list[dict[str, Any]]) -> int:
    """Count plugin parameters the user added through Live's Configure button.

    ``Device On`` belongs to Live's wrapper, not to the plugin, so it is never
    evidence that the plugin was configured.
    """

    return sum(1 for parameter in parameters if parameter.get("name") != "Device On")


def _plugin_state(class_name: str, parameters: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Describe a plugin wrapper's Configure state, or ``None`` for native devices.

    An empty ``parameters`` list on a plugin is ambiguous on its own: the
    caller cannot tell "this plugin has no controls" from "nobody has
    configured it yet". This block resolves that ambiguity so an agent knows
    to ask the user for the Configure step instead of assuming the device is
    not automatable.
    """

    if not is_plugin_device_class(class_name):
        return None
    configured = _configured_parameter_count(parameters)
    state: dict[str, Any] = {
        "configured_parameter_count": configured,
        "status": "configured" if configured else "not_configured",
    }
    if not configured:
        state["hint"] = PLUGIN_NOT_CONFIGURED
        state["message"] = PLUGIN_NOT_CONFIGURED_HINT
    return state


def _capture_device(device: Any, track_index: int, device_index: int) -> dict[str, Any]:
    device_id = "track:%s/device:%s" % (track_index, device_index)
    parameters = [
        _capture_parameter(parameter, "%s/param:%s" % (device_id, parameter_index))
        for parameter_index, parameter in enumerate(_safe(lambda: device.parameters, []))
    ]
    class_name = str(_safe(lambda: device.class_name, ""))
    payload = {
        "id": device_id,
        "name": str(_safe(lambda: device.name, "")),
        "class_name": class_name,
        "is_active": bool(_safe(lambda: device.is_active, True)),
        "parameters": parameters,
    }
    plugin_state = _plugin_state(class_name, parameters)
    if plugin_state is not None:
        payload["plugin_state"] = plugin_state
    return payload


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
        **_track_hierarchy(song, track),
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
            **_track_hierarchy(song, track),
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


def _device_at(song: Any, track_index: int, device_index: int) -> tuple[Any, Any]:
    track = _track_at(song, track_index)
    devices = list(_safe(lambda: track.devices, []))
    if device_index < 0 or device_index >= len(devices):
        raise RemoteError(ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index)
    return track, devices[device_index]


def _missing_parameter_error(device: Any, parameter_name: str, names: list[str]) -> RemoteError:
    """Build the INVALID_PARAMS envelope for an unresolved parameter name.

    On a plugin whose Configure list is empty the close-match suggestion has
    nothing to work with, so the envelope carries the Configure explanation
    instead of a bare "not found" the caller cannot act on.
    """

    suggestions = difflib.get_close_matches(parameter_name, names, n=3, cutoff=0.5)
    suffix = " Did you mean: %s?" % ", ".join(suggestions) if suggestions else ""
    class_name = str(_safe(lambda: device.class_name, ""))
    if is_plugin_device_class(class_name) and not _configured_parameter_count(
        [{"name": name} for name in names]
    ):
        return RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r was not found: plugin %r exposes no configured parameters."
            % (parameter_name, str(_safe(lambda: device.name, ""))),
            hint=PLUGIN_NOT_CONFIGURED_HINT,
            details={"hint_code": PLUGIN_NOT_CONFIGURED, "class_name": class_name},
        )
    return RemoteError(
        ERROR_INVALID_PARAMS,
        "Parameter %r was not found.%s" % (parameter_name, suffix),
    )


def cmd_get_parameter_value(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    chain_index = params.get("chain_index")
    chain_device_index = params.get("chain_device_index")
    _track, parameter, path_id = _resolve_device_parameter(
        song, track_index, device_index, parameter_name, chain_index, chain_device_index
    )
    return _capture_parameter(parameter, path_id)


def _plugin_device_at(song: Any, track_index: int, device_index: int) -> tuple[Any, Any]:
    """Resolve a device and refuse when it is not a plugin wrapper."""

    track, device = _device_at(song, track_index, device_index)
    class_name = str(_safe(lambda: device.class_name, ""))
    if not is_plugin_device_class(class_name):
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Device %s on track %s is %r, not a plugin; presets are a "
            "PluginDevice capability." % (device_index, track_index, class_name),
        )
    return track, device


def _plugin_presets(device: Any) -> list[str]:
    return [str(preset) for preset in _safe(lambda: device.presets, []) or []]


def cmd_get_plugin_presets(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    track, device = _plugin_device_at(song, track_index, device_index)
    presets = _plugin_presets(device)
    selected = _safe(lambda: device.selected_preset_index, None)
    parameters = [
        {"name": str(_safe(lambda parameter=parameter: parameter.name, ""))}
        for parameter in _safe(lambda: device.parameters, [])
    ]
    result: dict[str, Any] = {
        "id": "track:%s/device:%s" % (track_index, device_index),
        "track_index": track_index,
        "device_index": device_index,
        "track_name": str(_safe(lambda: track.name, "")),
        "device_name": str(_safe(lambda: device.name, "")),
        "class_name": str(_safe(lambda: device.class_name, "")),
        "presets": presets,
        "preset_count": len(presets),
        "selected_preset_index": int(selected) if isinstance(selected, int) else None,
    }
    plugin_state = _plugin_state(result["class_name"], parameters)
    if plugin_state is not None:
        result["plugin_state"] = plugin_state
    return result


def _resolve_preset_index(device: Any, presets: list[str], params: dict[str, Any]) -> int:
    """Resolve ``preset_index`` or ``preset_name`` to one in-range index."""

    has_index = params.get("preset_index") is not None
    has_name = params.get("preset_name") is not None
    if has_index == has_name:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Provide exactly one of 'preset_index' or 'preset_name'.",
        )
    if not presets:
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "Plugin %r exposes no presets through the Live Object Model."
            % str(_safe(lambda: device.name, "")),
        )
    if has_index:
        index = _integer_param(params, "preset_index")
        if index < 0 or index >= len(presets):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Preset index %s is outside [0, %s]." % (index, len(presets) - 1),
            )
        return index
    name = _string_param(params, "preset_name")
    matches = [index for index, preset in enumerate(presets) if preset == name]
    if not matches:
        suggestions = difflib.get_close_matches(name, presets, n=3, cutoff=0.5)
        suffix = " Did you mean: %s?" % ", ".join(suggestions) if suggestions else ""
        raise RemoteError(ERROR_INVALID_PARAMS, "Preset %r was not found.%s" % (name, suffix))
    if len(matches) > 1:
        raise RemoteError(
            ERROR_AMBIGUOUS_MATCH,
            "Preset name %r matches %s presets; use 'preset_index'." % (name, len(matches)),
        )
    return matches[0]


def _set_plugin_preset_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    track, device = _plugin_device_at(song, track_index, device_index)
    presets = _plugin_presets(device)
    target = _resolve_preset_index(device, presets, params)
    previous = _safe(lambda: device.selected_preset_index, None)

    observed: Any = previous
    for _attempt in range(2):
        device.selected_preset_index = target
        yield
        observed = _safe(lambda: device.selected_preset_index, None)
        if isinstance(observed, int) and observed == target:
            return {
                "id": "track:%s/device:%s" % (track_index, device_index),
                "selected_preset_index": target,
                "preset_name": presets[target],
                "previous_preset_index": int(previous) if isinstance(previous, int) else None,
                "preset_count": len(presets),
                "resolved": {
                    "kind": "device",
                    "track_index": track_index,
                    "device_index": device_index,
                    "track_name": str(_safe(lambda: track.name, "")),
                    "device_name": str(_safe(lambda: device.name, "")),
                },
            }
    raise RemoteError(
        ERROR_VERIFICATION_FAILED,
        "Plugin preset did not change: requested %s, observed %r." % (target, observed),
    )


def _chain_at(device: Any, chain_index: int, track_index: int, device_index: int) -> Any:
    chains = list(_safe(lambda: device.chains, []) or [])
    if not chains:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Device %s on track %s is not a rack; it exposes no chains."
            % (device_index, track_index),
        )
    if chain_index < 0 or chain_index >= len(chains):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Chain %s does not exist on device %s." % (chain_index, device_index),
        )
    return chains[chain_index]


def _resolve_device_parameter(
    song: Any,
    track_index: int,
    device_index: int,
    parameter_name: str,
    chain_index: Any = None,
    chain_device_index: Any = None,
) -> tuple[Any, Any, str]:
    """Resolve a parameter at top level, inside a chain, or on a chain's mixer.

    Live nests the controls that matter: the Velocity device that caps a drum
    track and the volume that balances one guitar articulation against another
    both live inside rack chains, where a top-level lookup cannot reach them.
    """

    track, device = _device_at(song, track_index, device_index)
    base_id = "track:%s/device:%s" % (track_index, device_index)
    if chain_index is None:
        parameters = list(_safe(lambda: device.parameters, []))
        owner = device
    else:
        if isinstance(chain_index, bool) or not isinstance(chain_index, int):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'chain_index' must be an integer.")
        chain = _chain_at(device, chain_index, track_index, device_index)
        if chain_device_index is None:
            # No inner device named: the target is the chain's own mixer, which
            # is how a rack blends its chains.
            mixer = _safe(lambda: chain.mixer_device, None)
            normalized = parameter_name.strip().casefold()
            alias = {"volume": "volume", "pan": "panning", "panning": "panning"}.get(normalized)
            if mixer is None or alias is None:
                raise RemoteError(
                    ERROR_INVALID_PARAMS,
                    "A chain mixer exposes 'volume' and 'panning'; pass "
                    "'chain_device_index' to reach a device inside the chain.",
                )
            parameter = _safe(lambda: getattr(mixer, alias), None)
            if parameter is None:
                raise RemoteError(
                    ERROR_CAPABILITY_UNAVAILABLE,
                    "This chain does not expose %r on its mixer." % alias,
                )
            return track, parameter, "%s/chain:%s/mixer:%s" % (base_id, chain_index, alias)
        if isinstance(chain_device_index, bool) or not isinstance(chain_device_index, int):
            raise RemoteError(
                ERROR_INVALID_PARAMS, "Parameter 'chain_device_index' must be an integer."
            )
        devices = list(_safe(lambda: chain.devices, []))
        if chain_device_index < 0 or chain_device_index >= len(devices):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Chain device %s does not exist in chain %s."
                % (chain_device_index, chain_index),
            )
        owner = devices[chain_device_index]
        parameters = list(_safe(lambda: owner.parameters, []))
        base_id = "%s/chain:%s/device:%s" % (base_id, chain_index, chain_device_index)
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
        raise _missing_parameter_error(owner, parameter_name, names)
    return track, parameter, "%s/param:%s" % (base_id, parameters.index(parameter))


def _set_parameter_value_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    parameter_name = _string_param(params, "parameter_name")
    requested = _float_param(params, "value", -1000000.0, 1000000.0)
    chain_index = params.get("chain_index")
    chain_device_index = params.get("chain_device_index")
    track, parameter, _path_id = _resolve_device_parameter(
        song,
        track_index,
        device_index,
        parameter_name,
        chain_index,
        chain_device_index,
    )
    _track_for_name, device = _device_at(song, track_index, device_index)
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
            resolved = {
                "kind": "device",
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": parameter_name,
            }
            if chain_index is not None:
                resolved["chain_index"] = chain_index
            if chain_device_index is not None:
                resolved["chain_device_index"] = chain_device_index
            track_name = str(_safe(lambda: track.name, ""))
            device_name = str(_safe(lambda: device.name, ""))
            if track_name:
                resolved["track_name"] = track_name
            if device_name:
                resolved["device_name"] = device_name
            return {
                "target": requested,
                "value": observed,
                "is_quantized": is_quantized,
                "resolved": resolved,
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
    visited: set[str] = set()
    budget = 5000
    for category in selected:
        root = _safe(lambda category=category: getattr(application.browser, category), None)
        if root is None:
            continue
        root_name = str(_safe(lambda root=root: root.name, category.replace("_", " ").title()))
        # Slice 1 Task 5: Live's LOM yields fresh proxy wrappers on every
        # ``.children`` access, so tracking identity via ``id()`` collapses.
        # Use URI keys (stable across proxies) and ordinal-path keys (URI-less
        # trees) to bound traversal.
        stack = [(root, [root_name], 0, ())]
        while stack and len(results) < limit and len(visited) < budget:
            item, path, depth, ordinal_path = stack.pop()
            uri = str(_safe(lambda item=item: item.uri, ""))
            key = (
                "uri:" + uri
                if uri
                else "%s:%s"
                % (
                    category,
                    "/".join(str(part) for part in ordinal_path),
                )
            )
            if key in visited:
                continue
            visited.add(key)
            name = str(_safe(lambda item=item: item.name, ""))
            if depth > 0 and query in name.casefold():
                results.append(
                    {
                        "name": name,
                        "uri": uri,
                        "category": category,
                        "path": path,
                        "is_loadable": bool(_safe(lambda item=item: item.is_loadable, False)),
                    }
                )
            if depth >= 5:
                continue
            children = list(_safe(lambda item=item: item.children, []))[:500]
            for child_index in range(len(children) - 1, -1, -1):
                child = children[child_index]
                child_name = str(_safe(lambda child=child: child.name, ""))
                stack.append((child, [*path, child_name], depth + 1, (*ordinal_path, child_index)))
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


def cmd_live_find_device(
    song: Any, application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    query = _string_param(params, "query").casefold()
    return [
        device
        for device in cmd_get_device_list(song, application, params)
        if query in str(device.get("name", "")).casefold()
        or query in str(device.get("class_name", "")).casefold()
    ]


def cmd_live_find_clip(song: Any, application: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    query = _string_param(params, "query").casefold()
    return [
        clip
        for clip in cmd_get_clip_summary(song, application, params)
        if clip.get("has_clip") and query in str(clip.get("clip_name", "")).casefold()
    ]


def cmd_list_device_params(
    song: Any, _application: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    track_id = _string_param(params, "track_id")
    track_index, track = _resolve_track_id(song, track_id)
    entries = []
    for device_index, device in enumerate(_safe(lambda: track.devices, [])):
        parameters = [
            _capture_parameter(
                parameter,
                "track:%s/device:%s/param:%s" % (track_index, device_index, parameter_index),
            )
            for parameter_index, parameter in enumerate(
                _safe(lambda device=device: device.parameters, [])
            )
        ]
        class_name = str(_safe(lambda device=device: device.class_name, ""))
        entry: dict[str, Any] = {
            "device_id": "track:%s/device:%s" % (track_index, device_index),
            "device_name": str(_safe(lambda device=device: device.name, "")),
            "parameters": parameters,
        }
        plugin_state = _plugin_state(class_name, parameters)
        if plugin_state is not None:
            entry["plugin_state"] = plugin_state
        entries.append(entry)
    return entries


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
        "State setter for %s did not reach %s after %s UI ticks." % (attribute, expected, retries),
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
        "State setter for %s did not reach %r after %s UI ticks." % (attribute, expected, retries),
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
    dry_run = params.get("dry_run", False)
    track, slot = _clip_slot(song, track_index, clip_index)
    if _track_type(song, track) != "midi":
        raise RemoteError(ERROR_WRONG_TYPE, "create_clip requires a MIDI track.")
    if bool(_safe(lambda: slot.has_clip, False)):
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is not empty.")

    clip_id = "track:%s/clipslot:%s/clip" % (track_index, clip_index)
    resolved = {
        "kind": "clip",
        "track_index": track_index,
        "clip_index": clip_index,
        "clip_id": clip_id,
    }
    track_name = str(_safe(lambda: track.name, ""))
    if track_name:
        resolved["track_name"] = track_name

    if dry_run:
        return {
            "created": False,
            "committed": False,
            "clip_id": clip_id,
            "length_beats": length,
            "resolved": resolved,
        }

    slot.create_clip(length)
    return {
        "created": True,
        "clip_id": clip_id,
        "length_beats": length,
        "resolved": resolved,
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


def _bounded_int_param(params: dict[str, Any], name: str, minimum: int, maximum: int) -> int:
    value = _required(params, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter %r must be an integer." % name)
    if value < minimum or value > maximum:
        raise RemoteError(
            ERROR_BAD_INPUT,
            "Parameter %r must be in %s..%s." % (name, minimum, maximum),
        )
    return value


def _require_regular_track(song: Any, index: int, label: str) -> Any:
    """Resolve a regular (non-return, non-master) track by session index."""

    track = _track_at(song, index)
    kind = _track_type(song, track)
    if kind in ("return", "master"):
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "%s must be a regular track; track %s is the %s track."
            % (label, index, "main/master" if kind == "master" else "return"),
        )
    return track


def _require_group_track(song: Any, index: int, label: str) -> Any:
    track = _require_regular_track(song, index, label)
    if not bool(_safe(lambda: track.is_foldable, False)):
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "%s must be a Group Track; track %s is not foldable." % (label, index),
        )
    return track


def _group_ancestors(song: Any, track: Any) -> list[int]:
    """Return the chain of group indexes above ``track``, outermost last."""

    chain: list[int] = []
    current = track
    for _depth in range(len(_all_tracks(song)) + 1):
        parent_index = _group_track_index(song, current)
        if parent_index is None:
            return chain
        if parent_index in chain:
            # Live cannot produce this, but a corrupt chain must not hang the
            # UI thread in an unbounded walk.
            return chain
        chain.append(parent_index)
        current = _track_at(song, parent_index)
    return chain


def _reject_group_cycle(song: Any, track_index: int, group_index: int) -> None:
    if track_index == group_index:
        raise RemoteError(
            ERROR_BAD_INPUT,
            "A Group Track cannot be placed inside itself (track %s)." % track_index,
        )
    group = _track_at(song, group_index)
    if track_index in _group_ancestors(song, group):
        raise RemoteError(
            ERROR_BAD_INPUT,
            "Track %s already contains group %s; nesting it there would create a cycle."
            % (track_index, group_index),
        )


def _validate_hierarchy_request(song: Any, command: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate a hierarchy request and echo back what was asked for.

    Validation runs *before* the capability refusal on purpose: a caller must
    be able to tell a malformed request (INVALID_PARAMS / BAD_INPUT /
    WRONG_TYPE) apart from a well-formed request that Live's API cannot
    perform (CAPABILITY_UNAVAILABLE). Nothing here writes to the Set.
    """

    regular_count = len(list(_safe(lambda: song.tracks, [])))
    if command == "move_track":
        source = _integer_param(params, "track_index")
        destination = _integer_param(params, "destination_index")
        _require_regular_track(song, source, "track_index")
        if destination >= regular_count:
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "destination_index %s is outside the %s regular tracks."
                % (destination, regular_count),
            )
        return {"track_index": source, "destination_index": destination}
    if command == "reorder_tracks":
        order = _required(params, "order")
        if not isinstance(order, list) or not order:
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'order' must be a non-empty list.")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in order):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'order' must contain integers.")
        if sorted(order) != list(range(regular_count)):
            raise RemoteError(
                ERROR_BAD_INPUT,
                "Parameter 'order' must be a permutation of the %s regular track indexes."
                % regular_count,
            )
        return {"order": list(order)}
    if command == "move_track_to_group":
        source = _integer_param(params, "track_index")
        group_index = _integer_param(params, "group_track_index")
        _require_regular_track(song, source, "track_index")
        _require_group_track(song, group_index, "group_track_index")
        _reject_group_cycle(song, source, group_index)
        return {"track_index": source, "group_track_index": group_index}
    if command == "ungroup_track":
        source = _integer_param(params, "track_index")
        track = _require_regular_track(song, source, "track_index")
        if not bool(_safe(lambda: track.is_grouped, False)):
            raise RemoteError(
                ERROR_WRONG_TYPE,
                "Track %s is not inside a Group Track." % source,
            )
        return {"track_index": source, "group_track_index": _group_track_index(song, track)}
    if command == "merge_groups":
        source = _integer_param(params, "source_group_index")
        destination = _integer_param(params, "destination_group_index")
        delete_empty_source = params.get("delete_empty_source", False)
        if not isinstance(delete_empty_source, bool):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Parameter 'delete_empty_source' must be boolean.",
            )
        if delete_empty_source:
            raise RemoteError(
                ERROR_BAD_INPUT,
                "delete_empty_source is not supported: this bridge never deletes a track.",
                "Leave the emptied group in place and remove it by hand if you want it gone.",
            )
        _require_group_track(song, source, "source_group_index")
        _require_group_track(song, destination, "destination_group_index")
        if source == destination:
            raise RemoteError(
                ERROR_BAD_INPUT,
                "source_group_index and destination_group_index must differ.",
            )
        _reject_group_cycle(song, source, destination)
        return {
            "source_group_index": source,
            "destination_group_index": destination,
            "delete_empty_source": False,
        }
    raise RemoteError(ERROR_UNKNOWN_COMMAND, "Unknown command %r." % command)


def cmd_unavailable_capability(song: Any, _application: Any, params: dict[str, Any]) -> Any:
    """Never returns: validates, then refuses with the API evidence."""

    command = str(params.get("__command", ""))
    request = _validate_hierarchy_request(song, command, params)
    evidence = dict(CAPABILITY_EVIDENCE[command])
    evidence["request"] = request
    evidence["applied"] = False
    raise RemoteError(
        ERROR_CAPABILITY_UNAVAILABLE,
        UNSUPPORTED_CAPABILITIES[command],
        "The request is well-formed; Live's public API has no operation that performs it. "
        "Nothing was changed in the Set.",
        evidence,
    )


def _requested_colour(params: dict[str, Any]) -> tuple[str, int]:
    """Resolve the single colour property to write and its validated value.

    Tracks and clips share Live's palette and the same packed-RGB encoding, so
    both colour commands validate through here.
    """

    requested = [name for name in ("color_index", "color") if name in params]
    if len(requested) != 1:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Provide exactly one of color_index or color.",
        )
    attribute = requested[0]
    if attribute == "color_index":
        return attribute, _bounded_int_param(
            params,
            "color_index",
            LIVE_COLOR_INDEX_MIN,
            LIVE_COLOR_INDEX_MAX,
        )
    return attribute, _bounded_int_param(
        params,
        "color",
        LIVE_COLOR_RGB_MIN,
        LIVE_COLOR_RGB_MAX,
    )


def _verified_colour_write_steps(
    target: Any,
    *,
    attribute: str,
    expected: int,
    label: str,
) -> Generator[None, None, dict[str, int | None]]:
    """Write one colour property once and confirm it on a later UI tick.

    There is no retry: the write is issued a single time, Live is given a tick,
    and the observed value is read back. A rejected or clamped write surfaces
    as ``VERIFICATION_FAILED`` instead of a fabricated success.
    """

    if _safe(lambda: getattr(target, attribute), None) is None:
        raise RemoteError(ERROR_WRONG_TYPE, "%s does not expose %r." % (label, attribute))
    try:
        setattr(target, attribute, expected)
    except (AttributeError, RuntimeError, TypeError) as error:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "%s rejected %r: %s" % (label, attribute, error),
        ) from error
    yield
    observed = _optional_int(_safe(lambda: getattr(target, attribute), None))
    if observed != expected:
        raise RemoteError(
            ERROR_VERIFICATION_FAILED,
            "%s %s readback returned %r, expected %r." % (label, attribute, observed, expected),
        )
    return {
        "color": _optional_int(_safe(lambda: target.color, None)),
        "color_index": _optional_int(_safe(lambda: target.color_index, None)),
    }


def _set_track_color_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Write ``Track.color_index`` or ``Track.color`` and read the value back."""

    track_index = _integer_param(params, "track_index")
    attribute, expected = _requested_colour(params)
    track = _track_at(song, track_index)
    observed = yield from _verified_colour_write_steps(
        track,
        attribute=attribute,
        expected=expected,
        label="Track %s" % track_index,
    )
    result: dict[str, Any] = {
        "track_id": "track:%s" % track_index,
        "track_index": track_index,
        "property": attribute,
        "color": observed["color"] if observed["color"] is not None else 0,
        "color_index": observed["color_index"],
    }
    resolved: dict[str, Any] = {"kind": "track", "track_index": track_index}
    track_name = str(_safe(lambda: track.name, ""))
    if track_name:
        resolved["track_name"] = track_name
    result["resolved"] = resolved
    return result


def _arrangement_clips(track: Any) -> list[Any] | None:
    """Return this track's Arrangement clips, or ``None`` when unavailable.

    ``Track.arrangement_clips`` was added to the Live 11 LOM. A host that
    predates it (or a track type that has no Arrangement lane) must be
    reported as inaccessible rather than silently treated as empty — an empty
    list and "the host cannot tell me" are different answers.
    """

    clips = _safe(lambda: track.arrangement_clips, None)
    if clips is None:
        return None
    try:
        return list(clips)
    except TypeError:
        return None


def _capture_clip_colour_target(
    clip: Any,
    *,
    scope: str,
    track_index: int,
    clip_index: int,
) -> dict[str, Any]:
    identifier = (
        "track:%s/clipslot:%s/clip" % (track_index, clip_index)
        if scope == "session"
        else "track:%s/arrangementclip:%s" % (track_index, clip_index)
    )
    return {
        "id": identifier,
        "scope": scope,
        "track_index": track_index,
        "clip_index": clip_index,
        "name": str(_safe(lambda: clip.name, "")),
        "is_midi_clip": bool(_safe(lambda: clip.is_midi_clip, False)),
        "color": _optional_int(_safe(lambda: clip.color, None)),
        "color_index": _optional_int(_safe(lambda: clip.color_index, None)),
        # ``color`` is documented ``getsetobserve`` on Clip, so a clip whose
        # colour reads back as an integer is writable. Anything else is
        # reported as not colourable instead of being attempted blindly.
        "colorable": _optional_int(_safe(lambda: clip.color, None)) is not None,
    }


def _require_arrangement_clips(song: Any, track_index: int) -> tuple[Any, list[Any]]:
    """Resolve a track's Arrangement lane or fail with the reason it is missing."""

    track = _track_at(song, track_index)
    clips = _arrangement_clips(track)
    if clips is None:
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "Track %s does not expose Track.arrangement_clips on this host." % track_index,
        )
    return track, clips


def _arrangement_clip_at(
    song: Any, track_index: int, clip_index: int
) -> tuple[Any, Any, list[Any]]:
    track, clips = _require_arrangement_clips(song, track_index)
    if clip_index < 0 or clip_index >= len(clips):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Arrangement clip %s does not exist on track %s." % (clip_index, track_index),
        )
    return track, clips[clip_index], clips


def _capture_arrangement_clip(clip: Any, track_index: int, clip_index: int) -> dict[str, Any]:
    """Describe one Arrangement clip, placement first.

    ``start_time`` and ``end_time`` are what makes a clip locatable on the
    timeline; without them a caller knows a clip exists but not when it plays.
    """

    start = _safe(lambda: clip.start_time, None)
    end = _safe(lambda: clip.end_time, None)
    return {
        "id": "track:%s/arrangementclip:%s" % (track_index, clip_index),
        "scope": "arrangement",
        "track_index": track_index,
        "clip_index": clip_index,
        "name": str(_safe(lambda: clip.name, "")),
        "start_time": _optional_float(start),
        "end_time": _optional_float(end),
        "length_beats": (
            _optional_float(end - start) if start is not None and end is not None else None
        ),
        "is_midi_clip": bool(_safe(lambda: clip.is_midi_clip, False)),
        "muted": bool(_safe(lambda: clip.muted, False)),
        "looping": bool(_safe(lambda: clip.looping, False)),
        "loop_start": _optional_float(_safe(lambda: clip.loop_start, None)),
        "loop_end": _optional_float(_safe(lambda: clip.loop_end, None)),
        "color_index": _optional_int(_safe(lambda: clip.color_index, None)),
    }


def cmd_get_arrangement_clips(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """List one track's Arrangement clips with their timeline placement."""

    track_index = _integer_param(params, "track_index")
    _track, clips = _require_arrangement_clips(song, track_index)
    captured = [
        _capture_arrangement_clip(clip, track_index, clip_index)
        for clip_index, clip in enumerate(clips)
    ]
    captured.sort(key=lambda entry: (entry["start_time"] is None, entry["start_time"]))
    return {
        "track_index": track_index,
        "clip_count": len(captured),
        "clips": captured,
    }


def _duplicate_session_clip_to_arrangement_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Place a Session clip on the Arrangement timeline at an exact beat.

    ``Track.duplicate_clip_to_arrangement`` is the only public path from the
    Session grid onto the timeline. The Session clip is left untouched, so the
    caller keeps a reusable source; clip envelopes travel with the copy.
    """

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    destination = _float_param(params, "time")

    track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Session slot %s is empty." % clip_index)

    duplicate = _safe(lambda: track.duplicate_clip_to_arrangement, None)
    if not callable(duplicate):
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "This host does not expose Track.duplicate_clip_to_arrangement.",
        )

    before = _arrangement_clips(track) or []
    count_before = len(before)
    duplicate(clip, destination)
    yield
    after = _arrangement_clips(track) or []
    if len(after) <= count_before:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Arrangement clip creation was not observed on track %s." % track_index,
        )

    placed_index, placed = min(
        ((index, item) for index, item in enumerate(after)),
        key=lambda pair: abs((_safe(lambda: pair[1].start_time, 0.0) or 0.0) - destination),
    )
    return {
        "placed": True,
        "source": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
        "arrangement_clip": _capture_arrangement_clip(placed, track_index, placed_index),
        "clip_count": len(after),
    }


def _delete_arrangement_clip_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Remove one clip from the Arrangement timeline."""

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    track, clip, clips = _arrangement_clip_at(song, track_index, clip_index)
    captured = _capture_arrangement_clip(clip, track_index, clip_index)
    count_before = len(clips)

    delete = _safe(lambda: track.delete_clip, None)
    if not callable(delete):
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "This host does not expose Track.delete_clip.",
        )
    delete(clip)
    yield
    remaining = _arrangement_clips(track) or []
    if len(remaining) >= count_before:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Arrangement clip deletion was not observed on track %s." % track_index,
        )
    return {"deleted": True, "clip": captured, "clip_count": len(remaining)}


def _move_arrangement_clip_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Move an Arrangement clip to a new beat.

    The LOM has no setter for ``Clip.start_time``, so the move is a copy to the
    destination followed by deletion of the original. Both halves are verified;
    a failed copy leaves the original in place rather than losing the clip.
    """

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    destination = _float_param(params, "time")

    track, clip, clips = _arrangement_clip_at(song, track_index, clip_index)
    origin = _safe(lambda: clip.start_time, None)
    count_before = len(clips)

    duplicate = _safe(lambda: track.duplicate_clip_to_arrangement, None)
    delete = _safe(lambda: track.delete_clip, None)
    if not callable(duplicate) or not callable(delete):
        raise RemoteError(
            ERROR_CAPABILITY_UNAVAILABLE,
            "Moving an Arrangement clip needs both "
            "Track.duplicate_clip_to_arrangement and Track.delete_clip.",
        )

    duplicate(clip, destination)
    yield
    after_copy = _arrangement_clips(track) or []
    if len(after_copy) <= count_before:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "The copy step of the move was not observed; the original clip was kept.",
        )

    delete(clip)
    yield
    remaining = _arrangement_clips(track) or []
    if len(remaining) != count_before:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "The delete step of the move was not observed; the track now holds "
            "%s clips instead of %s." % (len(remaining), count_before),
        )

    moved_index, moved = min(
        ((index, item) for index, item in enumerate(remaining)),
        key=lambda pair: abs((_safe(lambda: pair[1].start_time, 0.0) or 0.0) - destination),
    )
    return {
        "moved": True,
        "from_time": _optional_float(origin),
        "arrangement_clip": _capture_arrangement_clip(moved, track_index, moved_index),
        "clip_count": len(remaining),
    }


# ---------------------------------------------------------------------------
# v0.5.6 — Instrument comprehension and authoring shorthands
# ---------------------------------------------------------------------------

_MIDI_EFFECT_CONSEQUENCES = {
    "MidiVelocity": (
        "Rewrites incoming velocity. 'Out Low' and 'Out Hi' are the real "
        "dynamic floor and ceiling of this track, whatever the clip says."
    ),
    "MidiNoteLength": (
        "Overrides note duration. With 'Sync On' off the length comes from "
        "'Time Length'; 'Gate' only acts in synced mode."
    ),
    "MidiPitcher": "Transposes every note; the clip's written pitches are not what sounds.",
    "MidiArpeggiator": (
        "Generates its own note stream from held notes; written rhythm is a source, not the result."
    ),
    "MidiChord": "Adds intervals to every note, so one written note sounds as a chord.",
    "MidiScale": "Snaps pitches to a scale; out-of-scale notes are moved, not refused.",
    "MidiRandom": "Randomises pitch, so exact written pitches are not guaranteed.",
}

_INSTRUMENT_CLASSES = (
    "InstrumentGroupDevice",
    "PluginDevice",
    "InstrumentVector",
    "MultiSampler",
    "SimplerDevice",
    "Operator",
    "InstrumentImpulse",
    "DrumGroupDevice",
    "UltraAnalog",
    "Collision",
    "Tension",
    "Electric",
    "Wavetable",
)


def _chain_mixer_state(chain: Any) -> dict[str, Any]:
    mixer = _safe(lambda: chain.mixer_device, None)
    volume = _safe(lambda: mixer.volume, None) if mixer is not None else None
    panning = _safe(lambda: mixer.panning, None) if mixer is not None else None
    return {
        "volume": _optional_float(_safe(lambda: volume.value, None)),
        "volume_min": _optional_float(_safe(lambda: volume.min, None)),
        "volume_max": _optional_float(_safe(lambda: volume.max, None)),
        "panning": _optional_float(_safe(lambda: panning.value, None)),
        "muted": bool(_safe(lambda: chain.mute, False)),
        "soloed": bool(_safe(lambda: chain.solo, False)),
    }


def cmd_get_device_chains(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Open one rack: its chains, their mixer state and the devices inside.

    ``get_device_list`` stops at the top level, so a rack reads as a wall of
    macros. What actually shapes the sound — the sampler in chain three, the
    Velocity device hidden in a MIDI rack — only appears here.
    """

    track_index = _integer_param(params, "track_index")
    device_index = _integer_param(params, "device_index")
    _track, device = _device_at(song, track_index, device_index)
    chains = _safe(lambda: device.chains, None)
    if chains is None:
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Device %s on track %s is not a rack; it exposes no chains."
            % (device_index, track_index),
        )
    captured = []
    for chain_index, chain in enumerate(list(chains)):
        devices = []
        for inner_index, inner in enumerate(list(_safe(lambda chain=chain: chain.devices, []))):
            parameters = list(_safe(lambda inner=inner: inner.parameters, []))
            devices.append(
                {
                    "id": "track:%s/device:%s/chain:%s/device:%s"
                    % (track_index, device_index, chain_index, inner_index),
                    "chain_index": chain_index,
                    "device_index": inner_index,
                    "name": str(_safe(lambda inner=inner: inner.name, "")),
                    "class_name": str(_safe(lambda inner=inner: inner.class_name, "")),
                    "is_active": bool(_safe(lambda inner=inner: inner.is_active, True)),
                    "parameter_count": len(parameters),
                    "parameter_names": [
                        str(_safe(lambda parameter=parameter: parameter.name, ""))
                        for parameter in parameters[:24]
                    ],
                }
            )
        captured.append(
            {
                "id": "track:%s/device:%s/chain:%s" % (track_index, device_index, chain_index),
                "chain_index": chain_index,
                "name": str(_safe(lambda chain=chain: chain.name, "")),
                "devices": devices,
                **_chain_mixer_state(chain),
            }
        )
    return {
        "track_index": track_index,
        "device_index": device_index,
        "device_name": str(_safe(lambda: device.name, "")),
        "chain_count": len(captured),
        "chains": captured,
    }


def _midi_effect_finding(device: Any, path: str, device_index: int) -> dict[str, Any] | None:
    class_name = str(_safe(lambda: device.class_name, ""))
    consequence = _MIDI_EFFECT_CONSEQUENCES.get(class_name)
    if consequence is None:
        return None
    values = {}
    for parameter in list(_safe(lambda: device.parameters, [])):
        name = str(_safe(lambda parameter=parameter: parameter.name, ""))
        values[name] = _optional_float(_safe(lambda parameter=parameter: parameter.value, None))
    return {
        "path": path,
        "device_index": device_index,
        "name": str(_safe(lambda: device.name, "")),
        "class_name": class_name,
        "is_active": bool(_safe(lambda: device.is_active, True)),
        "consequence": consequence,
        "values": values,
    }


def cmd_get_midi_chain_report(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Report the MIDI effects that rewrite what a clip says, before writing one.

    Racks are walked, not just listed: the Velocity device that caps a drum
    track's dynamics usually sits inside a MIDI Effect Rack chain, where a
    top-level scan cannot see it.
    """

    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    findings: list[dict[str, Any]] = []
    for device_index, device in enumerate(list(_safe(lambda: track.devices, []))):
        path = "track:%s/device:%s" % (track_index, device_index)
        finding = _midi_effect_finding(device, path, device_index)
        if finding is not None:
            findings.append(finding)
        chains = list(_safe(lambda device=device: device.chains, []) or [])
        for chain_index, chain in enumerate(chains):
            for inner_index, inner in enumerate(
                list(_safe(lambda chain=chain: chain.devices, []))
            ):
                inner_path = "%s/chain:%s/device:%s" % (path, chain_index, inner_index)
                inner_finding = _midi_effect_finding(inner, inner_path, device_index)
                if inner_finding is not None:
                    inner_finding["chain_index"] = chain_index
                    inner_finding["chain_name"] = str(_safe(lambda chain=chain: chain.name, ""))
                    findings.append(inner_finding)
    return {
        "track_index": track_index,
        "rewrites_input": bool(findings),
        "devices": findings,
    }


def cmd_describe_instrument(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Describe a track's instrument and state what the user must still set up.

    An agent cannot control what it cannot address. When a plugin exposes no
    configured parameter, or a rack's macros are unmapped and unnamed, the fix
    belongs to the user inside Live — so the answer carries the request to
    make, not only the gap.
    """

    track_index = _integer_param(params, "track_index")
    track = _track_at(song, track_index)
    instrument = None
    instrument_index = None
    for device_index, device in enumerate(list(_safe(lambda: track.devices, []))):
        class_name = str(_safe(lambda device=device: device.class_name, ""))
        drum_capable = bool(_safe(lambda device=device: device.can_have_drum_pads, False))
        if class_name in _INSTRUMENT_CLASSES or drum_capable:
            instrument = device
            instrument_index = device_index
            break
    if instrument is None:
        return {
            "track_index": track_index,
            "has_instrument": False,
            "setup_requests": [
                "This track has no instrument device; load one before writing notes."
            ],
        }

    class_name = str(_safe(lambda: instrument.class_name, ""))
    parameters = list(_safe(lambda: instrument.parameters, []))
    captured = [
        {
            "name": str(_safe(lambda parameter=parameter: parameter.name, "")),
            "value": _optional_float(_safe(lambda parameter=parameter: parameter.value, None)),
            "min": _optional_float(_safe(lambda parameter=parameter: parameter.min, None)),
            "max": _optional_float(_safe(lambda parameter=parameter: parameter.max, None)),
            "quantized": bool(_safe(lambda parameter=parameter: parameter.is_quantized, False)),
        }
        for parameter in parameters
    ]
    named = [item["name"] for item in captured]
    setup_requests: list[str] = []

    is_plugin = is_plugin_device_class(class_name)
    configured = _configured_parameter_count([{"name": name} for name in named])
    if is_plugin and not configured:
        setup_requests.append(
            "This plugin exposes no automatable parameter. In Live, open the "
            "device, press Configure, move the controls an agent should drive, "
            "then leave Configure."
        )
    macros = [name for name in named if name.startswith("Macro ")]
    if len(macros) >= 8:
        setup_requests.append(
            "The rack's macros still carry default names. Map each macro to the "
            "parameter it should drive and rename it: a unique name is what "
            "lets an agent address it without ambiguity."
        )
    return {
        "track_index": track_index,
        "has_instrument": True,
        "device_index": instrument_index,
        "name": str(_safe(lambda: instrument.name, "")),
        "class_name": class_name,
        "is_plugin": is_plugin,
        "configured_parameter_count": configured,
        "parameter_count": len(captured),
        "parameters": captured,
        "setup_requests": setup_requests,
    }


def cmd_get_clip_automation(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Sample one clip envelope so a caller can read back what it wrote.

    The LOM exposes no breakpoint list, only ``value_at_time``, so the envelope
    is reported as a sampled curve. That is what Live can actually answer; a
    caller comparing intent against reality gets the shape, not a promise.
    """

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    parameter_name = _string_param(params, "parameter_name")
    device_index = params.get("device_index")
    resolution = float(params.get("resolution", 0.25))
    if resolution <= 0 or resolution > 16:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'resolution' must be in (0, 16].")

    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Session slot %s is empty." % clip_index)
    parameter = _automation_parameter(
        _track_at(song, track_index),
        parameter_name,
        device_index,
        params.get("chain_index"),
        params.get("chain_device_index"),
    )
    if parameter is None:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter %r was not found on track %s." % (parameter_name, track_index),
        )
    envelope_getter = _safe(lambda: clip.automation_envelope, None)
    if not callable(envelope_getter):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose the clip automation envelope API.",
        )
    envelope = envelope_getter(parameter)
    if envelope is None:
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
            "has_envelope": False,
            "samples": [],
        }
    value_at_time = _safe(lambda: envelope.value_at_time, None)
    if not callable(value_at_time):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose value_at_time on the clip envelope.",
        )
    length = float(_safe(lambda: clip.length, 0.0) or 0.0)
    samples = []
    time = 0.0
    while time < length - 1e-9 and len(samples) < 2000:
        samples.append({"time": round(time, 4), "value": _optional_float(value_at_time(time))})
        time += resolution
    values = [item["value"] for item in samples if item["value"] is not None]
    return {
        "track_index": track_index,
        "clip_index": clip_index,
        "parameter_name": str(_safe(lambda: parameter.name, parameter_name)),
        "has_envelope": True,
        "resolution": resolution,
        "sample_count": len(samples),
        "min_value": min(values) if values else None,
        "max_value": max(values) if values else None,
        "samples": samples,
    }


def _expand_curve(
    control_points: list[tuple[float, float]],
    shape: str,
    resolution: float,
) -> list[tuple[float, float]]:
    """Densify control points into contiguous steps.

    Live's clip envelope only accepts steps, so a smooth ramp is a dense
    staircase. Expanding server-side is what keeps a caller from shipping
    hundreds of breakpoints over the wire for one crescendo.
    """

    expanded: list[tuple[float, float]] = []
    pairs = zip(control_points, control_points[1:], strict=False)
    for (time_a, value_a), (time_b, value_b) in pairs:
        span = time_b - time_a
        if span <= 0:
            continue
        if shape == "hold":
            expanded.append((time_a, value_a))
            continue
        steps = max(1, int(math.ceil(span / resolution)))
        for step in range(steps):
            progress = step / steps
            if shape == "exp":
                weight = progress**2.0
            elif shape == "log":
                weight = 1.0 - (1.0 - progress) ** 2.0
            else:
                weight = progress
            expanded.append((time_a + progress * span, value_a + (value_b - value_a) * weight))
    expanded.append(control_points[-1])
    deduped: list[tuple[float, float]] = []
    for point in expanded:
        if deduped and abs(point[0] - deduped[-1][0]) < 1e-6:
            deduped[-1] = point
            continue
        deduped.append(point)
    return deduped


def _create_clip_automation_curve_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    _clip_index = _integer_param(params, "clip_index")
    _parameter_name = _string_param(params, "parameter_name")
    raw_points = _required(params, "control_points")
    shape = str(params.get("shape", "linear")).strip().lower()
    resolution = float(params.get("resolution", 0.25))
    if shape not in ("linear", "exp", "log", "hold"):
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter 'shape' must be one of linear, exp, log, hold.",
        )
    if resolution <= 0 or resolution > 16:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'resolution' must be in (0, 16].")
    if not isinstance(raw_points, list) or len(raw_points) < 2 or len(raw_points) > 200:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "Parameter 'control_points' must hold between 2 and 200 points.",
        )
    control: list[tuple[float, float]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Each control point must be an object.")
        control.append(
            (
                _float_param(raw_point, "time", 0.0, 100000.0),
                _float_param(raw_point, "value", -100000.0, 100000.0),
            )
        )
    control.sort(key=lambda item: item[0])
    expanded = _expand_curve(control, shape, resolution)
    if len(expanded) > 500:
        raise RemoteError(
            ERROR_BAD_INPUT,
            "The expansion produced %s steps; raise 'resolution' or shorten the span "
            "so it stays inside Live's 500-step envelope budget." % len(expanded),
        )
    forwarded = dict(params)
    forwarded["automation_points"] = [{"time": time, "value": value} for time, value in expanded]
    result = yield from _create_clip_automation_steps(song, forwarded)
    result["control_points"] = len(control)
    result["shape"] = shape
    result["resolution"] = resolution
    result["track_index"] = track_index
    return result


def cmd_add_notes_pattern(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Repeat one note cell N times, with optional transposition and dynamics.

    A sixteen-bar triplet sequence is nearly two hundred near-identical notes.
    Sending the cell once and letting the server repeat it keeps the payload
    proportional to the idea instead of to its length.
    """

    _track_index = _integer_param(params, "track_index")
    _clip_index = _integer_param(params, "clip_index")
    raw_cell = _required(params, "cell")
    repeats = _integer_param(params, "repeats", minimum=1)
    cell_length = _float_param(params, "cell_length", 0.0, 100000.0, strictly_positive=True)
    transpose = params.get("transpose_per_repeat", 0)
    velocity_scale = params.get("velocity_scale_per_repeat", 1.0)
    if not isinstance(raw_cell, list) or not raw_cell:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'cell' must be a non-empty list.")
    if repeats > 128:
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'repeats' must be <= 128.")
    if isinstance(transpose, bool) or not isinstance(transpose, (int, float)):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'transpose_per_repeat' must be numeric.")
    if isinstance(velocity_scale, bool) or not isinstance(velocity_scale, (int, float)):
        raise RemoteError(
            ERROR_INVALID_PARAMS, "Parameter 'velocity_scale_per_repeat' must be numeric."
        )

    notes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        offset = repeat * cell_length
        for raw_note in raw_cell:
            if not isinstance(raw_note, dict):
                raise RemoteError(ERROR_INVALID_PARAMS, "Each note must be an object.")
            pitch = _integer_param(raw_note, "pitch") + int(round(float(transpose) * repeat))
            velocity = float(raw_note.get("velocity", 100)) * (float(velocity_scale) ** repeat)
            notes.append(
                {
                    **raw_note,
                    "pitch": max(0, min(127, pitch)),
                    "velocity": int(max(1, min(127, round(velocity)))),
                    "start_time": _float_param(raw_note, "start_time", 0.0, 100000.0) + offset,
                }
            )
    forwarded = dict(params)
    forwarded["notes"] = notes
    result = cmd_add_notes_to_clip(song, _application, forwarded)
    result["repeats"] = repeats
    result["cell_notes"] = len(raw_cell)
    return result


def _set_arrangement_clip_properties_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Rename or mute one Arrangement clip, verified by readback."""

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    new_name = params.get("name")
    muted = params.get("muted")
    if new_name is None and muted is None:
        raise RemoteError(ERROR_INVALID_PARAMS, "Provide at least one of 'name' or 'muted'.")
    _track, clip, _clips = _arrangement_clip_at(song, track_index, clip_index)
    if new_name is not None:
        if not isinstance(new_name, str) or not new_name.strip():
            raise RemoteError(ERROR_BAD_INPUT, "Parameter 'name' must be a non-empty string.")
        clip.name = new_name.strip()
    if muted is not None:
        if not isinstance(muted, bool):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'muted' must be a boolean.")
        clip.muted = muted
    yield
    observed_name = str(_safe(lambda: clip.name, ""))
    observed_muted = bool(_safe(lambda: clip.muted, False))
    if new_name is not None and observed_name != new_name.strip():
        raise RemoteError(ERROR_VERIFICATION_FAILED, "Arrangement clip rename was not observed.")
    if muted is not None and observed_muted != muted:
        raise RemoteError(ERROR_VERIFICATION_FAILED, "Arrangement clip mute was not observed.")
    return {
        "updated": True,
        "clip": _capture_arrangement_clip(clip, track_index, clip_index),
    }


def cmd_diagnose_clip_targets(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Enumerate which clips ``set_clip_color`` can and cannot reach.

    Reports Session slots and Arrangement clips per track, plus an explicit
    reason for every target that is not colourable. Nothing is written.
    """

    requested_index = params.get("track_index")
    if requested_index is not None:
        if isinstance(requested_index, bool) or not isinstance(requested_index, int):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'track_index' must be an integer.")
        indices = [requested_index]
        _track_at(song, requested_index)
    else:
        indices = list(range(len(_all_tracks(song))))

    tracks: list[dict[str, Any]] = []
    inaccessible: list[dict[str, Any]] = []
    session_total = 0
    arrangement_total = 0
    for index in indices:
        track = _track_at(song, index)
        kind = _track_type(song, track)
        session: list[dict[str, Any]] = []
        for slot_index, slot in enumerate(_safe(lambda track=track: track.clip_slots, [])):
            clip = _safe(lambda slot=slot: slot.clip, None)
            if clip is None:
                continue
            session.append(
                _capture_clip_colour_target(
                    clip,
                    scope="session",
                    track_index=index,
                    clip_index=slot_index,
                )
            )
        arrangement_clips = _arrangement_clips(track)
        arrangement: list[dict[str, Any]] = []
        if arrangement_clips is None:
            inaccessible.append(
                {
                    "track_index": index,
                    "scope": "arrangement",
                    "reason": (
                        "This host does not expose Track.arrangement_clips; "
                        "Arrangement clips cannot be reached from the Remote "
                        "Script on this Live version."
                    ),
                }
            )
        else:
            for clip_index, clip in enumerate(arrangement_clips):
                arrangement.append(
                    _capture_clip_colour_target(
                        clip,
                        scope="arrangement",
                        track_index=index,
                        clip_index=clip_index,
                    )
                )
        session_total += len(session)
        arrangement_total += len(arrangement)
        for entry in (*session, *arrangement):
            if not entry["colorable"]:
                inaccessible.append(
                    {
                        "track_index": index,
                        "scope": entry["scope"],
                        "clip_index": entry["clip_index"],
                        "reason": "Clip.color did not read back as an integer on this host.",
                    }
                )
        tracks.append(
            {
                "track_index": index,
                "track_id": "track:%s" % index,
                "name": str(_safe(lambda track=track: track.name, "")),
                "type": kind,
                "session_clips": session,
                "arrangement_clips": arrangement,
                "arrangement_supported": arrangement_clips is not None,
            }
        )
    return {
        "tracks": tracks,
        "session_clip_count": session_total,
        "arrangement_clip_count": arrangement_total,
        "inaccessible": inaccessible,
    }


def _set_clip_color_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    """Write ``Clip.color_index`` or ``Clip.color`` and read the value back.

    ``scope`` selects the lane: ``session`` resolves ``track.clip_slots[i]``,
    ``arrangement`` resolves ``track.arrangement_clips[i]``. Both properties
    are ``getsetobserve`` on Clip, so both lanes are genuinely writable where
    the host exposes them; ``diagnose_clip_targets`` reports which ones do.
    """

    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    scope = str(params.get("scope", "session")).strip().lower()
    if scope not in ("session", "arrangement"):
        raise RemoteError(ERROR_BAD_INPUT, "Parameter 'scope' must be 'session' or 'arrangement'.")
    attribute, expected = _requested_colour(params)
    if scope == "session":
        _track, slot = _clip_slot(song, track_index, clip_index)
        clip = _safe(lambda: slot.clip, None)
        if clip is None:
            raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
        clip_id = "track:%s/clipslot:%s/clip" % (track_index, clip_index)
    else:
        track = _track_at(song, track_index)
        clips = _arrangement_clips(track)
        if clips is None:
            raise RemoteError(
                ERROR_CAPABILITY_UNAVAILABLE,
                "This Live host does not expose Track.arrangement_clips.",
                "Run diagnose_clip_targets to see which clips are reachable.",
            )
        if clip_index >= len(clips):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Arrangement clip %s does not exist on track %s." % (clip_index, track_index),
            )
        clip = clips[clip_index]
        clip_id = "track:%s/arrangementclip:%s" % (track_index, clip_index)
    observed = yield from _verified_colour_write_steps(
        clip,
        attribute=attribute,
        expected=expected,
        label="Clip %s" % clip_id,
    )
    resolved: dict[str, Any] = {
        "kind": "clip",
        "track_index": track_index,
        "clip_index": clip_index,
        "scope": scope,
        "clip_id": clip_id,
    }
    clip_name = str(_safe(lambda: clip.name, ""))
    if clip_name:
        resolved["clip_name"] = clip_name
    return {
        "clip_id": clip_id,
        "scope": scope,
        "track_index": track_index,
        "clip_index": clip_index,
        "property": attribute,
        "color": observed["color"],
        "color_index": observed["color_index"],
        "resolved": resolved,
    }


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
        _float_param(params, "loop_start", 0.0, 100000.0) if "loop_start" in params else None
    )
    requested_end = (
        _float_param(params, "loop_end", 0.0, 100000.0) if "loop_end" in params else None
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


def _automation_parameter(
    track: Any,
    parameter_name: str,
    device_index: Any = None,
    chain_index: Any = None,
    chain_device_index: Any = None,
) -> Any:
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
    devices = list(_safe(lambda: track.devices, []))
    if chain_index is not None:
        if device_index is None:
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Addressing a chain parameter needs 'device_index' as well as 'chain_index'.",
            )
        if isinstance(device_index, bool) or not isinstance(device_index, int):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'device_index' must be an integer.")
        if device_index < 0 or device_index >= len(devices):
            raise RemoteError(
                ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index
            )
        chain = _chain_at(devices[device_index], chain_index, -1, device_index)
        if chain_device_index is None:
            mixer = _safe(lambda: chain.mixer_device, None)
            alias = {"volume": "volume", "pan": "panning", "panning": "panning"}.get(
                parameter_name.strip().casefold()
            )
            if mixer is None or alias is None:
                raise RemoteError(
                    ERROR_INVALID_PARAMS,
                    "A chain mixer exposes 'volume' and 'panning'; pass "
                    "'chain_device_index' to reach a device inside the chain.",
                )
            return _safe(lambda: getattr(mixer, alias), None)
        inner_devices = list(_safe(lambda: chain.devices, []))
        if (
            isinstance(chain_device_index, bool)
            or not isinstance(chain_device_index, int)
            or chain_device_index < 0
            or chain_device_index >= len(inner_devices)
        ):
            raise RemoteError(
                ERROR_INVALID_PARAMS,
                "Chain device %s does not exist in chain %s."
                % (chain_device_index, chain_index),
            )
        for parameter in _safe(lambda: inner_devices[chain_device_index].parameters, []):
            if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
                return parameter
        return None
    if device_index is not None:
        if isinstance(device_index, bool) or not isinstance(device_index, int):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'device_index' must be an integer.")
        if device_index < 0 or device_index >= len(devices):
            raise RemoteError(
                ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index
            )
        devices = [devices[device_index]]
    matches = []
    for position, device in enumerate(devices):
        for parameter in _safe(lambda device=device: device.parameters, []):
            if str(_safe(lambda parameter=parameter: parameter.name, "")) == parameter_name:
                matches.append((position if device_index is None else device_index, parameter))
    if not matches:
        return None
    if len(matches) > 1:
        # Silently taking the first match is how an envelope lands on the wrong
        # rack: "Macro 1" exists on every rack of a track. Name the candidates
        # and let the caller disambiguate with device_index.
        raise RemoteError(
            ERROR_AMBIGUOUS_MATCH,
            "Parameter %r exists on devices %s of this track. Pass 'device_index' "
            "to choose one." % (parameter_name, [position for position, _ in matches]),
            details={"candidates": [position for position, _ in matches]},
        )
    return matches[0][1]


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
    parameter = _automation_parameter(
        track,
        parameter_name,
        params.get("device_index"),
        params.get("chain_index"),
        params.get("chain_device_index"),
    )
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
    envelope_getter = _safe(lambda: clip.automation_envelope, None)
    envelope_creator = _safe(lambda: clip.create_automation_envelope, None)
    clear_envelope = _safe(lambda: clip.clear_envelope, None)
    if (not callable(envelope_getter) and not callable(envelope_creator)) or not callable(
        clear_envelope
    ):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose the clip automation envelope API.",
        )
    clear_envelope(parameter)
    envelope = None
    if callable(envelope_getter):
        envelope = envelope_getter(parameter)
    if envelope is None and callable(envelope_creator):
        envelope = envelope_creator(parameter)
    if envelope is None:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime failed to retrieve or create the clip automation envelope.",
        )
    insert_step = _safe(lambda: envelope.insert_step, None)
    if not callable(insert_step):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not expose automation envelope insertion.",
        )
    for index, (point_time, value) in enumerate(points):
        # A zero-length step writes a value that occupies no time, so the
        # envelope falls back to the parameter value between breakpoints and
        # the curve reads as a comb of spikes. Each step has to reach the next
        # breakpoint for the envelope to be continuous; the last one keeps the
        # zero length because there is nothing after it to cover.
        duration = points[index + 1][0] - point_time if index + 1 < len(points) else 0.0
        insert_step(point_time, duration, value)
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


def cmd_create_audio_track(
    song,
    _application,
    params,
):
    # type: (Any, Any, dict[str, Any]) -> dict[str, Any]
    # v0.5.0 — Mirror cmd_create_midi_track for audio. Zero-touch on the midi path:
    # the existing TRACK_LIMIT_REACHED guard above is not reused because audio may
    # legitimately exceed 96 tracks on hosts that already grew the midi set past
    # the cap. We rely on Live's per-host track-limit instead.
    #
    # Slice 1 Task 4: Live's LOM yields a new proxy wrapper per enumeration, so
    # ``id()`` comparisons collapse to the proxy identity. We now identify the
    # new track by counting the collection before and after the mutation and
    # resolving the requested index against the verified post-mutation list.
    fn = getattr(song, "create_audio_track", None)
    if not callable(fn):
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live Song object does not expose create_audio_track()",
        )
    raw_index = params.get("index")
    index = int(raw_index) if raw_index is not None else -1
    name = params.get("name")
    before_count = len(list(song.tracks))
    fn(index)
    tracks = list(song.tracks)
    if len(tracks) != before_count + 1:
        raise RemoteError(
            ERROR_VERIFICATION_FAILED,
            "create_audio_track did not increase the regular track count by one",
        )
    created_index = len(tracks) - 1 if index == -1 else index
    if created_index < 0 or created_index >= len(tracks):
        raise RemoteError(ERROR_VERIFICATION_FAILED, "created track index is out of range")
    created = tracks[created_index]
    if name:
        created.name = str(name)
    return {
        "created": True,
        "track_id": "track:%s" % created_index,
        "track_index": created_index,
        "requested_index": index,
        "track_name": str(getattr(created, "name", "")),
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
    effective_clock: Callable[[], float] = clock or time.monotonic
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
    "live_find_device": cmd_live_find_device,
    "live_find_clip": cmd_live_find_clip,
    "list_device_params": cmd_list_device_params,
    # v0.5.4 — plugin presets bypass Live's Configure gate
    "get_plugin_presets": cmd_get_plugin_presets,
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
    # v0.5.0 — audio-track mirror of create_midi_track. Zero-touch on the midi path.
    "create_audio_track": cmd_create_audio_track,
    # v0.5.3 — clip colour target discovery (Session + Arrangement)
    "diagnose_clip_targets": cmd_diagnose_clip_targets,
    # v0.5.5 — Arrangement timeline read
    "get_arrangement_clips": cmd_get_arrangement_clips,
    # v0.5.6 — instrument comprehension and authoring shorthands
    "get_device_chains": cmd_get_device_chains,
    "get_midi_chain_report": cmd_get_midi_chain_report,
    "describe_instrument": cmd_describe_instrument,
    "get_clip_automation": cmd_get_clip_automation,
    "add_notes_pattern": cmd_add_notes_pattern,
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
            yield from _run_batch_steps(song, application, params, undo_target, control_surface)
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
        dry_run = params.get("dry_run", False)
        if dry_run:
            return {
                "tempo": tempo,
                "committed": False,
                "resolved": {"kind": "tempo", "tempo": tempo},
            }
        result: dict[str, Any] = yield from _verified_numeric_steps(
            song,
            attribute="tempo",
            expected=tempo,
            result_key="tempo",
        )
        result["resolved"] = {"kind": "tempo", "tempo": result["tempo"]}
        return result
    if normalized == "set_parameter_value":
        return (yield from _set_parameter_value_steps(song, params))
    if normalized == "set_plugin_preset":
        return (yield from _set_plugin_preset_steps(song, params))
    if normalized == "clear_clip_notes":
        return (yield from _clear_clip_notes_steps(song, params))
    if normalized == "set_track_property":
        return (yield from _set_track_property_steps(song, params))
    if normalized == "set_track_color":
        return (yield from _set_track_color_steps(song, params))
    if normalized == "set_clip_color":
        return (yield from _set_clip_color_steps(song, params))
    if normalized == "set_clip_properties":
        return (yield from _set_clip_properties_steps(song, params))
    if normalized == "create_clip_automation":
        return (yield from _create_clip_automation_steps(song, params))
    if normalized == "duplicate_session_clip_to_arrangement":
        return (yield from _duplicate_session_clip_to_arrangement_steps(song, params))
    if normalized == "delete_arrangement_clip":
        return (yield from _delete_arrangement_clip_steps(song, params))
    if normalized == "move_arrangement_clip":
        return (yield from _move_arrangement_clip_steps(song, params))
    if normalized == "create_clip_automation_curve":
        return (yield from _create_clip_automation_curve_steps(song, params))
    if normalized == "set_arrangement_clip_properties":
        return (yield from _set_arrangement_clip_properties_steps(song, params))
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
        # ``live_fade_steps`` is a generator that distributes its writes
        # across ``duration`` of monotonic-clock time and yields between
        # writes; ``yield from`` keeps the Live main thread pumping while it
        # waits for each step's deadline.
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
    if normalized in UNSUPPORTED_CAPABILITIES:
        # Distinct from UNKNOWN_COMMAND on purpose: the operation is real in
        # Live's UI but has no supported entry point in the public LOM or the
        # Extension SDK, so no amount of bridge work will make it available.
        # The request is still validated against the real Set first, and no
        # undo step is opened because nothing is ever written.
        return cmd_unavailable_capability(song, application, {**params, "__command": normalized})
    if not isinstance(params, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
    dry_run_only = _is_dry_run_only(normalized, params)
    owns_undo = normalized in ALLOWED_MUTATIONS and manage_undo and not dry_run_only
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


def _is_dry_run_only(normalized: str, params: dict[str, Any]) -> bool:
    if normalized in ("set_tempo", "create_clip"):
        dry_run = params.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'dry_run' must be boolean.")
        return dry_run
    if normalized != "run_batch":
        return False

    commands = params.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    for command in commands:
        if not isinstance(command, dict):
            return False
        if command.get("type") not in ("set_tempo", "create_clip"):
            return False
        command_params = command.get("params", {})
        if not isinstance(command_params, dict) or command_params.get("dry_run") is not True:
            return False
    return True


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
