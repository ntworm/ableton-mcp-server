"""Ableton Live MIDI Remote Script for the Ableton MCP Server.

Socket work runs in background threads. Every Live Object Model access is
dispatched by :meth:`AbletonMCPServer.update_display` on Live's main thread.
"""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import socket
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from ._contracts import (
    ALLOWED_MUTATIONS,
    CUE_TIME_TOLERANCE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ERROR_BAD_INPUT,
    ERROR_INTERNAL_ERROR,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_PLAYHEAD_NOT_MOVED,
    ERROR_READ_ONLY_VIOLATION,
    ERROR_STALE_REFERENCE,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN_COMMAND,
    ERROR_WRONG_TYPE,
    PLAYHEAD_MOVE_RETRIES,
    PLAYHEAD_MOVE_SLEEP,
    READ_ONLY_COMMANDS,
    REQUEST_TIMEOUT_SECONDS,
)

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
        logger.info("[PROBE] %s", message)


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


@dataclass(frozen=True)
class _FallbackMidiNoteSpecification:
    """Test-only stand-in for ``Live.Clip.MidiNoteSpecification``."""

    pitch: int
    start_time: float
    duration: float
    velocity: int
    mute: bool


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
        raise RemoteError(
            ERROR_INVALID_PARAMS, "Parameter %r must be numeric." % name
        ) from error
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


