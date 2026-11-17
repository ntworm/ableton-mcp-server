"""Track hierarchy refusals and public surface tests moved from the original module."""

from __future__ import annotations

from typing import Any

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from contracts import (
    ALL_REMOTE_COMMANDS,
    ALL_ROUTED_COMMANDS,
    ALLOWED_MUTATIONS,
    TRACK_COLOR_INDEX_MAX,
    UNSUPPORTED_CAPABILITIES,
)
from tests.remote_fakes import FakeApplication, FakeSong, FakeTrack, grouped_song

from . import test_track_hierarchy_and_color_v053 as _shared

# The shared helper of the original module, bound here for the calls below.
call = _shared.call


# ---------------------------------------------------------------------------
# Part C - track reordering is not available
# ---------------------------------------------------------------------------


# Well-formed requests against ``grouped_song()``: group at index 0, its child
# at 1, an ungrouped track at 2. Every one of these passes validation, so the
# only thing left to refuse is the capability itself.
_WELL_FORMED_HIERARCHY_REQUESTS: dict[str, dict[str, Any]] = {
    "move_track": {"track_index": 2, "destination_index": 0},
    # grouped_song() has 3 regular tracks; the fixtures below append a 4th.
    "reorder_tracks": {"order": [3, 2, 1, 0]},
    "move_track_to_group": {"track_index": 2, "group_track_index": 0},
    "ungroup_track": {"track_index": 1},
    "merge_groups": {"source_group_index": 0, "destination_group_index": 3},
}


@pytest.mark.parametrize("command", sorted(UNSUPPORTED_CAPABILITIES))
def test_hierarchy_commands_refuse_well_formed_requests(command: str) -> None:
    song = grouped_song()
    # merge_groups needs a second group; give the loose track group status.
    song.tracks.append(FakeTrack("2 KEYS", midi=False, is_foldable=True))

    with pytest.raises(RemoteError) as error:
        call(song, command, _WELL_FORMED_HIERARCHY_REQUESTS[command])

    _assert_capability_refusal(error)
    details = error.value.details
    assert details is not None
    _assert_capability_evidence(details)


def _assert_capability_refusal(error: pytest.ExceptionInfo[RemoteError]) -> None:
    """Assert the refusal answers with the capability code and a hint."""
    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert "not exposed by the public Live Object Model" in str(error.value)
    assert error.value.hint is not None


def _assert_capability_evidence(details: dict[str, Any]) -> None:
    """Assert the refusal carries the checked evidence details."""
    assert details["applied"] is False
    assert details["request"]
    assert details["lom_song_functions_checked"]
    assert details["sdk_bindings_checked"]
    assert details["rejected_workarounds"]


@pytest.mark.parametrize("command", sorted(UNSUPPORTED_CAPABILITIES))
def test_hierarchy_commands_never_open_an_undo_step(command: str) -> None:
    """A refusal must not leave an empty undo entry in the operator's Set."""

    song = grouped_song()
    song.tracks.append(FakeTrack("2 KEYS", midi=False, is_foldable=True))
    application = FakeApplication()

    with pytest.raises(RemoteError):
        execute_command(song, application, command, _WELL_FORMED_HIERARCHY_REQUESTS[command])

    assert application.begin_count == 0
    assert application.end_count == 0


@pytest.mark.parametrize("command", sorted(UNSUPPORTED_CAPABILITIES))
def test_hierarchy_commands_leave_the_set_untouched(command: str) -> None:
    song = grouped_song()
    song.tracks.append(FakeTrack("2 KEYS", midi=False, is_foldable=True))
    before = [
        (
            track.name,
            track.color_index,
            track.is_grouped,
            len(track.devices),
            len(track.clip_slots),
        )
        for track in song.tracks
    ]

    with pytest.raises(RemoteError):
        call(song, command, _WELL_FORMED_HIERARCHY_REQUESTS[command])

    assert [
        (
            track.name,
            track.color_index,
            track.is_grouped,
            len(track.devices),
            len(track.clip_slots),
        )
        for track in song.tracks
    ] == before


def test_hierarchy_commands_are_routed_but_never_mutations() -> None:
    """Discoverable as tools, but outside the mutation allowlist."""

    from ableton_mcp_server.catalog import TOOL_CATALOG, Risk

    by_name = {spec.name: spec for spec in TOOL_CATALOG}
    for command in UNSUPPORTED_CAPABILITIES:
        assert command not in ALL_REMOTE_COMMANDS
        assert command not in ALLOWED_MUTATIONS
        assert command in ALL_ROUTED_COMMANDS
        assert by_name[command].risk is Risk.UNAVAILABLE


