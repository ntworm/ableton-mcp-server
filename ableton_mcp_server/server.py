from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Generator, Sequence
from pathlib import Path
from typing import Any

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FASTMCP_TELEMETRY_DISABLED", "true")
os.environ.setdefault("MCP_TELEMETRY_DISABLED", "true")

from fastmcp import FastMCP
from fastmcp.tools import Tool

from contracts import DEFAULT_HOST, DEFAULT_PORT

from . import models
from .client import Client
from .diff import diff_snapshots

PUBLIC_TOOL_NAMES = (
    "get_session_info",
    "get_track_list",
    "get_track_state",
    "get_locators",
    "take_snapshot",
    "get_ableton_logs",
    "get_control_surfaces",
    "get_scenes",
    "get_scene_state",
    "get_project_metadata",
    "get_loop_settings",
    "get_selected_context",
    "get_clip_summary",
    "get_clip_notes",
    "get_device_list",
    "get_parameter_value",
    "get_routing",
    "get_browser_categories",
    "diff_snapshots_tool",
    "get_song_length",
    "live_find_track",
    "list_device_params",
    "create_cue_point",
    "bulk_create_cue_points",
    "delete_cue_point",
    "set_current_song_time",
    "set_tempo",
    "start_playback",
    "stop_playback",
    "set_loop",
    "set_loop_start",
    "set_loop_length",
    "run_batch",
    "add_notes_to_clip",
    "fire_clip",
    "create_clip",
)


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
        _client = Client(host=host, port=port, reconnect=True)
    return _client


def _remote(command: str, request: models.RequestModel) -> Any:
    return get_client().call(command, request.model_dump(mode="json"))


def find_ableton_log_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    ableton = Path(appdata) / "Ableton"
    if not ableton.is_dir():
        return None
    candidates = list(ableton.glob("Live */Preferences/Log.txt"))
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    except OSError:
        return None


@mcp.tool()
def get_session_info() -> Any:
    """Read top-level transport and time-signature state.

    Side effects: none.
    Example: ``get_session_info()`` returns tempo and playhead state.
    Edge cases: fails when the Remote Script is unavailable.
    """
    return _remote("get_session_info", models.GetSessionInfoRequest())


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
    """
    return _remote("create_cue_point", models.CreateCuePointRequest(name=name, time=time))


@mcp.tool()
def bulk_create_cue_points(items: list[dict[str, Any]]) -> Any:
    """Create or rename multiple cue points as one command.

    Side effects: mutates all successful items inside one undo step.
    Example: ``bulk_create_cue_points([{"name": "A", "time": 0}])``.
    Edge cases: per-item errors are aggregated instead of aborting later items.
    """
    request = models.BulkCuePointsRequest.model_validate({"items": items})
    return _remote("bulk_create_cue_points", request)


@mcp.tool()
def delete_cue_point(time: float) -> Any:
    """Delete a cue point by verified move-and-toggle.

    Side effects: mutates the Set in one undo step and temporarily moves the playhead.
    Example: ``delete_cue_point(8.0)`` deletes a cue near beat eight.
    Edge cases: no cue at the time returns ``deleted: false``.
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
    return _remote("add_notes_to_clip", request)


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


PUBLIC_TOOL_FUNCTIONS = (
    get_session_info,
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
    get_device_list,
    get_parameter_value,
    get_routing,
    get_browser_categories,
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
)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