def _set_transport_value(
    song: Any,
    attribute: str,
    value: float,
    *,
    retries: int = PLAYHEAD_MOVE_RETRIES,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> float:
    """Set, read, compare, and retry a transport property by explicit attribute name."""

    if retries < 1:
        raise ValueError("retries must be at least 1")
    previous_quantization = song.clip_trigger_quantization
    actual = float(_safe(lambda: getattr(song, attribute), -1.0))
    try:
        song.clip_trigger_quantization = _no_quantization_value()
        for attempt in range(retries):
            setattr(song, attribute, value)
            actual = float(getattr(song, attribute))
            _dbg(
                "transport attribute=%s asked=%s got=%s attempt=%s"
                % (attribute, value, actual, attempt + 1)
            )
            if abs(actual - value) < CUE_TIME_TOLERANCE:
                return actual
            if attempt + 1 < retries:
                sleep_fn(PLAYHEAD_MOVE_SLEEP)
        raise PlayheadNotMovedError(value, actual, retries)
    finally:
        song.clip_trigger_quantization = previous_quantization


def _restore_transport(song: Any, attribute: str, value: float) -> None:
    _set_transport_value(song, attribute, float(value))


def _find_cue(song: Any, target_time: float) -> Any:
    for cue in song.cue_points:
        if abs(float(cue.time) - target_time) < CUE_TIME_TOLERANCE:
            return cue
    return None


def cmd_create_cue_point(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = _string_param(params, "name")
    target_time = _float_param(params, "time", 0.0, 100000.0)
    existing = _find_cue(song, target_time)
    if existing is not None:
        existing.name = name
        return {"name": name, "time": float(existing.time), "action": "renamed"}

    previous_time = float(song.current_song_time)
    _dbg("create_cue_point name=%r time=%s prev=%s" % (name, target_time, previous_time))
    try:
        _set_transport_value(song, "current_song_time", target_time)
        song.set_or_delete_cue()
        created = _find_cue(song, target_time)
        if created is None:
            raise RemoteError(
                ERROR_LIVE_UNAVAILABLE,
                "set_or_delete_cue() did not create a cue near %s." % target_time,
            )
        created.name = name
        return {"name": name, "time": float(created.time), "action": "created"}
    finally:
        _restore_transport(song, "current_song_time", previous_time)


def cmd_bulk_create_cue_points(
    song: Any, application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    items = _required(params, "items")
    if not isinstance(items, list) or not items:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'items' must be a non-empty list.")
    results = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            error = RemoteError(ERROR_INVALID_PARAMS, "Cue item must be an object.")
            results.append({"index": index, **error.to_envelope()})
            continue
        try:
            result = cmd_create_cue_point(song, application, item)
            results.append({"index": index, "status": "ok", "result": result})
        except RemoteError as error:
            results.append({"index": index, **error.to_envelope()})
    return {"results": results}


def cmd_delete_cue_point(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, Any]:
    target_time = _float_param(params, "time", 0.0, 100000.0)
    cue = _find_cue(song, target_time)
    if cue is None:
        return {"deleted": False, "reason": "no cue at time"}
    cue_time = float(cue.time)
    previous_time = float(song.current_song_time)
    try:
        _set_transport_value(song, "current_song_time", cue_time)
        song.set_or_delete_cue()
    finally:
        _restore_transport(song, "current_song_time", previous_time)
    return {"deleted": True, "time": cue_time}


def cmd_set_current_song_time(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, float]:
    target = _float_param(params, "time", 0.0, 100000.0)
    return {"current_song_time": _set_transport_value(song, "current_song_time", target)}


def cmd_set_tempo(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, float]:
    tempo = _float_param(params, "tempo", 20.0, 999.0)
    song.tempo = tempo
    return {"tempo": float(song.tempo)}


def cmd_start_playback(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, bool]:
    song.start_playing()
    return {"is_playing": bool(song.is_playing)}


def cmd_stop_playback(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, bool]:
    song.stop_playing()
    return {"is_playing": bool(song.is_playing)}


def cmd_set_loop(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, bool]:
    enabled = _required(params, "enabled")
    if not isinstance(enabled, bool):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'enabled' must be boolean.")
    song.loop = enabled
    return {"loop": bool(song.loop)}


def cmd_set_loop_start(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, float]:
    start = _float_param(params, "start_beat", 0.0, 100000.0)
    return {"loop_start": _set_transport_value(song, "loop_start", start)}


def cmd_set_loop_length(song: Any, _application: Any, params: dict[str, Any]) -> dict[str, float]:
    length = _float_param(params, "length_beats", 0.0, 100000.0, strictly_positive=True)
    return {"loop_length": _set_transport_value(song, "loop_length", length)}


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
        note = _midi_note_specification(
            pitch=pitch,
            start_time=_float_param(raw_note, "start_time", 0.0, 100000.0),
            duration=_float_param(
                raw_note, "duration", 0.0, 100000.0, strictly_positive=True
            ),
            velocity=velocity,
            mute=bool(raw_note.get("mute", False)),
        )
        notes.append(note)
    note_ids = clip.add_new_notes(tuple(notes))
    return {
        "added": len(notes),
        "note_ids": [int(note_id) for note_id in note_ids],
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }


CommandHandler = Callable[[Any, Any, dict[str, Any]], Any]

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
    "get_device_list": cmd_get_device_list,
    "get_parameter_value": cmd_get_parameter_value,
    "get_routing": cmd_get_routing,
    "get_browser_categories": cmd_get_browser_categories,
    "get_song_length": cmd_get_song_length,
    "live_find_track": cmd_live_find_track,
    "list_device_params": cmd_list_device_params,
    "create_cue_point": cmd_create_cue_point,
    "bulk_create_cue_points": cmd_bulk_create_cue_points,
    "delete_cue_point": cmd_delete_cue_point,
    "set_current_song_time": cmd_set_current_song_time,
    "set_tempo": cmd_set_tempo,
    "start_playback": cmd_start_playback,
    "stop_playback": cmd_stop_playback,
    "set_loop": cmd_set_loop,
    "set_loop_start": cmd_set_loop_start,
    "set_loop_length": cmd_set_loop_length,
    "create_clip": cmd_create_clip,
    "fire_clip": cmd_fire_clip,
    "add_notes_to_clip": cmd_add_notes_to_clip,
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


def cmd_run_batch(
    song: Any,
    application: Any,
    params: dict[str, Any],
    undo_target: Any,
) -> dict[str, Any]:
    commands = _required(params, "commands")
    if not isinstance(commands, list) or not commands:
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'commands' must be a non-empty list.")
    results = []
    completed = 0
    aborted_at = None
    _begin_undo(undo_target)
    try:
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
                    raise RemoteError(
                        ERROR_INVALID_PARAMS, "Batch command params must be an object."
                    )
                result = execute_command(
                    song,
                    application,
                    str(command_type),
                    command_params,
                    manage_undo=False,
                    undo_target=undo_target,
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
    finally:
        _end_undo(undo_target)
    return {
        "results": results,
        "completed": completed,
        "aborted_at": aborted_at,
        "rolled_back": False,
    }


def execute_command(
    song: Any,
    application: Any,
    command: str,
    params: dict[str, Any],
    *,
    manage_undo: bool = True,
    undo_target: Any = None,
) -> Any:
    normalized = command.strip().lower()
    if normalized in READ_ONLY_COMMANDS:
        raise RemoteError(
            ERROR_READ_ONLY_VIOLATION,
            "Command %r is blocked: creative mutation is not available." % command,
        )
    if not isinstance(params, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
    target = undo_target if undo_target is not None else application
    if normalized == "run_batch":
        return cmd_run_batch(song, application, params, target)
    handler = COMMAND_HANDLERS.get(normalized)
    if handler is None:
        raise RemoteError(ERROR_UNKNOWN_COMMAND, "Unknown command %r." % command)
    if normalized in ALLOWED_MUTATIONS and manage_undo:
        _begin_undo(target)
        try:
            return handler(song, application, params)
        finally:
            _end_undo(target)
    return handler(song, application, params)


@dataclass
class QueuedRequest:
    command: str
    params: dict[str, Any]
    response_queue: queue.Queue[dict[str, Any]]


class RequestProcessor:
    """Owns the UI-thread queue; socket threads only call :meth:`enqueue`."""

    def __init__(self, song: Any, application: Any, undo_target: Any = None) -> None:
        self.song = song
        self.application = application
        self.undo_target = undo_target if undo_target is not None else application
        self.request_queue: queue.Queue[QueuedRequest] = queue.Queue()

    def enqueue(self, request: QueuedRequest) -> None:
        self.request_queue.put(request)

    def process_pending(self, max_requests: int = 16) -> int:
        processed = 0
        while processed < max_requests:
            try:
                request = self.request_queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = execute_command(
                    self.song,
                    self.application,
                    request.command,
                    request.params,
                    undo_target=self.undo_target,
                )
                response = {"status": "ok", "result": result}
            except RemoteError as error:
                response = error.to_envelope()
            except Exception as error:
                logger.exception("Unhandled Remote Script error for %s", request.command)
                response = RemoteError(ERROR_LIVE_UNAVAILABLE, str(error)).to_envelope()
            request.response_queue.put(response)
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
        connection.settimeout(10.0)
        try:
            while not self.shutdown_event.is_set():
                chunk = connection.recv(4096)
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
            return response_queue.get(timeout=REQUEST_TIMEOUT_SECONDS)
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
        self._processor = RequestProcessor(song, application, undo_target)
        self._socket_server = JsonlSocketServer(self._processor)
        self._socket_server.start()
        self.show_message("AbletonMCPServer: Active on 127.0.0.1:9888")

    def update_display(self) -> None:
        super().update_display()
        self._processor.process_pending()

    def disconnect(self) -> None:
        self._socket_server.stop()
        super().disconnect()


def create_instance(c_instance: Any) -> AbletonMCPServer:
    return AbletonMCPServer(c_instance)
