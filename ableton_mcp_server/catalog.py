from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Route(str, Enum):
    LOCAL = "local"
    TCP = "tcp"
    WEBSOCKET = "websocket"
    COMPOSED = "composed"


class Risk(str, Enum):
    READ = "read"
    REVERSIBLE = "reversible"
    DESTRUCTIVE = "destructive"
    LIFECYCLE = "lifecycle"
    LOCAL_WRITE = "local_write"
    # Validated, never applied: Live's public API cannot perform the
    # operation, so the tool refuses with CAPABILITY_UNAVAILABLE.
    UNAVAILABLE = "unavailable"


class AcceptanceMode(str, Enum):
    OFFLINE = "offline"
    GUARDED = "guarded"
    MANUAL = "manual"
    ENVIRONMENT = "environment"
    # Certified by proving the refusal, not by proving a mutation.
    CAPABILITY = "capability"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    domain: str
    route: Route
    risk: Risk
    acceptance: AcceptanceMode
    reversible: bool


def _group(
    names: tuple[str, ...],
    *,
    domain: str,
    route: Route,
    risk: Risk,
    acceptance: AcceptanceMode,
    reversible: bool,
) -> tuple[ToolSpec, ...]:
    return tuple(ToolSpec(name, domain, route, risk, acceptance, reversible) for name in names)


_LOCAL_READS = (
    "get_ableton_logs",
    "diff_snapshots_tool",
    "analyze_audio",
    "find_frequency_masking",
    "analyze_mix",
    "extract_single_cycle",
)
_LOCAL_WRITES = ("scaffold_extension", "build_extension")
_COMPOSED_READS = ("get_session_overview", "get_bridge_status")
_WS_READS = ("get_warp_state",)
_WS_WRITES = ("set_warp_state", "load_device_to_track")
_TCP_READS = (
    "get_session_info",
    "get_track_list",
    "get_track_state",
    "get_locators",
    "take_snapshot",
    "get_control_surfaces",
    "get_scenes",
    "get_scene_state",
    "get_project_metadata",
    "get_loop_settings",
    "get_selected_context",
    "get_clip_summary",
    "get_clip_notes",
    "get_clip_info",
    "get_device_list",
    "get_parameter_value",
    "get_routing",
    "get_browser_categories",
    "search_browser",
    "get_song_length",
    "live_find_track",
    "list_device_params",
    "get_composition_structure",
    "diagnose_midi_clip",
    "lifecycle_status",
    "diagnose_clip_targets",
)
# Routed like commands so the Remote Script can validate them against the real
# Set, but they never mutate: Live's public API cannot perform any of them.
_TCP_UNAVAILABLE = (
    "move_track",
    "reorder_tracks",
    "move_track_to_group",
    "ungroup_track",
    "merge_groups",
)
_TCP_MUTATIONS = (
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
    "delete_clip",
    "clear_clip_notes",
    "fire_scene",
    "set_track_property",
    "set_track_color",
    "set_clip_color",
    "set_clip_properties",
    "create_clip_automation",
    "create_midi_track",
    "create_audio_track",
    "rename_track",
    "set_parameter_value",
    "save_set",
    "quit_ableton",
    "live_fade",
)


TOOL_CATALOG = (
    *_group(
        _TCP_READS,
        domain="live",
        route=Route.TCP,
        risk=Risk.READ,
        acceptance=AcceptanceMode.GUARDED,
        reversible=True,
    ),
    *_group(
        _TCP_MUTATIONS[:-3],
        domain="live",
        route=Route.TCP,
        risk=Risk.REVERSIBLE,
        acceptance=AcceptanceMode.GUARDED,
        reversible=True,
    ),
    *_group(
        _TCP_UNAVAILABLE,
        domain="hierarchy",
        route=Route.TCP,
        risk=Risk.UNAVAILABLE,
        acceptance=AcceptanceMode.CAPABILITY,
        reversible=True,
    ),
    ToolSpec("save_set", "lifecycle", Route.TCP, Risk.LIFECYCLE, AcceptanceMode.GUARDED, False),
    ToolSpec("quit_ableton", "lifecycle", Route.TCP, Risk.LIFECYCLE, AcceptanceMode.MANUAL, False),
    ToolSpec("live_fade", "mixer", Route.TCP, Risk.REVERSIBLE, AcceptanceMode.GUARDED, True),
    *_group(
        _WS_READS,
        domain="extension",
        route=Route.WEBSOCKET,
        risk=Risk.READ,
        acceptance=AcceptanceMode.GUARDED,
        reversible=True,
    ),
    *_group(
        _WS_WRITES,
        domain="extension",
        route=Route.WEBSOCKET,
        risk=Risk.REVERSIBLE,
        acceptance=AcceptanceMode.GUARDED,
        reversible=True,
    ),
    *_group(
        _COMPOSED_READS,
        domain="diagnostics",
        route=Route.COMPOSED,
        risk=Risk.READ,
        acceptance=AcceptanceMode.GUARDED,
        reversible=True,
    ),
    *_group(
        _LOCAL_READS,
        domain="local",
        route=Route.LOCAL,
        risk=Risk.READ,
        acceptance=AcceptanceMode.OFFLINE,
        reversible=True,
    ),
    ToolSpec(
        "scaffold_extension",
        "developer",
        Route.LOCAL,
        Risk.LOCAL_WRITE,
        AcceptanceMode.OFFLINE,
        True,
    ),
    ToolSpec(
        "build_extension",
        "developer",
        Route.LOCAL,
        Risk.LOCAL_WRITE,
        AcceptanceMode.ENVIRONMENT,
        True,
    ),
)
