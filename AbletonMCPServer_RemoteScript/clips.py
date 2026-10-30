"""Session clip creation, firing, deletion, notes, properties and colours."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from ._contracts import (
    ERROR_BAD_INPUT,
    ERROR_CAPABILITY_UNAVAILABLE,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_WRONG_TYPE,
)
from .arrangement import _arrangement_clips
from .common import (
    RemoteError,
    _float_param,
    _integer_param,
    _midi_note_specification,
    _required,
    _safe,
    _string_param,
)
from .lom import _clip_slot, _track_at, _track_type
from .tracks import _requested_colour, _verified_colour_write_steps
from .transport import _verified_attribute_numeric_steps, _verified_attribute_string_steps


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


def _validate_pattern_params(
    raw_cell: Any, repeats: int, transpose: Any, velocity_scale: Any
) -> None:
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


def _pattern_notes(
    raw_cell: Any, repeats: int, cell_length: float, transpose: Any, velocity_scale: Any
) -> list[dict[str, Any]]:
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
    return notes


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
    _validate_pattern_params(raw_cell, repeats, transpose, velocity_scale)
    notes = _pattern_notes(raw_cell, repeats, cell_length, transpose, velocity_scale)
    forwarded = dict(params)
    forwarded["notes"] = notes
    result = cmd_add_notes_to_clip(song, _application, forwarded)
    result["repeats"] = repeats
    result["cell_notes"] = len(raw_cell)
    return result


def _colour_target_clip(
    song: Any, track_index: int, clip_index: int, scope: str
) -> tuple[Any, str]:
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
    return clip, clip_id


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
    clip, clip_id = _colour_target_clip(song, track_index, clip_index, scope)
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


def _require_clip_property(params: dict[str, Any]) -> None:
    requested_names = [name for name in ("loop_start", "loop_end", "name") if name in params]
    if not requested_names:
        raise RemoteError(
            ERROR_INVALID_PARAMS,
            "At least one of loop_start, loop_end, or name is required.",
        )


def _requested_clip_property_values(
    params: dict[str, Any]
) -> tuple[float | None, float | None, str | None]:
    requested_start = (
        _float_param(params, "loop_start", 0.0, 100000.0) if "loop_start" in params else None
    )
    requested_end = (
        _float_param(params, "loop_end", 0.0, 100000.0) if "loop_end" in params else None
    )
    requested_name = _string_param(params, "name") if "name" in params else None
    return requested_start, requested_end, requested_name


def _clip_numeric_write_steps(
    clip: Any,
    requested_start: float | None,
    requested_end: float | None,
    final_start: float,
    current_end: float,
) -> Generator[None, None, list[dict[str, Any]]]:
    numeric_order = ["loop_start", "loop_end"]
    if requested_start is not None and requested_end is not None and final_start >= current_end:
        numeric_order.reverse()
    observed_values: list[dict[str, Any]] = []
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
        observed_values.append(observed)
    return observed_values


def _clip_name_write_steps(clip: Any, requested_name: str) -> Generator[None, None, dict[str, Any]]:
    observed_name = yield from _verified_attribute_string_steps(
        clip,
        attribute="name",
        expected=requested_name,
        result_key="name",
    )
    return observed_name


def _set_clip_properties_steps(
    song: Any,
    params: dict[str, Any],
) -> Generator[None, None, dict[str, Any]]:
    track_index = _integer_param(params, "track_index")
    clip_index = _integer_param(params, "clip_index")
    _require_clip_property(params)
    _track, slot = _clip_slot(song, track_index, clip_index)
    clip = _safe(lambda: slot.clip, None)
    if clip is None:
        raise RemoteError(ERROR_BAD_INPUT, "Clip slot is empty.")
    current_start = float(_safe(lambda: clip.loop_start, 0.0))
    current_end = float(_safe(lambda: clip.loop_end, _safe(lambda: clip.length, 0.0)))
    requested_start, requested_end, requested_name = _requested_clip_property_values(params)
    final_start = requested_start if requested_start is not None else current_start
    final_end = requested_end if requested_end is not None else current_end
    if final_start >= final_end:
        raise RemoteError(ERROR_BAD_INPUT, "loop_start must be less than loop_end.")
    result: dict[str, Any] = {}
    numeric_results = yield from _clip_numeric_write_steps(
        clip,
        requested_start,
        requested_end,
        final_start,
        current_end,
    )
    for observed in numeric_results:
        result.update(observed)
    if requested_name is not None:
        observed_name = yield from _clip_name_write_steps(clip, requested_name)
        result.update(observed_name)
    result["clip_id"] = "track:%s/clipslot:%s/clip" % (track_index, clip_index)
    return result


def _clip_note_values(raw_note: dict[str, Any]) -> dict[str, Any]:
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
    return note_values


def _clip_note(raw_note: Any) -> Any:
    if not isinstance(raw_note, dict):
        raise RemoteError(ERROR_INVALID_PARAMS, "Each note must be an object.")
    note_values = _clip_note_values(raw_note)
    try:
        note = _midi_note_specification(**note_values)
    except (AttributeError, TypeError) as error:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "Live runtime does not support the requested MIDI note expression fields.",
        ) from error
    return note


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
        notes.append(_clip_note(raw_note))
    note_ids = clip.add_new_notes(tuple(notes))
    return {
        "added": len(notes),
        "note_ids": [int(note_id) for note_id in note_ids],
        "clip_id": "track:%s/clipslot:%s/clip" % (track_index, clip_index),
    }
