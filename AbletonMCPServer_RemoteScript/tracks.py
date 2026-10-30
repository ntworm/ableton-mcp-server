"""Track creation, renaming, properties, colours and group hierarchy checks."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from ._contracts import (
    CAPABILITY_EVIDENCE,
    ERROR_BAD_INPUT,
    ERROR_CAPABILITY_UNAVAILABLE,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_TRACK_LIMIT_REACHED,
    ERROR_UNKNOWN_COMMAND,
    ERROR_VERIFICATION_FAILED,
    ERROR_WRONG_TYPE,
    LIVE_COLOR_INDEX_MAX,
    LIVE_COLOR_INDEX_MIN,
    LIVE_COLOR_RGB_MAX,
    LIVE_COLOR_RGB_MIN,
    UNSUPPORTED_CAPABILITIES,
)
from .common import (
    RemoteError,
    _bounded_int_param,
    _integer_param,
    _optional_int,
    _required,
    _safe,
    _string_param,
)
from .lom import _all_tracks, _group_track_index, _track_at, _track_type
from .transport import _verified_attribute_boolean_steps


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


def _validate_move_track(song: Any, params: dict[str, Any], regular_count: int) -> dict[str, Any]:
    """Validate a ``move_track`` request and echo back what was asked for."""

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


def _validate_reorder_tracks(params: dict[str, Any], regular_count: int) -> dict[str, Any]:
    """Validate a ``reorder_tracks`` request and echo back what was asked for."""

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


def _validate_move_track_to_group(song: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Validate a ``move_track_to_group`` request and echo back what was asked for."""

    source = _integer_param(params, "track_index")
    group_index = _integer_param(params, "group_track_index")
    _require_regular_track(song, source, "track_index")
    _require_group_track(song, group_index, "group_track_index")
    _reject_group_cycle(song, source, group_index)
    return {"track_index": source, "group_track_index": group_index}


def _validate_ungroup_track(song: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Validate an ``ungroup_track`` request and echo back what was asked for."""

    source = _integer_param(params, "track_index")
    track = _require_regular_track(song, source, "track_index")
    if not bool(_safe(lambda: track.is_grouped, False)):
        raise RemoteError(
            ERROR_WRONG_TYPE,
            "Track %s is not inside a Group Track." % source,
        )
    return {"track_index": source, "group_track_index": _group_track_index(song, track)}


def _validate_merge_groups(song: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Validate a ``merge_groups`` request and echo back what was asked for."""

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


def _validate_hierarchy_request(song: Any, command: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate a hierarchy request and echo back what was asked for.

    Validation runs *before* the capability refusal on purpose: a caller must
    be able to tell a malformed request (INVALID_PARAMS / BAD_INPUT /
    WRONG_TYPE) apart from a well-formed request that Live's API cannot
    perform (CAPABILITY_UNAVAILABLE). Nothing here writes to the Set.
    """

    regular_count = len(list(_safe(lambda: song.tracks, [])))
    if command == "move_track":
        return _validate_move_track(song, params, regular_count)
    if command == "reorder_tracks":
        return _validate_reorder_tracks(params, regular_count)
    if command == "move_track_to_group":
        return _validate_move_track_to_group(song, params)
    if command == "ungroup_track":
        return _validate_ungroup_track(song, params)
    if command == "merge_groups":
        return _validate_merge_groups(song, params)
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
