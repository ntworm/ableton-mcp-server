"""Read tools: session, tracks, clips, devices, browser and search."""

from __future__ import annotations

from typing import Any

from . import models
from . import server as _s
from .diff import diff_snapshots
from .server import (
    PUBLIC_TOOL_NAMES,
    mcp,
)


@mcp.tool()
def get_session_info() -> Any:
    """Read top-level transport and time-signature state.

    Side effects: none.
    Example: ``get_session_info()`` returns tempo and playhead state.
    Edge cases: fails when the Remote Script is unavailable.
    """
    return _s._remote("get_session_info", models.GetSessionInfoRequest())


@mcp.tool()
def get_session_overview() -> dict[str, Any]:
    """Compose a compact Session snapshot from three existing read tools.

    Side effects: none; performs three read-only TCP bridge calls.
    Example: ``get_session_overview()`` returns session, tracks, and scenes.
    Edge cases: a bridge failure is returned by the corresponding component read.
    """
    models.GetSessionOverviewRequest()
    return {
        "session": _s._remote("get_session_info", models.GetSessionInfoRequest()),
        "tracks": _s._remote("get_track_list", models.GetTrackListRequest()),
        "scenes": _s._remote("get_scenes", models.GetScenesRequest()),
    }


@mcp.tool()
def get_bridge_status() -> dict[str, Any]:
    """Probe the Live bridge and explain environment-specific connection failures.

    Side effects: opens a loopback connection and performs one read-only session query.
    Example: ``get_bridge_status()`` distinguishes MCP discovery from Live availability.
    Edge cases: WSL NAT failures include a Windows-Python launcher hint.
    """
    models.GetBridgeStatusRequest()
    return _s.bridge_status(_s.get_client(), tool_count=len(PUBLIC_TOOL_NAMES))


@mcp.tool()
def get_track_list() -> Any:
    """List regular, return, and master tracks with session path-ids.

    Side effects: none.
    Example: ``get_track_list()`` returns ``[{"id": "track:0", ...}]``.
    Edge cases: path-ids must be refreshed after structural track changes.
    """
    return _s._remote("get_track_list", models.GetTrackListRequest())


@mcp.tool()
def get_track_state(track_index: int) -> Any:
    """Read mixer, device, and Session clip-slot state for one track.

    Side effects: none.
    Example: ``get_track_state(0)`` inspects the first track.
    Edge cases: an out-of-range index returns ``INVALID_PARAMS``.
    """
    return _s._remote("get_track_state", models.GetTrackStateRequest(track_index=track_index))


@mcp.tool()
def get_locators() -> Any:
    """List Arrangement cue points with names and beat times.

    Side effects: none.
    Example: ``get_locators()`` returns ``[{"name": "Verse", "time": 8.0}]``.
    Edge cases: Live beat-time objects are serialized as floats.
    """
    return _s._remote("get_locators", models.GetLocatorsRequest())


@mcp.tool()
def take_snapshot() -> Any:
    """Capture a normalized full-state debugging snapshot.

    Side effects: none.
    Example: ``take_snapshot()`` returns schema version, tracks, and context.
    Edge cases: large Sets produce correspondingly large JSON results.
    """
    return _s._remote("take_snapshot", models.TakeSnapshotRequest())


@mcp.tool()
def get_ableton_logs(lines: int = 100) -> str:
    """Read the tail of the newest Ableton ``Log.txt`` on Windows.

    Side effects: reads a local log file; it does not contact Live.
    Example: ``get_ableton_logs(50)`` returns the last fifty lines.
    Edge cases: returns a diagnostic string when no log can be located.
    """
    request = models.GetAbletonLogsRequest(lines=lines)
    path = _s.find_ableton_log_path()
    if path is None:
        return "Error: Ableton Log.txt path could not be resolved."
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return "".join(handle.readlines()[-request.lines :])
    except OSError as error:
        return f"Error reading Ableton Log.txt: {error}"


@mcp.tool()
def get_control_surfaces() -> Any:
    """List MIDI Remote Scripts currently exposed by Live.

    Side effects: none.
    Example: ``get_control_surfaces()`` confirms this script loaded.
    Edge cases: unavailable surfaces may be omitted by Live.
    """
    return _s._remote("get_control_surfaces", models.GetControlSurfacesRequest())


@mcp.tool()
def get_scenes() -> Any:
    """List Session View scenes and whether each scene is empty.

    Side effects: none.
    Example: ``get_scenes()`` returns scene indexes and names.
    Edge cases: a scene is non-empty when any contained slot has a clip.
    """
    return _s._remote("get_scenes", models.GetScenesRequest())


@mcp.tool()
def get_scene_state(scene_index: int) -> Any:
    """Read one scene and its per-track clip-slot summary.

    Side effects: none.
    Example: ``get_scene_state(0)`` inspects the first scene.
    Edge cases: an invalid scene index returns ``INVALID_PARAMS``.
    """
    return _s._remote("get_scene_state", models.GetSceneStateRequest(scene_index=scene_index))


