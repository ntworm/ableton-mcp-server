# GENERATED FILE - DO NOT EDIT.
# Source: ../contracts.py
# Regenerate with: python scripts/vendor_contracts.py

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
        "live_find_device",
        "live_find_clip",
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
        # v0.5.3 — clip colour target discovery (Session + Arrangement)
        "diagnose_clip_targets",
        # v0.5.4 — plugin preset discovery (needs no Configure step)
        "get_plugin_presets",
        # v0.5.5 — Arrangement timeline read: placement, not just existence
        "get_arrangement_clips",
        # v0.5.6 — instrument comprehension: what an agent must know before it
        # writes anything into a track it did not build
        "get_device_chains",
        "get_midi_chain_report",
        "describe_instrument",
        "get_clip_automation",
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
        # v0.5.3 — verified track and clip colour writes
        "set_track_color",
        "set_clip_color",
        # v0.4.0 — Session clip automation only
        "create_clip_automation",
        # v0.5.0 — set lifecycle mutations
        "save_set",
        "quit_ableton",
        "live_fade",
        # v0.5.0 — audio-track mirror of create_midi_track
        "create_audio_track",
        # v0.5.4 — verified plugin preset write (needs no Configure step)
        "set_plugin_preset",
        # v0.5.5 — Arrangement authoring. Track.duplicate_clip_to_arrangement is
        # the only public path from a Session slot onto the timeline; deletion
        # and movement build on the same handle.
        "duplicate_session_clip_to_arrangement",
        "delete_arrangement_clip",
        "move_arrangement_clip",
        # v0.5.6 — authoring shorthands: the server expands them so callers do
        # not ship hundreds of breakpoints or repeated note cells
        "create_clip_automation_curve",
        "add_notes_pattern",
        "set_arrangement_clip_properties",
    }
)

