from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Generator, Sequence
from pathlib import Path
from typing import Any, Literal

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FASTMCP_TELEMETRY_DISABLED", "true")
os.environ.setdefault("MCP_TELEMETRY_DISABLED", "true")

from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult
from mcp.types import TextContent

from contracts import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_WS_PORT

from . import models
from .analysis import (
    analyze_audio as _analyze_audio,
)
from .analysis import (
    analyze_mix as _analyze_mix,
)
from .analysis import (
    extract_single_cycle as _extract_single_cycle,
)
from .analysis import (
    find_frequency_masking as _find_frequency_masking,
)
from .catalog import TOOL_CATALOG
from .client import Client
from .diagnostics import bridge_status, find_ableton_log_path
from .diff import diff_snapshots
from .errors import BridgeError

PUBLIC_TOOL_NAMES = tuple(spec.name for spec in TOOL_CATALOG)


class CountableToolListing(Awaitable[Sequence[Tool]]):
    """Lazy async FastMCP listing that also supports synchronous ``len``."""

    def __init__(
        self,
        factory: Callable[[], Awaitable[Sequence[Tool]]],
        count: Callable[[], int],
    ) -> None:
        self._factory = factory
        self._count = count

    def __await__(self) -> Generator[Any, None, Sequence[Tool]]:
        return self._factory().__await__()

    def __len__(self) -> int:
        return self._count()


class CountableFastMCP(FastMCP):
    """FastMCP 3.x with a backwards-compatible countable tool listing."""

    def list_tools(  # type: ignore[override]
        self, *, run_middleware: bool = True
    ) -> CountableToolListing:
        return CountableToolListing(
            lambda: super(CountableFastMCP, self).list_tools(run_middleware=run_middleware),
            lambda: len(PUBLIC_TOOL_NAMES),
        )


mcp = CountableFastMCP("AbletonMCPServer")
_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        host = os.environ.get("ABLETON_MCP_SERVER_HOST", DEFAULT_HOST)
        port = int(os.environ.get("ABLETON_MCP_SERVER_PORT", str(DEFAULT_PORT)))
        ws_port = int(os.environ.get("ABLETON_MCP_SERVER_WS_PORT", str(DEFAULT_WS_PORT)))
        _client = Client(host=host, port=port, ws_port=ws_port, reconnect=True)
    return _client


def _explicit_json_result(
    value: Any, *, is_error: bool = False, unwrap_result: bool = False
) -> ToolResult:
    """Keep JSON values visible without leaking domain errors into FastMCP."""

    content = [
        TextContent(
            type="text",
            text=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )
    ]
    structured = {"result": value} if unwrap_result else value
    meta = {"fastmcp": {"wrap_result": True}} if unwrap_result else None
    return ToolResult(
        content=content,
        structured_content=structured,
        meta=meta,
        is_error=is_error,
    )


def _remote(
    command: str,
    request: models.RequestModel,
    *,
    exclude_none: bool = False,
) -> Any:
    try:
        result = get_client().call(
            command,
            request.model_dump(mode="json", exclude_none=exclude_none),
        )
    except BridgeError as error:
        return _explicit_json_result(error.to_envelope(), is_error=True)
    if isinstance(result, list) and not result:
        return _explicit_json_result(result, unwrap_result=True)
    return result


async def _remote_ws(method: str, params: dict[str, Any] | None = None) -> Any:
    """Route a command to the Extension Host WebSocket bridge."""
    return await get_client().call_ws(method, params)


@mcp.tool()
def get_session_info() -> Any:
    """Read top-level transport and time-signature state.

    Side effects: none.
    Example: ``get_session_info()`` returns tempo and playhead state.
    Edge cases: fails when the Remote Script is unavailable.
    """
    return _remote("get_session_info", models.GetSessionInfoRequest())


@mcp.tool()
def get_session_overview() -> dict[str, Any]:
    """Compose a compact Session snapshot from three existing read tools.

    Side effects: none; performs three read-only TCP bridge calls.
    Example: ``get_session_overview()`` returns session, tracks, and scenes.
    Edge cases: a bridge failure is returned by the corresponding component read.
    """
    models.GetSessionOverviewRequest()
    return {
        "session": _remote("get_session_info", models.GetSessionInfoRequest()),
        "tracks": _remote("get_track_list", models.GetTrackListRequest()),
        "scenes": _remote("get_scenes", models.GetScenesRequest()),
    }


@mcp.tool()
def get_bridge_status() -> dict[str, Any]:
    """Probe the Live bridge and explain environment-specific connection failures.

    Side effects: opens a loopback connection and performs one read-only session query.
    Example: ``get_bridge_status()`` distinguishes MCP discovery from Live availability.
    Edge cases: WSL NAT failures include a Windows-Python launcher hint.
    """
    models.GetBridgeStatusRequest()
    return bridge_status(get_client(), tool_count=len(PUBLIC_TOOL_NAMES))


