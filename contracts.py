"""Dependency-free protocol contract shared with the Ableton Remote Script."""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9888

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
ERROR_STALE_REFERENCE = "STALE_REFERENCE"
ERROR_WRONG_TYPE = "WRONG_TYPE"
ERROR_BAD_INPUT = "BAD_INPUT"

CUE_TIME_TOLERANCE = 0.01
PLAYHEAD_MOVE_RETRIES = 3
SNAPSHOT_REFRESH_INTERVAL_MS = 100
REQUEST_TIMEOUT_SECONDS = 6.0

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
    }
)

READ_ONLY_COMMANDS = frozenset(
    {
        "create_midi_track",
        "delete_track",
        "set_track_name",
        "duplicate_session_clip_to_arrangement",
        "switch_to_arrangement_view",
        "load_instrument_or_effect",
        "load_browser_item",
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
