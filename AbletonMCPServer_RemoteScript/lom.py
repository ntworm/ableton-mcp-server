"""Track, clip slot, device and chain lookups, and the captures built on them."""

from __future__ import annotations

import re
from typing import Any

from ._contracts import (
    ERROR_BAD_INPUT,
    ERROR_INVALID_PARAMS,
    ERROR_STALE_REFERENCE,
    ERROR_WRONG_TYPE,
    PLUGIN_NOT_CONFIGURED,
    PLUGIN_NOT_CONFIGURED_HINT,
    is_plugin_device_class,
)
from .common import RemoteError, _optional_int, _safe


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


# ``Device.type`` codes. Live keeps a chain in the order MIDI effects, one
# instrument, audio effects, and refuses an insert that breaks it.
_DEVICE_TYPES = {1: "instrument", 2: "audio_effect", 4: "midi_effect"}


def _device_type(device: Any) -> str:
    """Return ``Device.type`` as text, or ``undefined`` when Live reports none."""
    return _DEVICE_TYPES.get(_safe(lambda: int(device.type), 0), "undefined")


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
        "type": _device_type(device),
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


def _device_at(song: Any, track_index: int, device_index: int) -> tuple[Any, Any]:
    track = _track_at(song, track_index)
    devices = list(_safe(lambda: track.devices, []))
    if device_index < 0 or device_index >= len(devices):
        raise RemoteError(ERROR_INVALID_PARAMS, "Device index %s does not exist." % device_index)
    return track, devices[device_index]


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
