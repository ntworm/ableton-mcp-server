"""Dependency-free protocol contract shared with the Ableton Remote Script."""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9888
DEFAULT_WS_PORT = 9889

REQUEST_TYPE_FIELD = "type"
REQUEST_PARAMS_FIELD = "params"
RESPONSE_STATUS_OK = "ok"
RESPONSE_STATUS_ERROR = "error"

ERROR_UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
ERROR_INVALID_PARAMS = "INVALID_PARAMS"
ERROR_READ_ONLY_VIOLATION = "READ_ONLY_VIOLATION"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_LIVE_UNAVAILABLE = "LIVE_UNAVAILABLE"
ERROR_INTERNAL_ERROR = "INTERNAL_ERROR"
ERROR_PLAYHEAD_NOT_MOVED = "PLAYHEAD_NOT_MOVED"
ERROR_CUE_SNAPPED_TO_GRID = "CUE_SNAPPED_TO_GRID"
ERROR_STALE_REFERENCE = "STALE_REFERENCE"
ERROR_WRONG_TYPE = "WRONG_TYPE"
ERROR_BAD_INPUT = "BAD_INPUT"
ERROR_EXTENSION_UNAVAILABLE = "EXTENSION_UNAVAILABLE"
ERROR_TRACK_LIMIT_REACHED = "TRACK_LIMIT_REACHED"
ERROR_CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
ERROR_AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
ERROR_VERIFICATION_FAILED = "VERIFICATION_FAILED"
ERROR_ACCEPTANCE_GUARD_FAILED = "ACCEPTANCE_GUARD_FAILED"

CUE_TIME_TOLERANCE = 0.01
CUE_OPERATION_VERIFY_TICKS = 10
PLAYHEAD_MOVE_RETRIES = 10
SNAPSHOT_REFRESH_INTERVAL_MS = 100
REQUEST_TIMEOUT_SECONDS = 20.0
REQUEST_TIMEOUT_PER_WORK_UNIT_SECONDS = 2.0
COMMAND_TIMEOUT_OVERRIDES = {
    "load_device_to_track": 30.0,
    "search_browser": 30.0,
    "create_clip_automation": 20.0,
    "live_fade": 60.0,
}


def _request_work_units(command_name: str, params: object) -> int:
    if not isinstance(params, dict):
        return 1
    normalized = command_name.strip().lower()
    if normalized == "bulk_create_cue_points":
        items = params.get("items")
        return max(1, len(items)) if isinstance(items, list) else 1
    if normalized == "create_clip_automation":
        points = params.get("automation_points")
        return min(10, 1 + len(points)) if isinstance(points, list) else 1
    if normalized == "set_clip_properties":
        return max(1, sum(name in params for name in ("loop_start", "loop_end", "name")))
    if normalized == "clear_clip_notes":
        return 2
    if normalized == "live_fade":
        steps = params.get("steps")
        return min(60, int(steps) + 1) if isinstance(steps, int) else 41
    if normalized == "run_batch":
        commands = params.get("commands")
        if not isinstance(commands, list):
            return 1
        units = 0
        for command in commands:
            if not isinstance(command, dict):
                units += 1
                continue
            command_type = command.get("type")
            command_params = command.get("params", {})
            units += _request_work_units(
                command_type if isinstance(command_type, str) else "",
                command_params,
            )
        return max(1, units)
    return 1


def request_timeout_seconds(command_name: str, params: object) -> float:
    """Return a shared client/server deadline scaled to serialized UI work.

    ``live_fade`` is special: its deadline must exceed the requested
    ``duration`` by enough overhead to absorb Live's ``update_display``
    tick jitter. With ``duration=60, steps=1`` the previous formula
    returned exactly ``60.0``, leaving zero margin and timing out under
    normal scheduler jitter. We now add ``REQUEST_TIMEOUT_SECONDS`` of
    slack on top of the requested ``duration`` for ``live_fade``.
    """

    work_units = _request_work_units(command_name, params)
    scaled = REQUEST_TIMEOUT_SECONDS + (work_units - 1) * REQUEST_TIMEOUT_PER_WORK_UNIT_SECONDS
    override = COMMAND_TIMEOUT_OVERRIDES.get(command_name.strip().lower(), 0.0)
    base = max(scaled, override)
    normalized = command_name.strip().lower()
    if normalized == "live_fade" and isinstance(params, dict):
        duration = params.get("duration")
        if isinstance(duration, (int, float)) and float(duration) > 0.0:
            return max(base, float(duration) + REQUEST_TIMEOUT_SECONDS)
    return base


