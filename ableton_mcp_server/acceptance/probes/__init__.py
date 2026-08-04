"""Probe groups + registry helpers.

Each catalogued tool has a home in exactly one probe group. The
runner derives its probe groups from ``BASELINE_PROBE_GROUPS`` and
refuses to finish until every catalogued tool has a recorded row.

Probe groups themselves are filled in by subagents in Phase 2:

- :mod:`ableton_mcp_server.acceptance.probes.offline`
- :mod:`ableton_mcp_server.acceptance.probes.composed`
- :mod:`ableton_mcp_server.acceptance.probes.tcp_reads`
- :mod:`ableton_mcp_server.acceptance.probes.websocket_reads`
- :mod:`ableton_mcp_server.acceptance.probes.mutations`
- :mod:`ableton_mcp_server.acceptance.probes.quit`

The constants here stay because they are referenced by ``report.py``
and the public API.
"""

from __future__ import annotations

# Tools that may legitimately be classified ``environment_unavailable``
# under specific, documented conditions. Everything else either runs,
# raises ``BridgeError`` → ``failed``, or is missing-from-profile.
#
# ``quit_ableton`` is classified ``manual_required`` whenever it is not
# actually invoked. The runner must never record ``live_passed`` for an
# operation that was not executed: that is a documented false-positive
# pattern. ``build_extension`` is unavailable only when Node is genuinely
# absent. ``fire_clip`` is unavailable when ``--fire-clip`` is not set.
_ALLOWED_UNAVAILABLE: dict[str, str] = {
    "build_extension": "node executable not found on PATH",
    "fire_clip": "fire_clip requires --fire-clip flag",
}

# ``quit_ableton`` is only valid as ``live_passed`` after the bridge was
# actually invoked and a real shutdown handshake completed. The runner
# does not invoke it during the automated probe (doing so would close
# the host and block every later probe). Until an out-of-band owner
# confirmation arrives, the row must read ``manual_required``.
QUIT_ABLETON_MANUAL_REASON = (
    "quit_ableton requires out-of-band owner confirmation; "
    "automated probe never invokes a destructive shutdown"
)

# Slice 1 Task 9: baseline probe map. The flattened names must equal the
# 66-name ``PUBLIC_TOOL_NAMES`` set, so each catalogued tool has a home in
# exactly one probe group. The runner never fabricates
# ``environment_unavailable`` for a tool that is actually selected.
BASELINE_PROBE_GROUPS: dict[str, tuple[str, ...]] = {
    "offline": (
        "get_ableton_logs",
        "diff_snapshots_tool",
        "scaffold_extension",
        "build_extension",
        "analyze_audio",
        "find_frequency_masking",
        "analyze_mix",
        "extract_single_cycle",
    ),
    "composed": ("get_bridge_status", "get_session_overview"),
    "tcp_reads": (
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
    ),
    "websocket_reads": ("get_warp_state",),
    # Tools whose contract is a refusal. The probe proves they reject a
    # well-formed request with CAPABILITY_UNAVAILABLE and change nothing;
    # a success is recorded as a hard failure.
    "capability": (
        "move_track",
        "reorder_tracks",
        "move_track_to_group",
        "ungroup_track",
        "merge_groups",
    ),
    "mutations": (
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
        "live_fade",
        "set_warp_state",
        "load_device_to_track",
    ),
    "quit": ("quit_ableton",),
}


def _baseline_probe_names() -> tuple[str, ...]:
    names: list[str] = []
    for group in BASELINE_PROBE_GROUPS.values():
        names.extend(group)
    return tuple(names)


def assert_baseline_probe_coverage() -> None:
    flat = set(_baseline_probe_names())
    from ..helpers import _baseline_tool_names

    catalog_names = set(_baseline_tool_names())
    assert flat == catalog_names, (
        f"baseline probe mismatch: missing={catalog_names - flat}, extra={flat - catalog_names}"
    )


def _expand_profiles(profiles: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve ``"baseline"`` to every group and validate names."""
    if "baseline" in profiles:
        return tuple(BASELINE_PROBE_GROUPS)
    for profile in profiles:
        if profile not in BASELINE_PROBE_GROUPS:
            raise ValueError(f"unknown acceptance profile: {profile}")
    return profiles


# Public alias for new code. The legacy underscore-prefixed name above
# stays in place so the monolith body in ``runner.py`` keeps working.
expand_profiles = _expand_profiles
