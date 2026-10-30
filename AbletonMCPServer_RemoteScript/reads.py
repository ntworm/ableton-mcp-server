"""Read-only handlers for the session, tracks, scenes, clips, browser and snapshots."""

from __future__ import annotations

import time
from typing import Any

from ._contracts import (
    BRIDGE_OWNER,
    BRIDGE_PRECONDITION_CAPABILITY,
    BRIDGE_PROTOCOL_VERSION,
    BRIDGE_SCHEMA_VERSION,
    ERROR_INVALID_PARAMS,
    ERROR_WRONG_TYPE,
)
from .common import RemoteError, _integer_param, _safe, _string_param
from .lom import (
    _all_tracks,
    _capture_clip_slot,
    _capture_device,
    _capture_routing,
    _capture_track,
    _clip_slot,
    _note_value,
    _track_at,
    _track_hierarchy,
    _track_type,
)


def cmd_get_session_info(song: Any, _application: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return {
        "tempo": float(song.tempo),
        "signature_numerator": int(song.signature_numerator),
        "signature_denominator": int(song.signature_denominator),
        "is_playing": bool(song.is_playing),
        "current_song_time": float(song.current_song_time),
        "bridge_contract": {
            "schema_version": BRIDGE_SCHEMA_VERSION,
            "owner": BRIDGE_OWNER,
            "protocol_version": BRIDGE_PROTOCOL_VERSION,
            "capabilities": {BRIDGE_PRECONDITION_CAPABILITY: "v1"},
        },
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
    # ``None`` means Live did not answer, never "saved" or "clean". On Live
    # 12.4.25b1 ``Song.is_dirty`` does not report unsaved changes
    # (docs/KNOWN_BUGS.md Category S), so the acceptance preflight checks
    # ``can_undo``: false while nothing undoable happened since the Set opened.
    file_path = _safe(lambda: song.file_path, None)
    is_dirty = _safe(lambda: song.is_dirty, None)
    can_undo = _safe(lambda: song.can_undo, None)
    return {
        "song_name": str(_safe(lambda: song.name, "")),
        "file_path": None if file_path is None else str(file_path),
        "is_dirty": None if is_dirty is None else bool(is_dirty),
        "can_undo": None if can_undo is None else bool(can_undo),
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


def _browser_search_limit(params: dict[str, Any]) -> int:
    """Return the clamped number of browser matches a search may return."""
    raw_limit = params.get("limit", 50)
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
        raise RemoteError(ERROR_INVALID_PARAMS, "Parameter 'limit' must be an integer.")
    return max(1, min(200, raw_limit))


def _browser_search_categories(params: dict[str, Any]) -> tuple[str, ...]:
    """Return the browser categories a search has to visit."""
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
    return (category_filter,) if category_filter is not None else category_names


def _browser_item_key(category: str, uri: str, ordinal_path: tuple[int, ...]) -> str:
    """Return the traversal key of one browser item."""
    if uri:
        return "uri:" + uri
    return "%s:%s" % (category, "/".join(str(part) for part in ordinal_path))


def _browser_match(
    item: Any, uri: str, name: str, category: str, path: list[str]
) -> dict[str, Any]:
    """Build the result entry of a browser item that matches the query."""
    return {
        "name": name,
        "uri": uri,
        "category": category,
        "path": path,
        "is_loadable": bool(_safe(lambda item=item: item.is_loadable, False)),
    }


def _browser_children(
    item: Any, path: list[str], depth: int, ordinal_path: tuple[int, ...]
) -> list[Any]:
    """Return the stack entries of the children of one browser item."""
    children = list(_safe(lambda item=item: item.children, []))[:500]
    entries = []
    for child_index in range(len(children) - 1, -1, -1):
        child = children[child_index]
        child_name = str(_safe(lambda child=child: child.name, ""))
        entries.append((child, [*path, child_name], depth + 1, (*ordinal_path, child_index)))
    return entries


def _browser_visit(
    entry: tuple[Any, list[str], int, tuple[int, ...]],
    category: str,
    query: str,
    results: list[dict[str, Any]],
    visited: set[str],
) -> list[Any] | None:
    """Visit one browser item, appending its match and returning its children."""
    item, path, depth, ordinal_path = entry
    uri = str(_safe(lambda item=item: item.uri, ""))
    key = _browser_item_key(category, uri, ordinal_path)
    if key in visited:
        return None
    visited.add(key)
    name = str(_safe(lambda item=item: item.name, ""))
    if depth > 0 and query in name.casefold():
        results.append(_browser_match(item, uri, name, category, path))
    if depth >= 5:
        return None
    return _browser_children(item, path, depth, ordinal_path)


def _traverse_browser_category(
    entry: tuple[Any, list[str], int, tuple[int, ...]],
    category: str,
    query: str,
    limit: int,
    budget: int,
    results: list[dict[str, Any]],
    visited: set[str],
) -> None:
    """Walk one browser category and append the matches it finds to ``results``."""
    # Slice 1 Task 5: Live's LOM yields fresh proxy wrappers on every
    # ``.children`` access, so tracking identity via ``id()`` collapses.
    # Use URI keys (stable across proxies) and ordinal-path keys (URI-less
    # trees) to bound traversal.
    stack = [entry]
    while stack and len(results) < limit and len(visited) < budget:
        children = _browser_visit(stack.pop(), category, query, results, visited)
        if children is not None:
            stack.extend(children)


def cmd_search_browser(
    _song: Any,
    application: Any,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    query = _string_param(params, "query").casefold()
    limit = _browser_search_limit(params)
    selected = _browser_search_categories(params)
    results: list[dict[str, Any]] = []
    visited: set[str] = set()
    budget = 5000
    for category in selected:
        root = _safe(lambda category=category: getattr(application.browser, category), None)
        if root is None:
            continue
        root_name = str(_safe(lambda root=root: root.name, category.replace("_", " ").title()))
        _traverse_browser_category(
            (root, [root_name], 0, ()), category, query, limit, budget, results, visited
        )
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