@mcp.tool()
def get_project_metadata() -> Any:
    """Read Set name, file path, dirty flag, and whether Live can undo anything.

    Side effects: none.
    Example: ``get_project_metadata()`` identifies the loaded Set.
    Edge cases: ``null`` means Live did not answer; Live 12.4.25b1 has no ``Song.is_dirty``.
    """
    return _s._remote("get_project_metadata", models.GetProjectMetadataRequest())


@mcp.tool()
def get_loop_settings() -> Any:
    """Read Arrangement loop enablement, start, and length.

    Side effects: none.
    Example: ``get_loop_settings()`` returns loop geometry in beats.
    Edge cases: values can change with user interaction during a session.
    """
    return _s._remote("get_loop_settings", models.GetLoopSettingsRequest())


@mcp.tool()
def get_selected_context() -> Any:
    """Read the currently selected track, scene, and device.

    Side effects: none.
    Example: ``get_selected_context()`` returns selected path-ids.
    Edge cases: absent selections use ``null`` or index ``-1``.
    """
    return _s._remote("get_selected_context", models.GetSelectedContextRequest())


@mcp.tool()
def get_clip_summary(track_index: int) -> Any:
    """List Session clip slots and clip metadata for one track.

    Side effects: none.
    Example: ``get_clip_summary(0)`` lists the first track's slots.
    Edge cases: return and master tracks produce ``WRONG_TYPE``.
    """
    return _s._remote("get_clip_summary", models.GetClipSummaryRequest(track_index=track_index))