READ_COMMANDS = frozenset(
    {
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
        "get_device_list",
        "get_parameter_value",
        "get_routing",
        "get_browser_categories",
        "get_song_length",
        "live_find_track",
        "list_device_params",
        # v0.3.0 — composition diagnostics
        "get_composition_structure",
        "diagnose_midi_clip",
        # v0.3.0 — warp read (routed via WebSocket)
        "get_warp_state",
        # v0.4.0 — Session detail and bounded browser discovery
        "get_clip_info",
        "search_browser",
        # v0.5.0 — set lifecycle read-only probe
        "lifecycle_status",
    }
)

ALLOWED_MUTATIONS = frozenset(
    {
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
        "create_clip",
        "fire_clip",
        "add_notes_to_clip",
        # v0.3.0 — guarded creative mutations
        "create_midi_track",
        "rename_track",
        # v0.3.0 — warp write (routed via WebSocket)
        "set_warp_state",
        # v0.3.0 — device loading (routed via WebSocket)
        "load_device_to_track",
        # v0.4.0 — verified device parameter write (TCP)
        "set_parameter_value",
        # v0.4.0 — Session clip and scene mutations
        "delete_clip",
        "clear_clip_notes",
        "fire_scene",
        # v0.4.0 — verified track and clip attributes
        "set_track_property",
        "set_clip_properties",
        # v0.4.0 — Session clip automation only
        "create_clip_automation",
        # v0.5.0 — set lifecycle mutations
        "save_set",
        "quit_ableton",
        "live_fade",
        # v0.5.0 — audio-track mirror of create_midi_track
        "create_audio_track",
    }
)

READ_ONLY_COMMANDS = frozenset(
    {
        "delete_track",
        "duplicate_session_clip_to_arrangement",
        "switch_to_arrangement_view",
        "load_instrument_or_effect",
        "load_browser_item",
    }
)

# v0.3.0 — Commands routed to the Extension Host WebSocket bridge (port 9889)
# instead of the Remote Script TCP bridge (port 9888).
WEBSOCKET_TARGET_COMMANDS = frozenset(
    {
        "get_warp_state",
        "set_warp_state",
        "load_device_to_track",
    }
)

ALL_REMOTE_COMMANDS = READ_COMMANDS | ALLOWED_MUTATIONS


def is_allowed_mutation(command_name: str) -> bool:
    return command_name.strip().lower() in ALLOWED_MUTATIONS


def is_read_only(command_name: str) -> bool:
    return command_name.strip().lower() in READ_ONLY_COMMANDS


def assert_not_blocked(command_name: str) -> None:
    """Raise when an explicitly blocked creative mutation is requested."""

    normalized = command_name.strip().lower()
    if normalized in READ_ONLY_COMMANDS:
        raise ValueError(
            "Command %r is blocked: creative mutation is not available." % command_name
        )


# Set lifecycle and fader fade (v0.5.0)
COMMAND_LIFECYCLE_STATUS = "lifecycle_status"
COMMAND_SAVE_SET = "save_set"
COMMAND_QUIT_ABLETON = "quit_ableton"
COMMAND_LIVE_FADE = "live_fade"
COMMAND_CREATE_AUDIO_TRACK = "create_audio_track"
COMMAND_ANALYZE_AUDIO = "analyze_audio"
COMMAND_FIND_FREQUENCY_MASKING = "find_frequency_masking"
COMMAND_ANALYZE_MIX = "analyze_mix"
COMMAND_EXTRACT_SINGLE_CYCLE = "extract_single_cycle"