@pytest.mark.parametrize(
    ("command", "params", "expected_code"),
    [
        # Index and shape errors must stay distinguishable from the
        # capability gap, otherwise a caller cannot tell a typo from a
        # permanent API limit.
        ("move_track", {"track_index": 99, "destination_index": 0}, "INVALID_PARAMS"),
        ("move_track", {"track_index": 0, "destination_index": 99}, "INVALID_PARAMS"),
        ("reorder_tracks", {"order": [0, 1]}, "BAD_INPUT"),
        ("reorder_tracks", {"order": "nope"}, "INVALID_PARAMS"),
        # Target is not foldable -> WRONG_TYPE wins over the cycle rule.
        ("move_track_to_group", {"track_index": 2, "group_track_index": 2}, "WRONG_TYPE"),
        # Target is foldable and is the track itself -> cycle rule fires.
        ("move_track_to_group", {"track_index": 0, "group_track_index": 0}, "BAD_INPUT"),
        ("move_track_to_group", {"track_index": 0, "group_track_index": 1}, "WRONG_TYPE"),
        ("ungroup_track", {"track_index": 2}, "WRONG_TYPE"),
        (
            "merge_groups",
            {"source_group_index": 0, "destination_group_index": 1},
            "WRONG_TYPE",
        ),
        (
            "merge_groups",
            {
                "source_group_index": 0,
                "destination_group_index": 0,
                "delete_empty_source": True,
            },
            "BAD_INPUT",
        ),
    ],
)
def test_hierarchy_validation_runs_before_the_capability_refusal(
    command: str, params: dict[str, Any], expected_code: str
) -> None:
    song = grouped_song()
    with pytest.raises(RemoteError) as error:
        call(song, command, params)
    assert error.value.code == expected_code


def test_moving_a_return_or_main_track_is_rejected_by_type() -> None:
    song = grouped_song()
    return_index = len(song.tracks)
    master_index = return_index + 1

    for index in (return_index, master_index):
        with pytest.raises(RemoteError) as error:
            call(song, "move_track", {"track_index": index, "destination_index": 0})
        assert error.value.code == "WRONG_TYPE"


def test_nesting_a_group_inside_its_own_child_is_rejected_as_a_cycle() -> None:
    """group(0) -> child(1); asking to put 0 inside 1 would close a loop."""

    song = grouped_song()
    song.tracks[1].is_foldable = True

    with pytest.raises(RemoteError) as error:
        call(song, "move_track_to_group", {"track_index": 0, "group_track_index": 1})

    assert error.value.code == "BAD_INPUT"
    assert "cycle" in str(error.value)


def test_public_docs_state_the_reorder_limitation() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    known_bugs = (root / "docs" / "KNOWN_BUGS.md").read_text(encoding="utf-8")
    reference = (root / "docs" / "TOOL_REFERENCE.md").read_text(encoding="utf-8")

    assert "CAPABILITY_UNAVAILABLE" in known_bugs
    assert "move_track" in known_bugs
    assert "move_track" in reference


# ---------------------------------------------------------------------------
# Public surface - model validation and wrapper forwarding
# ---------------------------------------------------------------------------


def test_request_model_requires_exactly_one_colour_source() -> None:
    from pydantic import ValidationError

    from ableton_mcp_server import models

    with pytest.raises(ValidationError):
        models.SetTrackColorRequest(track_index=0)
    with pytest.raises(ValidationError):
        models.SetTrackColorRequest(track_index=0, color=1, color_index=1)
    with pytest.raises(ValidationError):
        models.SetTrackColorRequest(track_index=0, color_index=TRACK_COLOR_INDEX_MAX + 1)
    with pytest.raises(ValidationError):
        models.SetTrackColorRequest(track_index=0, color=0x1000000)

    assert models.SetTrackColorRequest(track_index=0, color_index=0).color is None


def test_server_wrapper_forwards_only_the_requested_colour_key() -> None:
    from unittest.mock import MagicMock, patch

    from ableton_mcp_server import server

    with patch("ableton_mcp_server.server.get_client") as get_client:
        get_client.return_value = MagicMock()
        get_client.return_value.call.return_value = {"forwarded": True}

        assert server.set_track_color(2, color_index=9) == {"forwarded": True}
        assert server.set_track_color(2, color=0x336699) == {"forwarded": True}

    calls = [call.args for call in get_client.return_value.call.call_args_list]
    assert calls == [
        ("set_track_color", {"track_index": 2, "color_index": 9}),
        ("set_track_color", {"track_index": 2, "color": 0x336699}),
    ]


def test_catalog_models_contracts_and_remote_script_stay_in_sync() -> None:
    from ableton_mcp_server.acceptance.probes import BASELINE_PROBE_GROUPS
    from ableton_mcp_server.catalog import TOOL_CATALOG
    from ableton_mcp_server.models import TOOL_REQUEST_MODELS
    from ableton_mcp_server.server import PUBLIC_TOOL_NAMES

    assert "set_track_color" in {spec.name for spec in TOOL_CATALOG}
    assert "set_track_color" in TOOL_REQUEST_MODELS
    assert "set_track_color" in PUBLIC_TOOL_NAMES
    assert "set_track_color" in ALLOWED_MUTATIONS
    assert "set_track_color" in BASELINE_PROBE_GROUPS["mutations"]


def test_track_count_is_unchanged_by_a_rejected_reorder() -> None:
    song = FakeSong()
    before = [track.name for track in song.tracks]

    with pytest.raises(RemoteError):
        call(song, "move_track", {"track_index": 0, "target_index": 1})

    assert [track.name for track in song.tracks] == before
