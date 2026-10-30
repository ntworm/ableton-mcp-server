"""Arrangement clip reads, edits and clip target diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from ._contracts import (
    ERROR_BAD_INPUT,
    ERROR_CAPABILITY_UNAVAILABLE,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_VERIFICATION_FAILED,
)
from .common import RemoteError, _float_param, _integer_param, _optional_float, _optional_int, _safe
from .lom import _all_tracks, _clip_slot, _track_at, _track_type


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


def _lane_after(track: Any, seen: Callable[[list[Any]], bool]) -> Generator[None, None, list[Any]]:
    """Confirm an edit in its own tick (one undo step, KNOWN_BUGS H); wait a tick only if unseen."""
    clips = _arrangement_clips(track) or []
    if not seen(clips):
        yield
        clips = _arrangement_clips(track) or []
    return clips


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

    count_before = len(_arrangement_clips(track) or [])
    duplicate(clip, destination)
    after = yield from _lane_after(track, lambda clips: len(clips) > count_before)
    if len(after) <= count_before:
        message = "Arrangement clip creation was not observed on track %s." % track_index
        raise RemoteError(ERROR_LIVE_UNAVAILABLE, message)

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
        message = "This host does not expose Track.delete_clip."
        raise RemoteError(ERROR_CAPABILITY_UNAVAILABLE, message)
    delete(clip)
    remaining = yield from _lane_after(track, lambda clips: len(clips) < count_before)
    if len(remaining) >= count_before:
        message = "Arrangement clip deletion was not observed on track %s." % track_index
        raise RemoteError(ERROR_LIVE_UNAVAILABLE, message)
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
    after_copy = yield from _lane_after(track, lambda clips: len(clips) > count_before)
    if len(after_copy) <= count_before:
        raise RemoteError(
            ERROR_LIVE_UNAVAILABLE,
            "The copy step of the move was not observed; the original clip was kept.",
        )

    delete(clip)
    remaining = yield from _lane_after(track, lambda clips: len(clips) < len(after_copy))
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


def _apply_arrangement_clip_properties(clip: Any, new_name: Any, muted: Any) -> None:
    """Write the requested Arrangement clip properties, name before mute."""

    if new_name is not None:
        if not isinstance(new_name, str) or not new_name.strip():
            raise RemoteError(ERROR_BAD_INPUT, "Parameter 'name' must be a non-empty string.")
        clip.name = new_name.strip()
    if muted is not None:
        if not isinstance(muted, bool):
            raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'muted' must be a boolean.")
        clip.muted = muted


def _verify_arrangement_clip_properties(clip: Any, new_name: Any, muted: Any) -> None:
    """Confirm the written Arrangement clip properties read back as asked."""

    observed_name = str(_safe(lambda: clip.name, ""))
    observed_muted = bool(_safe(lambda: clip.muted, False))
    if new_name is not None and observed_name != new_name.strip():
        raise RemoteError(ERROR_VERIFICATION_FAILED, "Arrangement clip rename was not observed.")
    if muted is not None and observed_muted != muted:
        raise RemoteError(ERROR_VERIFICATION_FAILED, "Arrangement clip mute was not observed.")


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
    _apply_arrangement_clip_properties(clip, new_name, muted)
    yield
    _verify_arrangement_clip_properties(clip, new_name, muted)
    return {
        "updated": True,
        "clip": _capture_arrangement_clip(clip, track_index, clip_index),
    }


def _requested_track_indices(song: Any, params: dict[str, Any]) -> list[int]:
    """Resolve the tracks to diagnose, validating an explicit index."""

    requested_index = params.get("track_index")
    if requested_index is None:
        return list(range(len(_all_tracks(song))))
    if isinstance(requested_index, bool) or not isinstance(requested_index, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'track_index' must be an integer.")
    _track_at(song, requested_index)
    return [requested_index]


def _session_clip_colour_targets(track: Any, index: int) -> list[dict[str, Any]]:
    """List the Session slots of one track that hold a clip."""

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
    return session


def _arrangement_clip_colour_targets(
    track: Any, index: int
) -> tuple[list[Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """List one track's Arrangement clips, or why they cannot be reached."""

    arrangement_clips = _arrangement_clips(track)
    if arrangement_clips is None:
        reason = {
            "track_index": index,
            "scope": "arrangement",
            "reason": (
                "This host does not expose Track.arrangement_clips; "
                "Arrangement clips cannot be reached from the Remote "
                "Script on this Live version."
            ),
        }
        return None, [], [reason]
    arrangement: list[dict[str, Any]] = []
    for clip_index, clip in enumerate(arrangement_clips):
        arrangement.append(
            _capture_clip_colour_target(
                clip,
                scope="arrangement",
                track_index=index,
                clip_index=clip_index,
            )
        )
    return arrangement_clips, arrangement, []


def _diagnose_track_clip_targets(
    song: Any, index: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Collect one track's clip targets and the reasons some are unreachable."""

    track = _track_at(song, index)
    kind = _track_type(song, track)
    session = _session_clip_colour_targets(track, index)
    arrangement_clips, arrangement, reasons = _arrangement_clip_colour_targets(track, index)
    for entry in (*session, *arrangement):
        if not entry["colorable"]:
            reasons.append(
                {
                    "track_index": index,
                    "scope": entry["scope"],
                    "clip_index": entry["clip_index"],
                    "reason": "Clip.color did not read back as an integer on this host.",
                }
            )
    target = {
        "track_index": index,
        "track_id": "track:%s" % index,
        "name": str(_safe(lambda track=track: track.name, "")),
        "type": kind,
        "session_clips": session,
        "arrangement_clips": arrangement,
        "arrangement_supported": arrangement_clips is not None,
    }
    return target, reasons


def cmd_diagnose_clip_targets(
    song: Any, _application: Any, params: dict[str, Any]
) -> dict[str, Any]:
    """Enumerate which clips ``set_clip_color`` can and cannot reach.

    Reports Session slots and Arrangement clips per track, plus an explicit
    reason for every target that is not colourable. Nothing is written.
    """

    indices = _requested_track_indices(song, params)
    tracks: list[dict[str, Any]] = []
    inaccessible: list[dict[str, Any]] = []
    session_total = 0
    arrangement_total = 0
    for index in indices:
        target, reasons = _diagnose_track_clip_targets(song, index)
        tracks.append(target)
        inaccessible.extend(reasons)
        session_total += len(target["session_clips"])
        arrangement_total += len(target["arrangement_clips"])
    return {
        "tracks": tracks,
        "session_clip_count": session_total,
        "arrangement_clip_count": arrangement_total,
        "inaccessible": inaccessible,
    }