@mcp.tool()
def get_track_list() -> Any:
    """List regular, return, and master tracks with session path-ids.

    Side effects: none.
    Example: ``get_track_list()`` returns ``[{"id": "track:0", ...}]``.
    Edge cases: path-ids must be refreshed after structural track changes.
    """
    return _remote("get_track_list", models.GetTrackListRequest())


@mcp.tool()
def get_track_state(track_index: int) -> Any:
    """Read mixer, device, and Session clip-slot state for one track.

    Side effects: none.
    Example: ``get_track_state(0)`` inspects the first track.
    Edge cases: an out-of-range index returns ``INVALID_PARAMS``.
    """
    return _remote("get_track_state", models.GetTrackStateRequest(track_index=track_index))


@mcp.tool()
def get_locators() -> Any:
    """List Arrangement cue points with names and beat times.

    Side effects: none.
    Example: ``get_locators()`` returns ``[{"name": "Verse", "time": 8.0}]``.
    Edge cases: Live beat-time objects are serialized as floats.
    """
    return _remote("get_locators", models.GetLocatorsRequest())


@mcp.tool()
def take_snapshot() -> Any:
    """Capture a normalized full-state debugging snapshot.

    Side effects: none.
    Example: ``take_snapshot()`` returns schema version, tracks, and context.
    Edge cases: large Sets produce correspondingly large JSON results.
    """
    return _remote("take_snapshot", models.TakeSnapshotRequest())


@mcp.tool()
def get_ableton_logs(lines: int = 100) -> str:
    """Read the tail of the newest Ableton ``Log.txt`` on Windows.

    Side effects: reads a local log file; it does not contact Live.
    Example: ``get_ableton_logs(50)`` returns the last fifty lines.
    Edge cases: returns a diagnostic string when no log can be located.
    """
    request = models.GetAbletonLogsRequest(lines=lines)
    path = find_ableton_log_path()
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
    return _remote("get_control_surfaces", models.GetControlSurfacesRequest())


@mcp.tool()
def get_scenes() -> Any:
    """List Session View scenes and whether each scene is empty.

    Side effects: none.
    Example: ``get_scenes()`` returns scene indexes and names.
    Edge cases: a scene is non-empty when any contained slot has a clip.
    """
    return _remote("get_scenes", models.GetScenesRequest())


@mcp.tool()
def get_scene_state(scene_index: int) -> Any:
    """Read one scene and its per-track clip-slot summary.

    Side effects: none.
    Example: ``get_scene_state(0)`` inspects the first scene.
    Edge cases: an invalid scene index returns ``INVALID_PARAMS``.
    """
    return _remote("get_scene_state", models.GetSceneStateRequest(scene_index=scene_index))


@mcp.tool()
def get_project_metadata() -> Any:
    """Read Set name, file path, and dirty state.

    Side effects: none.
    Example: ``get_project_metadata()`` identifies the loaded Set.
    Edge cases: unsaved Sets can have an empty file path.
    """
    return _remote("get_project_metadata", models.GetProjectMetadataRequest())


@mcp.tool()
def get_loop_settings() -> Any:
    """Read Arrangement loop enablement, start, and length.

    Side effects: none.
    Example: ``get_loop_settings()`` returns loop geometry in beats.
    Edge cases: values can change with user interaction during a session.
    """
    return _remote("get_loop_settings", models.GetLoopSettingsRequest())


@mcp.tool()
def get_selected_context() -> Any:
    """Read the currently selected track, scene, and device.

    Side effects: none.
    Example: ``get_selected_context()`` returns selected path-ids.
    Edge cases: absent selections use ``null`` or index ``-1``.
    """
    return _remote("get_selected_context", models.GetSelectedContextRequest())


@mcp.tool()
def get_clip_summary(track_index: int) -> Any:
    """List Session clip slots and clip metadata for one track.

    Side effects: none.
    Example: ``get_clip_summary(0)`` lists the first track's slots.
    Edge cases: return and master tracks produce ``WRONG_TYPE``.
    """
    return _remote("get_clip_summary", models.GetClipSummaryRequest(track_index=track_index))


