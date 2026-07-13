from __future__ import annotations

import contracts


def test_protocol_constants_match_approved_transport() -> None:
    assert contracts.DEFAULT_HOST == "127.0.0.1"
    assert contracts.DEFAULT_PORT == 9888
    assert contracts.REQUEST_TYPE_FIELD == "type"
    assert contracts.REQUEST_PARAMS_FIELD == "params"


def test_debug_mutations_are_explicitly_allowed() -> None:
    expected = {
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
        # v0.3.0
        "create_midi_track",
        "rename_track",
        "set_warp_state",
        "load_device_to_track",
        "set_parameter_value",
        "delete_clip",
        "clear_clip_notes",
        "fire_scene",
        "set_track_property",
        "set_clip_properties",
        "create_clip_automation",
        # v0.5.0 — set lifecycle mutations
        "save_set",
        "quit_ableton",
    }
    assert frozenset(expected) == contracts.ALLOWED_MUTATIONS
    assert expected.isdisjoint(contracts.READ_ONLY_COMMANDS)


def test_creative_mutations_remain_blocked_without_prefix_rules() -> None:
    assert (
        frozenset(
            {
                "delete_track",
                "duplicate_session_clip_to_arrangement",
                "switch_to_arrangement_view",
                "load_instrument_or_effect",
                "load_browser_item",
            }
        )
        == contracts.READ_ONLY_COMMANDS
    )
    assert not contracts.is_read_only("set_tempo")
    assert not contracts.is_read_only("set_song_length")
    assert "set_song_length" not in contracts.ALL_REMOTE_COMMANDS


def test_remote_command_sets_do_not_overlap() -> None:
    assert contracts.READ_COMMANDS.isdisjoint(contracts.ALLOWED_MUTATIONS)
    assert contracts.ALL_REMOTE_COMMANDS == (contracts.READ_COMMANDS | contracts.ALLOWED_MUTATIONS)


def test_v040_remote_reads_are_explicitly_registered() -> None:
    assert {"get_clip_info", "search_browser"} <= contracts.READ_COMMANDS
    assert "get_session_overview" not in contracts.ALL_REMOTE_COMMANDS


def test_v040_work_units_and_slow_command_timeouts_are_bounded() -> None:
    assert contracts.request_timeout_seconds("load_device_to_track", {}) == 30.0
    assert contracts.request_timeout_seconds("search_browser", {"query": "Operator"}) == 30.0
    assert contracts.request_timeout_seconds(
        "set_clip_properties",
        {"loop_start": 0, "loop_end": 8, "name": "Verse"},
    ) == 24.0
    assert contracts.request_timeout_seconds("clear_clip_notes", {}) == 22.0
    assert contracts.request_timeout_seconds(
        "create_clip_automation",
        {"automation_points": [{"time": index, "value": 0.5} for index in range(20)]},
    ) == 38.0