READ_ONLY_COMMANDS = frozenset(
    {
        "delete_track",
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

# ---------------------------------------------------------------------------
# Capabilities that no public API can perform
# ---------------------------------------------------------------------------
#
# These name real Live editing gestures that neither the public Live Object
# Model nor the Ableton Extension SDK exposes. They are *routed* — the Remote
# Script validates the request against the live Set first, so a malformed call
# still returns INVALID_PARAMS / BAD_INPUT / WRONG_TYPE — and then answered
# with a typed ``CAPABILITY_UNAVAILABLE`` carrying the evidence below. A
# caller can therefore tell "your request was wrong", "this bridge has not
# implemented it", and "no public API can do it" apart from each other.
#
# Evidence was collected against the Live 12 LOM reference published by
# Cycling '74 and against the vendored ``ableton-extensions-sdk`` 1.0.0-beta.0
# type declarations, not from memory. Re-verify with a newer Live/SDK before
# assuming any of this changed.

# Every ``Song`` function in the Live 12 LOM, for the record. There are 34 and
# not one of them repositions a track.
LOM_SONG_TRACK_FUNCTIONS = (
    "create_audio_track(index)",
    "create_midi_track(index)",
    "create_return_track()",
    "duplicate_track(index)",
    "delete_track(index)",
    "delete_return_track(index)",
    "move_device(device, target, target_position)",
    "find_device_position(device, target, target_position)",
)

# The Extension SDK 1.0.0-beta.0 DataModel bindings that touch tracks.
SDK_TRACK_BINDINGS = (
    "songCreateMidiTrack(handle)",
    "songCreateAudioTrack(handle)",
    "songDuplicateTrack(handle, trackHandle)",
    "songDeleteTrack(handle, trackHandle)",
    "trackGetGroupTrack(handle)",
)

_NO_TRACK_MOVE_EVIDENCE = {
    "lom_song_functions_checked": LOM_SONG_TRACK_FUNCTIONS,
    "lom_verdict": (
        "Song exposes track creation at an index, duplication and deletion, "
        "but no reposition entry point. song.tracks and song.visible_tracks "
        "are get/observe lists and cannot be assigned. Track.group_track is "
        "get-only, so a track cannot be re-parented either."
    ),
    "sdk_bindings_checked": SDK_TRACK_BINDINGS,
    "sdk_verdict": (
        "ableton-extensions-sdk 1.0.0-beta.0 has no reposition binding. Its "
        "Song.createAudioTrack() / createMidiTrack() do not even accept an "
        "index ('Inserted after the last selected track, or appended'), and "
        "Track exposes groupTrack as a getter only."
    ),
    "rejected_workarounds": (
        "duplicate_track + delete_track cannot reorder at all: the duplicate "
        "is always inserted immediately after the original, so relative order "
        "never changes — and it would destroy the original track.",
        "Rebuilding a track at a new index would have to copy devices, clips, "
        "notes, automation, envelopes, routing and mixer state by hand; the "
        "LOM has no API for most of that, so content would be silently lost.",
        "GUI automation and .als file edits are out of scope by project rule.",
    ),
    "supported_alternative": (
        "Create tracks at the index you want with create_audio_track(index) / "
        "create_midi_track(index), or reorder and (un)group by hand in Live "
        "(drag, or Cmd/Ctrl+G). Devices — unlike tracks — can be moved "
        "between tracks with Song.move_device."
    ),
}

UNSUPPORTED_CAPABILITIES = {
    "move_track": (
        "Moving an existing track to another index is not exposed by the "
        "public Live Object Model or by the Ableton Extension SDK."
    ),
    "reorder_tracks": (
        "Reordering existing tracks is not exposed by the public Live Object "
        "Model or by the Ableton Extension SDK."
    ),
    "move_track_to_group": (
        "Re-parenting a track into a Group Track is not exposed by the public "
        "Live Object Model or by the Ableton Extension SDK: Track.group_track "
        "is read-only and no grouping function exists."
    ),
    "ungroup_track": (
        "Removing a track from its Group Track is not exposed by the public "
        "Live Object Model or by the Ableton Extension SDK: Track.group_track "
        "is read-only and there is no ungroup function."
    ),
    "merge_groups": (
        "Moving the members of one Group Track into another is not exposed by "
        "the public Live Object Model or by the Ableton Extension SDK; it "
        "would require the same re-parenting operation that does not exist."
    ),
}

CAPABILITY_EVIDENCE = {name: _NO_TRACK_MOVE_EVIDENCE for name in UNSUPPORTED_CAPABILITIES}

# Routed like a command so the Remote Script can validate against the real
# Set, but never a mutation: no undo step is opened and nothing is written.
UNAVAILABLE_COMMANDS = frozenset(UNSUPPORTED_CAPABILITIES)

ALL_REMOTE_COMMANDS = READ_COMMANDS | ALLOWED_MUTATIONS
ALL_ROUTED_COMMANDS = ALL_REMOTE_COMMANDS | UNAVAILABLE_COMMANDS

# Live's colour palette. ``color_index`` addresses the 70-swatch palette
# (14 columns x 5 rows) shown in Live's colour chooser; ``color`` is the
# packed ``0x00rrggbb`` value of the resulting swatch. Tracks and clips share
# the same palette and the same packed-RGB encoding. The LOM reference
# documents ``color`` explicitly and leaves the ``color_index`` range
# undocumented, so the bound below is enforced client-side and every write is
# confirmed by reading the value back.
LIVE_COLOR_INDEX_MIN = 0
LIVE_COLOR_INDEX_MAX = 69
LIVE_COLOR_RGB_MIN = 0x000000
LIVE_COLOR_RGB_MAX = 0xFFFFFF

# Names kept from the track-only colour change that introduced them.
TRACK_COLOR_INDEX_MIN = LIVE_COLOR_INDEX_MIN
TRACK_COLOR_INDEX_MAX = LIVE_COLOR_INDEX_MAX
TRACK_COLOR_RGB_MIN = LIVE_COLOR_RGB_MIN
TRACK_COLOR_RGB_MAX = LIVE_COLOR_RGB_MAX


def is_unsupported_capability(command_name: str) -> bool:
    return command_name.strip().lower() in UNSUPPORTED_CAPABILITIES


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


# ---------------------------------------------------------------------------
# Plugin devices (v0.5.4)
# ---------------------------------------------------------------------------
#
# Live wraps VST/VST3/AU plugins in a device whose ``parameters`` list is not
# the plugin's parameter set. It contains only ``Device On`` plus whatever the
# user added by hand through the device's Configure button. Until somebody
# does that in the Live GUI, the LOM has nothing to hand back, so a plugin
# looks parameterless to every automation surface — the LOM, MIDI mapping and
# clip automation alike. That is Live's design, not a bridge limitation, and
# no remote API can add a parameter to the Configure list.
#
# ``PluginDevice.presets`` / ``selected_preset_index`` are the exception: they
# are exposed without Configure, which is why ``get_plugin_presets`` and
# ``set_plugin_preset`` are the one plugin surface an agent can drive alone.

PLUGIN_DEVICE_CLASS_NAMES = frozenset({"PluginDevice", "AuPluginDevice"})

PLUGIN_NOT_CONFIGURED = "PLUGIN_NOT_CONFIGURED"

PLUGIN_NOT_CONFIGURED_HINT = (
    "Live only exposes plugin parameters that were added through the device's "
    "Configure button, so this plugin reports no automatable parameters. Ask "
    "the user to open the plugin in Live, click Configure, and add the "
    "controls they want; they then appear here with no change to this bridge. "
    "Preset switching through get_plugin_presets / set_plugin_preset works "
    "without the Configure step."
)


def is_plugin_device_class(class_name: str) -> bool:
    """Return True when ``class_name`` names a Live plugin wrapper device."""

    return class_name.strip() in PLUGIN_DEVICE_CLASS_NAMES


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

# Plugin preset access (v0.5.4)
COMMAND_GET_PLUGIN_PRESETS = "get_plugin_presets"
COMMAND_SET_PLUGIN_PRESET = "set_plugin_preset"