@mcp.tool()
def get_clip_notes(track_index: int, clip_index: int) -> Any:
    """Read MIDI notes from one Session clip.

    Side effects: none.
    Example: ``get_clip_notes(0, 1)`` reads slot one on track zero.
    Edge cases: audio clips return ``WRONG_TYPE`` and empty slots return an empty list.
    """
    return _remote(
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
    return _remote(
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
    return _remote("get_device_list", models.GetDeviceListRequest(track_index=track_index))


@mcp.tool()
def get_parameter_value(track_index: int, device_index: int, parameter_name: str) -> Any:
    """Read a named device parameter and its bounds.

    Side effects: none.
    Example: ``get_parameter_value(0, 0, "Device On")`` reads a parameter.
    Edge cases: names are exact and missing parameters return ``INVALID_PARAMS``.
    """
    return _remote(
        "get_parameter_value",
        models.GetParameterValueRequest(
            track_index=track_index,
            device_index=device_index,
            parameter_name=parameter_name,
        ),
    )


@mcp.tool()
def set_parameter_value(
    track_index: int,
    device_index: int,
    parameter_name: str,
    value: float,
) -> Any:
    """Write a named device parameter and verify the observed Live value.

    Side effects: mutates one device parameter in one Live undo step.
    Example: ``set_parameter_value(0, 0, "Filter Freq", 0.75)`` updates a device.
    Edge cases: disabled, unknown, and out-of-range parameters return structured errors.
    """
    return _remote(
        "set_parameter_value",
        models.SetParameterValueRequest(
            track_index=track_index,
            device_index=device_index,
            parameter_name=parameter_name,
            value=value,
        ),
    )


@mcp.tool()
def get_routing(track_index: int) -> Any:
    """Read input and output routing labels for one track.

    Side effects: none.
    Example: ``get_routing(0)`` reports the first track's routes.
    Edge cases: unavailable routes are returned as empty strings.
    """
    return _remote("get_routing", models.GetRoutingRequest(track_index=track_index))


@mcp.tool()
def get_browser_categories() -> Any:
    """List top-level Live Browser categories available in this version.

    Side effects: none.
    Example: ``get_browser_categories()`` returns category display names.
    Edge cases: version-specific missing categories are omitted.
    """
    return _remote("get_browser_categories", models.GetBrowserCategoriesRequest())


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
    return _remote(
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
    return _remote("get_song_length", models.GetSongLengthRequest())


@mcp.tool()
def live_find_track(query: str) -> Any:
    """Find tracks by case-insensitive name substring and return fresh path-ids.

    Side effects: none.
    Example: ``live_find_track("bass")`` resolves matching tracks.
    Edge cases: no match is a valid empty result.
    """
    return _remote("live_find_track", models.LiveFindTrackRequest(query=query))


@mcp.tool()
def list_device_params(track_id: str) -> Any:
    """Resolve a track path-id and list all device parameters.

    Side effects: none.
    Example: ``list_device_params("track:0")`` returns parameter path-ids.
    Edge cases: missing targets return ``STALE_REFERENCE`` with a recovery hint.
    """
    return _remote("list_device_params", models.ListDeviceParamsRequest(track_id=track_id))


@mcp.tool()
def create_cue_point(name: str, time: float) -> Any:
    """Create or idempotently rename a cue point at a beat time.

    Side effects: mutates the Set in one undo step and temporarily moves the playhead.
    Example: ``create_cue_point("Verse", 8.0)`` creates a locator.
    Edge cases: verified movement failure raises ``PLAYHEAD_NOT_MOVED`` before toggling.
    Arrangement-grid snap is reversed and raises ``CUE_SNAPPED_TO_GRID``.
    """
    return _remote("create_cue_point", models.CreateCuePointRequest(name=name, time=time))


@mcp.tool()
def bulk_create_cue_points(items: list[dict[str, Any]]) -> Any:
    """Create or rename multiple cue points as one command.

    Side effects: mutates all successful items inside one undo step.
    Example: ``bulk_create_cue_points([{"name": "A", "time": 0}])``.
    Edge cases: per-item errors are aggregated instead of aborting later items;
    off-grid snaps are reversed and reported as ``CUE_SNAPPED_TO_GRID``.
    """
    request = models.BulkCuePointsRequest.model_validate({"items": items})
    return _remote("bulk_create_cue_points", request)


@mcp.tool()
def delete_cue_point(time: float) -> Any:
    """Delete a cue point by verified move-and-toggle.

    Side effects: mutates the Set in one undo step and temporarily moves the playhead.
    Example: ``delete_cue_point(8.0)`` deletes a cue near beat eight.
    Edge cases: no cue at the time returns ``deleted: false``; an Arrangement-grid
    snap is reversed and raises ``CUE_SNAPPED_TO_GRID``.
    """
    return _remote("delete_cue_point", models.DeleteCuePointRequest(time=time))


@mcp.tool()
def set_current_song_time(time: float) -> Any:
    """Move the Arrangement playhead with set/read/retry verification.

    Side effects: writes transport state in one undo step.
    Example: ``set_current_song_time(32.0)`` moves to beat thirty-two.
    Edge cases: a stuck setter raises ``PLAYHEAD_NOT_MOVED`` after three attempts.
    """
    return _remote("set_current_song_time", models.SetCurrentSongTimeRequest(time=time))


@mcp.tool()
def set_tempo(tempo: float) -> Any:
    """Set the Live Set tempo in BPM.

    Side effects: writes tempo in one undo step.
    Example: ``set_tempo(128.0)`` sets 128 BPM.
    Edge cases: values outside 20..999 or non-finite values are rejected.
    """
    return _remote("set_tempo", models.SetTempoRequest(tempo=tempo))


@mcp.tool()
def start_playback() -> Any:
    """Start Live's transport.

    Side effects: starts playback in one undo-scoped command.
    Example: ``start_playback()`` returns the observed playing state.
    Edge cases: Live can reject the call while shutting down.
    """
    return _remote("start_playback", models.StartPlaybackRequest())


@mcp.tool()
def stop_playback() -> Any:
    """Stop Live's transport.

    Side effects: stops playback in one undo-scoped command.
    Example: ``stop_playback()`` returns the observed playing state.
    Edge cases: Live can reject the call while shutting down.
    """
    return _remote("stop_playback", models.StopPlaybackRequest())


@mcp.tool()
def set_loop(enabled: bool) -> Any:
    """Enable or disable the Arrangement loop.

    Side effects: writes loop state in one undo step.
    Example: ``set_loop(True)`` enables looping.
    Edge cases: only a boolean value is accepted.
    """
    return _remote("set_loop", models.SetLoopRequest(enabled=enabled))


@mcp.tool()
def set_loop_start(start_beat: float) -> Any:
    """Set Arrangement loop start with read-back verification.

    Side effects: writes loop geometry in one undo step.
    Example: ``set_loop_start(16.0)`` starts the loop at beat sixteen.
    Edge cases: a stuck setter raises ``PLAYHEAD_NOT_MOVED``.
    """
    return _remote("set_loop_start", models.SetLoopStartRequest(start_beat=start_beat))


@mcp.tool()
def set_loop_length(length_beats: float) -> Any:
    """Set Arrangement loop length with read-back verification.

    Side effects: writes loop geometry in one undo step.
    Example: ``set_loop_length(8.0)`` makes an eight-beat loop.
    Edge cases: length must be positive and a stuck setter raises an error.
    """
    return _remote(
        "set_loop_length",
        models.SetLoopLengthRequest(length_beats=length_beats),
    )


@mcp.tool()
def run_batch(commands: list[dict[str, Any]]) -> Any:
    """Run allowed mutations sequentially inside one Live undo step.

    Side effects: successful prefix mutations persist until one Ctrl+Z; no rollback occurs.
    Example: ``run_batch([{"type": "set_tempo", "params": {"tempo": 128}}])``.
    Edge cases: execution aborts at the first error and nested batches are rejected.
    """
    request = models.RunBatchRequest.model_validate({"commands": commands})
    return _remote("run_batch", request)


@mcp.tool()
def add_notes_to_clip(track_index: int, clip_index: int, notes: list[dict[str, Any]]) -> Any:
    """Add validated MIDI notes to an existing Session clip.

    Side effects: adds notes in one undo step; existing notes remain.
    Example: ``add_notes_to_clip(0, 0, [{"pitch": 60, ...}])``.
    Edge cases: audio clips, empty slots, and invalid MIDI ranges are rejected.
    """
    request = models.AddNotesToClipRequest.model_validate(
        {"track_index": track_index, "clip_index": clip_index, "notes": notes}
    )
    return _remote("add_notes_to_clip", request, exclude_none=True)


@mcp.tool()
def fire_clip(track_index: int, clip_index: int) -> Any:
    """Fire an existing Session clip through its clip slot.

    Side effects: launches playback in one undo-scoped command.
    Example: ``fire_clip(0, 1)`` launches slot one on track zero.
    Edge cases: empty or invalid slots are rejected.
    """
    return _remote(
        "fire_clip",
        models.FireClipRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def create_clip(track_index: int, clip_index: int, length_beats: float) -> Any:
    """Create an empty MIDI clip in an empty Session slot.

    Side effects: creates a clip in one undo step.
    Example: ``create_clip(0, 1, 4.0)`` creates a four-beat clip.
    Edge cases: only empty slots on MIDI tracks accept this operation.
    """
    return _remote(
        "create_clip",
        models.CreateClipRequest(
            track_index=track_index,
            clip_index=clip_index,
            length_beats=length_beats,
        ),
    )


@mcp.tool()
def delete_clip(track_index: int, clip_index: int) -> Any:
    """Delete one occupied Session clip slot.

    Side effects: deletes a clip in one Live undo step.
    Example: ``delete_clip(0, 1)`` removes the clip in slot one.
    Edge cases: empty slots return ``BAD_INPUT``.
    """
    return _remote(
        "delete_clip",
        models.DeleteClipRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def clear_clip_notes(track_index: int, clip_index: int) -> Any:
    """Remove every MIDI note from one Session clip and report the observed delta.

    Side effects: clears notes in one Live undo step.
    Example: ``clear_clip_notes(0, 1)`` empties a MIDI clip without deleting it.
    Edge cases: empty or audio clips return structured errors.
    """
    return _remote(
        "clear_clip_notes",
        models.ClearClipNotesRequest(track_index=track_index, clip_index=clip_index),
    )


@mcp.tool()
def fire_scene(scene_index: int) -> Any:
    """Fire one Session scene using Live's current launch quantization.

    Side effects: triggers all playable clips in the selected scene.
    Example: ``fire_scene(0)`` launches the first scene.
    Edge cases: an out-of-range index returns ``INVALID_PARAMS``.
    """
    return _remote("fire_scene", models.FireSceneRequest(scene_index=scene_index))


@mcp.tool()
def set_track_property(
    track_index: int,
    property: Literal["mute", "solo", "arm"],
    value: bool,
) -> Any:
    """Set and verify one boolean track property.

    Side effects: changes mute, solo, or arm in one Live undo step.
    Example: ``set_track_property(0, "mute", True)`` mutes the first track.
    Edge cases: arm is rejected for return and master tracks.
    """
    return _remote(
        "set_track_property",
        models.SetTrackPropertyRequest(track_index=track_index, property=property, value=value),
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
    return _remote(
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
) -> Any:
    """Replace one Session clip parameter envelope with verified breakpoints.

    Side effects: clears and rewrites one clip envelope in one Live undo step.
    Example: ``create_clip_automation(0, 1, "volume", [{"time": 0, "value": 0.5}])``.
    Edge cases: requires Session-clip automation APIs and accepts at most 500 points.
    """
    request = models.CreateClipAutomationRequest.model_validate(
        {
            "track_index": track_index,
            "clip_index": clip_index,
            "parameter_name": parameter_name,
            "automation_points": automation_points,
        }
    )
    return _remote("create_clip_automation", request)


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
    return _remote("get_composition_structure", models.GetCompositionStructureRequest())


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
    return _remote(
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
    return _remote(
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
    return _remote(
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
    return _remote(
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
    result = await _remote_ws(
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
    result = await _remote_ws(
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
    """Load a device onto a track using the Extensions SDK browser API.

    Side effects: mutates the track device chain via the Extension Host.
    Example: ``load_device_to_track(0, device_name="Operator")`` loads Operator
    on track 0. ``device_uri`` is retained as a deprecated alias for callers
    that still pass a query URI.
    Edge cases: requires the AbletonMCPServer Extension to be installed.
    """
    request = models.LoadDeviceToTrackRequest(
        track_index=track_index,
        device_name=device_name,
        device_uri=device_uri,
    )
    result = await _remote_ws(
        "load_device_to_track",
        {"track_index": request.track_index, "device_name": request.resolved_name},
    )
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
    return _remote("lifecycle_status", models.GetLifecycleStatusRequest())


@mcp.tool()
def save_set(require_api: bool = False) -> Any:
    """Save the Live Set via Song.save() when exposed, otherwise return a GUI workflow.

    Side effects: invokes Song.save() in one undo step when available.
    Example: ``save_set(require_api=True)`` raises when the API is missing.
    Edge cases: missing API returns a structured GUI workflow response.
    """
    return _remote("save_set", models.SaveSetRequest(require_api=require_api))


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
    return _remote(
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
    return _remote(
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


# ---------------------------------------------------------------------------
# v0.3.0 — Extension Scaffolding & Building
# ---------------------------------------------------------------------------
_EXTENSION_TEMPLATE_TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022",
        "module": "NodeNext",
        "moduleResolution": "NodeNext",
        "esModuleInterop": True,
        "strict": True,
        "outDir": "./dist",
        "declaration": True,
        "sourceMap": True,
    },
    "include": ["src"],
}

_EXTENSION_ENTRYPOINT_REL = "dist/extension.js"
_EXTENSION_BUILD_STEP_NAME = "build"
_EXTENSION_INSTALL_STEP_NAME = "install"


def _extension_vendor_dir() -> Path | None:
    """Locate the bundled ``vendor/`` directory shipped with the package.

    Checks the package-local ``_extension_vendor`` directory first (for
    wheel installations) and falls back to the checkout's
    ``AbletonMCPServer_Extension/vendor`` directory.
    """
    pkg_dir = Path(__file__).resolve().parent
    local_vendor = pkg_dir / "_extension_vendor"
    if local_vendor.is_dir():
        return local_vendor
    repo_root = pkg_dir.parent
    candidate = repo_root / "AbletonMCPServer_Extension" / "vendor"
    return candidate if candidate.is_dir() else None


def _read_extension_vendor_tarballs() -> dict[str, Path]:
    """Return a mapping of dependency name → absolute tarball path.

    Returns an empty mapping when the ``vendor/`` directory is not available.
    """
    vendor = _extension_vendor_dir()
    if vendor is None:
        return {}
    found: dict[str, Path] = {}
    sdk = next(vendor.glob("ableton-extensions-sdk-*.tgz"), None)
    cli = next(vendor.glob("ableton-extensions-cli-*.tgz"), None)
    if sdk is not None:
        found["@ableton-extensions/sdk"] = sdk
    if cli is not None:
        found["@ableton-extensions/cli"] = cli
    return found


def _build_extension_package_json(
    *,
    name: str,
    tarballs: dict[str, Path],
) -> dict[str, Any]:
    """Compose the ``package.json`` body for the scaffolded project.

    The dependency graph mirrors the repository's own Extension: the SDK
    tarball is a runtime dependency, the CLI tarball is a devDependency
    used to package the final ``.ablx``. The ``main`` field points to
    ``dist/extension.js`` so Node treats that file as the package
    entry; ``build_extension`` reads the same field to validate the
    build artefact.
    """
    pkg: dict[str, Any] = {
        "name": name.lower().replace(" ", "-"),
        "version": "0.5.2",
        "private": True,
        "type": "module",
        "main": _EXTENSION_ENTRYPOINT_REL,
        "scripts": {
            "build": "tsc --noEmit && tsx build.ts",
            "build:prod": "tsc --noEmit && tsx build.ts --production",
            "package": "npm run build:prod && extensions-cli package",
        },
        "engines": {"node": ">=18.0.0"},
        "dependencies": {},
        "devDependencies": {},
    }
    for dep_name, tarball in tarballs.items():
        target = pkg["dependencies"] if dep_name.endswith("/sdk") else pkg["devDependencies"]
        target[dep_name] = f"file:./vendor/{tarball.name}"
    if not any(dep.startswith("@ableton-extensions/") for dep in pkg["dependencies"]):
        # Mirror the real extension's runtime ws dependency so the
        # scaffolded project type-checks even when the SDK tarball is
        # missing from the install environment.
        pkg["dependencies"]["ws"] = "^8.18.0"
    pkg["devDependencies"].update(
        {
            "@types/node": "^24.1.0",
            "@types/ws": "^8.5.13",
            "esbuild": "0.28.1",
            "tsx": "^4.19.0",
            "typescript": "^5.9.3",
        }
    )
    return pkg


def _build_extension_manifest(*, name: str, author: str) -> dict[str, Any]:
    """Compose the Extension ``manifest.json`` payload."""
    return {
        "name": name,
        "author": author,
        "entry": _EXTENSION_ENTRYPOINT_REL,
        "version": "0.5.2",
        "minimumApiVersion": "1.0.0",
    }


_EXTENSION_TEMPLATE_EXTENSION_TS = """\
import {{ initialize, type ActivationContext }} from '@ableton-extensions/sdk';

/**
 * {name} — Ableton Live Extension scaffold
 *
 * Auto-scaffolded by ableton-mcp-server. The SDK contract is the only
 * requirement for a real Extension; this scaffold keeps the surface
 * minimal so future agents can iterate on real handlers.
 */

let activated = false;

function activate(activation: ActivationContext): void {{
  if (activated) {{
    console.log('[{name}] activate() called while already active');
    return;
  }}
  activated = true;
  const context = initialize(activation, '1.0.0');
  // Hand the SDK context to the real handlers (see ./index.js).
  console.log('[{name}] extension activated');
  void context;
}}

function deactivate(): void {{
  if (!activated) return;
  activated = false;
  console.log('[{name}] extension deactivated');
}}

export {{ activate, deactivate }};
"""


_EXTENSION_TEMPLATE_BUILD_TS = """\
import * as esbuild from 'esbuild';
import * as fs from 'node:fs';

const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const production = process.argv.includes('--production');

await esbuild.build({
  entryPoints: ['src/extension.ts'],
  outfile: manifest.entry,
  bundle: true,
  format: 'cjs',
  platform: 'node',
  sourcesContent: false,
  logLevel: production ? 'silent' : 'info',
  sourcemap: !production,
});
"""


@mcp.tool()
def scaffold_extension(name: str, author: str = "ntworm", output_directory: str = ".") -> str:
    """Create a template Ableton Extension project folder.

    The scaffold produces an extension that follows the same shape as
    the repository's own ``AbletonMCPServer_Extension``: it imports
    ``@ableton-extensions/sdk``, declares ``dist/extension.js`` as the
    package entry in both ``package.json["main"]`` and
    ``manifest.json["entry"]``, and bundles via ``tsx build.ts``. Vendor
    tarballs shipped with the package are copied locally into the new
    project so local SDK/CLI packages are used during build. In the
    acceptance report, ``offline_passed`` indicates a probe that runs
    without requiring a connection to Ableton Live.

    Side effects: creates files on disk. No Ableton connection required.
    Example: ``scaffold_extension("MyEffect", output_directory="/tmp/ext")``
    Edge cases: returns a ``status="error"`` JSON when vendor tarballs are
    missing or output directory is not writable; never raises during disk writes.
    """
    tarballs = _read_extension_vendor_tarballs()
    if (
        len(tarballs) < 2
        or "@ableton-extensions/sdk" not in tarballs
        or "@ableton-extensions/cli" not in tarballs
    ):
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "vendor tarballs for @ableton-extensions/sdk and "
                    "@ableton-extensions/cli are missing"
                ),
            },
            indent=2,
        )

    request = models.ScaffoldExtensionRequest(
        name=name, author=author, output_directory=output_directory
    )
    project_dir = Path(request.output_directory) / request.name
    try:
        project_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return json.dumps(
            {
                "status": "error",
                "message": f"project directory already exists: {project_dir}",
            },
            indent=2,
        )
    except OSError as error:
        return json.dumps(
            {
                "status": "error",
                "message": f"cannot create project directory: {error}",
            },
            indent=2,
        )
    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)

    vendor_target = project_dir / "vendor"
    vendor_target.mkdir(exist_ok=True)
    copied_vendor_files: list[str] = []
    for tarball in tarballs.values():
        (vendor_target / tarball.name).write_bytes(tarball.read_bytes())
        copied_vendor_files.append(f"vendor/{tarball.name}")

    pkg = _build_extension_package_json(
        name=request.name,
        tarballs=tarballs,
    )
    (project_dir / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    (project_dir / "tsconfig.json").write_text(
        json.dumps(_EXTENSION_TEMPLATE_TSCONFIG, indent=2), encoding="utf-8"
    )
    (project_dir / "manifest.json").write_text(
        json.dumps(
            _build_extension_manifest(name=request.name, author=request.author),
            indent=2,
        ),
        encoding="utf-8",
    )
    (project_dir / "build.ts").write_text(_EXTENSION_TEMPLATE_BUILD_TS, encoding="utf-8")
    (src_dir / "extension.ts").write_text(
        _EXTENSION_TEMPLATE_EXTENSION_TS.format(name=request.name),
        encoding="utf-8",
    )

    files = [
        "package.json",
        "tsconfig.json",
        "manifest.json",
        "build.ts",
        "src/extension.ts",
        *copied_vendor_files,
    ]

    return json.dumps(
        {
            "status": "scaffolded",
            "project_path": str(project_dir),
            "entrypoint": _EXTENSION_ENTRYPOINT_REL,
            "files": files,
        },
        indent=2,
    )


@mcp.tool()
def build_extension(project_path: str) -> str:
    """Run a build of an Ableton Extension project.

    Side effects: runs ``npm install`` and ``npm run build`` in the
    supplied project directory.

    Contract (v0.5.1): the JSON document returned by this tool has the
    following shape::

        {
            "status": "built" | "error",
            "entrypoint": "dist/extension.js",
            "entrypoint_exists": true,
            "steps": [
                {"step": "install", "returncode": 0,
                 "stdout": "...", "stderr": "..."},
                {"step": "build", "returncode": 0,
                 "stdout": "...", "stderr": "..."}
            ],
            "artifacts": ["dist/extension.js", "..."]
        }

    ``entrypoint`` is read from ``package.json["main"]`` (falling back
    to ``manifest.json["entry"]`` when ``main`` is missing) so the
    contract reflects the project's own declaration. ``artifacts`` is
    populated when ``status == "built"`` and lists every file under
    ``dist/`` relative to the project root. When the build completes
    but the declared entrypoint is missing on disk, ``status`` flips
    to ``"error"`` and ``entrypoint_exists`` is ``false``.

    Example: ``build_extension("/path/to/my-extension")`` runs
    ``npm install`` then ``npm run build`` and returns the JSON
    document above. Requires Node.js and npm on the host machine.
    Edge cases: returns ``{"status": "error", "message": ...}``
    when ``package.json`` is missing; never raises during the
    subprocess execution — every step's ``returncode`` is reported
    in the ``steps`` array instead.
    """
    request = models.BuildExtensionRequest(project_path=project_path)
    project = Path(request.project_path)
    if not (project / "package.json").is_file():
        return json.dumps(
            {"status": "error", "message": "no package.json found", "project_path": str(project)},
            indent=2,
        )

    entrypoint_rel = _resolve_extension_entrypoint(project)
    if entrypoint_rel is None:
        return json.dumps(
            {
                "status": "error",
                "message": (
                    "package.json has no 'main' and manifest.json has no 'entry'; "
                    "cannot validate build artefact"
                ),
            },
            indent=2,
        )

    steps: list[dict[str, Any]] = []
    # Use an argument list rather than shell=True so the user-supplied
    # project_path can never be interpreted by a shell. Each step is a
    # separate subprocess so a failing install does not mask a build failure.
    npm_bin = shutil.which("npm") or "npm"
    for step_name, raw_cmd in (
        (_EXTENSION_INSTALL_STEP_NAME, [npm_bin, "install"]),
        (_EXTENSION_BUILD_STEP_NAME, [npm_bin, "run", "build"]),
    ):
        cmd = ["cmd.exe", "/c"] + raw_cmd if os.name == "nt" else raw_cmd
        result = subprocess.run(
            cmd,
            cwd=str(project),
            shell=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        steps.append(
            {
                "step": step_name,
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-2000:] if result.stderr else "",
            }
        )
        if result.returncode != 0:
            return json.dumps(
                {
                    "status": "error",
                    "entrypoint": entrypoint_rel,
                    "entrypoint_exists": ((project / entrypoint_rel).is_file()),
                    "steps": steps,
                    "artifacts": [],
                },
                indent=2,
            )

    dist_dir = project / "dist"
    artifacts: list[str] = []
    if dist_dir.is_dir():
        for candidate in sorted(dist_dir.rglob("*")):
            if candidate.is_file():
                artifacts.append(candidate.relative_to(project).as_posix())

    entrypoint_exists = (project / entrypoint_rel).is_file()
    status = "built" if entrypoint_exists else "error"
    return json.dumps(
        {
            "status": status,
            "entrypoint": entrypoint_rel,
            "entrypoint_exists": entrypoint_exists,
            "steps": steps,
            "artifacts": artifacts,
        },
        indent=2,
    )


def _resolve_extension_entrypoint(project: Path) -> str | None:
    """Discover the canonical Extension entrypoint.

    Prefers ``package.json["main"]`` (Node's package entry convention).
    Falls back to ``manifest.json["entry"]`` so legacy scaffolds that
    only declared ``manifest.entry`` still validate. Returns ``None``
    when neither source is present.
    """
    pkg_path = project / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pkg = None
        if isinstance(pkg, dict):
            main = pkg.get("main")
            if isinstance(main, str) and main.strip():
                return main.strip()
    manifest_path = project / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        if isinstance(manifest, dict):
            entry = manifest.get("entry")
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
    return None


PUBLIC_TOOL_FUNCTIONS_HEAD = (
    get_session_info,
    get_session_overview,
    get_bridge_status,
    get_track_list,
    get_track_state,
    get_locators,
    take_snapshot,
    get_ableton_logs,
    get_control_surfaces,
    get_scenes,
    get_scene_state,
    get_project_metadata,
    get_loop_settings,
    get_selected_context,
    get_clip_summary,
    get_clip_notes,
    get_clip_info,
    get_device_list,
    get_parameter_value,
    set_parameter_value,
    get_routing,
    get_browser_categories,
    search_browser,
    diff_snapshots_tool,
    get_song_length,
    live_find_track,
    list_device_params,
    create_cue_point,
    bulk_create_cue_points,
    delete_cue_point,
    set_current_song_time,
    set_tempo,
    start_playback,
    stop_playback,
    set_loop,
    set_loop_start,
    set_loop_length,
    run_batch,
    add_notes_to_clip,
    fire_clip,
    create_clip,
    delete_clip,
    clear_clip_notes,
    fire_scene,
    set_track_property,
    set_clip_properties,
    create_clip_automation,
    # v0.3.0
    get_composition_structure,
    diagnose_midi_clip,
    create_midi_track,
    rename_track,
    get_warp_state,
    set_warp_state,
    load_device_to_track,
    scaffold_extension,
    build_extension,
    # v0.5.0 — set lifecycle
    lifecycle_status,
    save_set,
    quit_ableton,
    live_fade,
    create_audio_track,
)
# NOTE: v0.5.0 offline mix analysis wrappers (analyze_audio, find_frequency_masking,
# analyze_mix, extract_single_cycle) are defined below; the canonical PUBLIC_TOOL_FUNCTIONS
# tuple is assembled AFTER those definitions so all names are in scope.


# ---------------------------------------------------------------------------
# v0.5.0 — Offline Mix Analysis
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_audio(path: str) -> ToolResult:
    """Compute LUFS-I, true-peak, RMS, and per-band energy summary for a
    local audio file.

    Side effects: reads the file from disk.
    Example: ``analyze_audio(path="/stems/kick.wav")`` returns LUFS-I plus
    per-band energy summary.
    Edge cases: missing files and unsupported encodings return a structured
    ``{"ok": False, "reason": ...}``.
    """
    return _explicit_json_result(_analyze_audio(path))


@mcp.tool()
def find_frequency_masking(
    target_path: str,
    reference_path: str,
    threshold_db: float = 6.0,
) -> ToolResult:
    """Identify frequency bands where ``target_path`` exceeds ``reference_path``
    by ``threshold_db`` dB or more.

    Side effects: reads both files.
    Example: ``find_frequency_masking(target_path=master, reference_path=kick)``
    suggests band-level cuts.
    Edge cases: mismatched sample rates raise a structured error; identical
    paths are rejected at the model.
    """
    return _explicit_json_result(
        _find_frequency_masking(
            target_path=target_path,
            reference_path=reference_path,
            threshold_db=threshold_db,
        )
    )


@mcp.tool()
def analyze_mix(stems: list[str]) -> ToolResult:
    """Run per-stem analysis and pair-wise masking across up to 16 local audio files.

    Side effects: reads each stem from disk.
    Example: ``analyze_mix(stems=["/stems/kick.wav", "/stems/bass.wav"])`` returns
    per-stem LUFS plus pair-wise masking scores.
    Edge cases: more than 16 stems raises a structured error; missing files
    are reported per-stem via ``{"ok": False, "reason": ...}``.
    """
    return _explicit_json_result(_analyze_mix(stems=stems))


@mcp.tool()
def extract_single_cycle(path: str, frame_size: int = 2048) -> ToolResult:
    """Find a candidate single-cycle loop in a local audio file plus its
    detected pitch.

    Side effects: reads the file from disk.
    Example: ``extract_single_cycle(path="/stems/kick.wav")`` returns the
    detected pitch plus the single-cycle sample buffer.
    Edge cases: aperiodic content returns ``{"ok": False, "reason": ...}``
    instead of crashing.
    """
    return _explicit_json_result(_extract_single_cycle(path=path, frame_size=frame_size))


# Canonical ordered tuple of every public tool callable. Assembled after the
# v0.5.0 offline mix analysis wrappers are defined so all names are in scope.
PUBLIC_TOOL_FUNCTIONS = (
    *PUBLIC_TOOL_FUNCTIONS_HEAD,
    # v0.5.0 — offline mix analysis
    analyze_audio,
    find_frequency_masking,
    analyze_mix,
    extract_single_cycle,
)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