@mcp.tool()
def get_clip_notes(track_index: int, clip_index: int) -> Any:
    """Read MIDI notes from one Session clip.

    Side effects: none.
    Example: ``get_clip_notes(0, 1)`` reads slot one on track zero.
    Edge cases: audio clips return ``WRONG_TYPE`` and empty slots return an empty list.
    """
    return _s._remote(
        "get_clip_notes",
        models.GetClipNotesRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def get_clip_info(track_index: int, clip_index: int) -> Any:
    """Read stable metadata for one Session clip slot.

    Side effects: none.
    Example: ``get_clip_info(0, 1)`` returns loop, type, color, and signature fields.
    Edge cases: empty slots return ``has_clip=false`` instead of an error.
    """
    return _s._remote(
        "get_clip_info",
        models.GetClipInfoRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def get_device_list(track_index: int) -> Any:
    """List devices and parameter snapshots on one track.

    Side effects: none.
    Example: ``get_device_list(0)`` returns device path-ids.
    Edge cases: special tracks may expose an empty device list.
    """
    return _s._remote("get_device_list", models.GetDeviceListRequest(track_index=track_index))


@mcp.tool()
def get_parameter_value(
    track_index: int,
    device_index: int,
    parameter_name: str,
    chain_index: int | None = None,
    chain_device_index: int | None = None,
) -> Any:
    """Read a named device parameter and its bounds.

    Side effects: none.
    Example: ``get_parameter_value(0, 0, "Device On")`` reads a top-level
    parameter; ``get_parameter_value(4, 1, "Out Low", chain_index=0,
    chain_device_index=0)`` reads one nested inside a rack chain.
    Edge cases: names are exact and missing parameters return ``INVALID_PARAMS``.
    ``chain_index`` without ``chain_device_index`` addresses the chain's mixer,
    which exposes only ``volume`` and ``panning``.
    """
    return _s._remote(
        "get_parameter_value",
        models.GetParameterValueRequest(
            track_index=track_index,
            device_index=device_index,
            parameter_name=parameter_name,
            chain_index=chain_index,
            chain_device_index=chain_device_index,
        ),
        exclude_none=True,
    )


@mcp.tool()
def set_parameter_value(
    track_index: int,
    device_index: int,
    parameter_name: str,
    value: float,
    chain_index: int | None = None,
    chain_device_index: int | None = None,
) -> Any:
    """Write a named device parameter and verify the observed Live value.

    Side effects: mutates one device parameter in one Live undo step.
    Example: ``set_parameter_value(0, 0, "Filter Freq", 0.75)`` updates a device;
    ``set_parameter_value(4, 1, "Out Low", 20, chain_index=0, chain_device_index=0)``
    reaches a Velocity device nested inside a rack chain.
    Edge cases: ``chain_index`` alone addresses the chain's own mixer, where only
    ``volume`` and ``panning`` exist. Disabled, unknown, and out-of-range
    parameters return structured errors.
    """
    return _s._remote(
        "set_parameter_value",
        models.SetParameterValueRequest(
            track_index=track_index,
            device_index=device_index,
            chain_index=chain_index,
            chain_device_index=chain_device_index,
            parameter_name=parameter_name,
            value=value,
        ),
        exclude_none=True,
    )


@mcp.tool()
def get_plugin_presets(track_index: int, device_index: int) -> Any:
    """List a VST/VST3/AU plugin's presets and report its Configure state.

    Side effects: none.
    Example: ``get_plugin_presets(2, 2)`` returns the preset names plus
    ``selected_preset_index`` for the plugin on track two.
    Edge cases: native Live devices return ``WRONG_TYPE``; a plugin whose
    parameters were never added through Live's Configure button reports
    ``plugin_state.hint = "PLUGIN_NOT_CONFIGURED"``.
    """
    return _s._remote(
        "get_plugin_presets",
        models.GetPluginPresetsRequest(track_index=track_index, device_index=device_index),
    )


@mcp.tool()
def set_plugin_preset(
    track_index: int,
    device_index: int,
    preset_index: int | None = None,
    preset_name: str | None = None,
) -> Any:
    """Select one plugin preset by index or exact name and verify the readback.

    Side effects: switches the plugin preset in one Live undo step.
    Example: ``set_plugin_preset(2, 2, preset_name="Rock Kit")`` selects a
    preset without the Configure step ``set_parameter_value`` needs.
    Edge cases: pass exactly one selector; unknown names, out-of-range indexes,
    and plugins that expose no presets return structured errors.
    """
    return _s._remote(
        "set_plugin_preset",
        models.SetPluginPresetRequest(
            track_index=track_index,
            device_index=device_index,
            preset_index=preset_index,
            preset_name=preset_name,
        ),
        exclude_none=True,
    )


@mcp.tool()
def get_routing(track_index: int) -> Any:
    """Read input and output routing labels for one track.

    Side effects: none.
    Example: ``get_routing(0)`` reports the first track's routes.
    Edge cases: unavailable routes are returned as empty strings.
    """
    return _s._remote("get_routing", models.GetRoutingRequest(track_index=track_index))


@mcp.tool()
def get_browser_categories() -> Any:
    """List top-level Live Browser categories available in this version.

    Side effects: none.
    Example: ``get_browser_categories()`` returns category display names.
    Edge cases: version-specific missing categories are omitted.
    """
    return _s._remote("get_browser_categories", models.GetBrowserCategoriesRequest())


@mcp.tool()
def search_browser(
    query: str,
    category_type: str | None = None,
    limit: int = 50,
) -> Any:
    """Search the Live Browser with bounded TCP-side traversal.

    Side effects: none.
    Example: ``search_browser("Operator", "instruments", 25)`` finds native devices.
    Edge cases: traversal is capped by depth, children, visited nodes, and result limit.
    """
    return _s._remote(
        "search_browser",
        models.SearchBrowserRequest(
            query=query,
            category_type=category_type,
            limit=limit,
        ),
    )


@mcp.tool()
def diff_snapshots_tool(
    snap_a: dict[str, Any], snap_b: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Compare two snapshots recursively on the MCP-server side.

    Side effects: none; no socket call is made.
    Example: ``diff_snapshots_tool(old, new)`` reports changed paths.
    Edge cases: list entries are compared by position, not object identity.
    """
    request = models.DiffSnapshotsRequest(snap_a=snap_a, snap_b=snap_b)
    return diff_snapshots(request.snap_a, request.snap_b)


@mcp.tool()
def get_song_length() -> Any:
    """Read the derived Arrangement song length in beats.

    Side effects: none.
    Example: ``get_song_length()`` returns ``{"song_length": 64.25}``.
    Edge cases: the LOM property is read-only; no setter tool exists.
    """
    return _s._remote("get_song_length", models.GetSongLengthRequest())


@mcp.tool()
def live_find_track(query: str) -> Any:
    """Find tracks by case-insensitive name substring and return fresh path-ids.

    Side effects: none.
    Example: ``live_find_track("bass")`` resolves matching tracks.
    Edge cases: no match is a valid empty result.
    """
    return _s._remote("live_find_track", models.LiveFindTrackRequest(query=query))


@mcp.tool()
def live_find_device(track_index: int, query: str) -> Any:
    """Find devices in a track by case-insensitive name substring and return fresh path-ids.

    Side effects: none.
    Example: ``live_find_device(0, "operator")`` resolves matching devices on track 0.
    Edge cases: no match is a valid empty result.
    """
    return _s._remote(
        "live_find_device", models.LiveFindDeviceRequest(track_index=track_index, query=query)
    )


@mcp.tool()
def live_find_clip(track_index: int, query: str) -> Any:
    """Find clip slots in a track by case-insensitive name substring and return fresh path-ids.

    Side effects: none.
    Example: ``live_find_clip(0, "verse")`` resolves matching clips on track 0.
    Edge cases: no match is a valid empty result.
    """
    return _s._remote(
        "live_find_clip", models.LiveFindClipRequest(track_index=track_index, query=query)
    )


@mcp.tool()
def list_device_params(track_id: str) -> Any:
    """Resolve a track path-id and list all device parameters.

    Side effects: none.
    Example: ``list_device_params("track:0")`` returns parameter path-ids.
    Edge cases: missing targets return ``STALE_REFERENCE`` with a recovery hint.
    """
    return _s._remote("list_device_params", models.ListDeviceParamsRequest(track_id=track_id))
