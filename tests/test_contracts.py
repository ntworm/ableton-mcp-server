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
