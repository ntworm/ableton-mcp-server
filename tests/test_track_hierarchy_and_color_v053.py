"""Track hierarchy reads, verified colour writes, and the reorder capability.

Three surfaces are covered here:

1. ``get_track_list`` / ``get_track_state`` must report Live's grouping and
   colour properties, so a Group Track is recognisable without guessing from
   ``type``.
2. ``set_track_color`` must write exactly one colour property, verify it by
   reading it back, and never retry.
3. Moving an existing track has no supported entry point in the public LOM or
   the Ableton Extension SDK, so the bridge answers ``CAPABILITY_UNAVAILABLE``
   instead of pretending or improvising a destructive emulation.
"""

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


def call(song: FakeSong, command: str, params: dict[str, object] | None = None) -> Any:
    return execute_command(song, FakeApplication(), command, params or {})


# ---------------------------------------------------------------------------
# Part A — hierarchy reads
# ---------------------------------------------------------------------------


def test_group_track_is_reported_as_a_group_not_only_as_audio() -> None:
    song = grouped_song()
    tracks = call(song, "get_track_list")
    group = tracks[0]

    # Live gives a Group Track no MIDI input, so ``type`` is "audio" — that is
    # precisely why the boolean exists.
    assert group["name"] == "1 DRUMS"
    assert group["type"] == "audio"
    assert group["is_group_track"] is True
    assert group["is_grouped"] is False
    assert group["group_track_index"] is None
    assert group["group_track_id"] is None


def test_child_track_points_at_its_group_and_reports_hidden_when_folded() -> None:
    song = grouped_song()
    tracks = call(song, "get_track_list")
    child = tracks[1]

    assert child["is_grouped"] is True
    assert child["is_group_track"] is False
    assert child["group_track_index"] == 0
    assert child["group_track_id"] == "track:0"
    assert child["is_visible"] is False


def test_folded_and_open_group_report_distinct_fold_state() -> None:
    folded = grouped_song()
    assert call(folded, "get_track_list")[0]["fold_state"] == 1

    opened = grouped_song()
    opened.tracks[0].fold_state = 0
    opened.tracks[1].is_visible = True
    open_tracks = call(opened, "get_track_list")
    assert open_tracks[0]["fold_state"] == 0
    assert open_tracks[1]["is_visible"] is True


def test_ungrouped_track_reports_no_parent() -> None:
    song = grouped_song()
    loose = call(song, "get_track_list")[2]
    assert loose["is_grouped"] is False
    assert loose["is_group_track"] is False
    assert loose["group_track_index"] is None


def test_return_and_master_tracks_degrade_without_grouping_properties() -> None:
    """Return/master fakes omit the grouping properties, as some hosts do.

    The reads must report ``False``/``None`` rather than raising or inventing
    a group relationship.
    """

    song = grouped_song()
    tracks = call(song, "get_track_list")
    return_track = next(track for track in tracks if track["type"] == "return")
    master_track = next(track for track in tracks if track["type"] == "master")

    for track in (return_track, master_track):
        assert track["is_group_track"] is False
        assert track["is_grouped"] is False
        assert track["group_track_index"] is None
        assert track["fold_state"] is None
        # ``is_visible`` defaults to True: a return/master track is never
        # hidden inside a folded group.
        assert track["is_visible"] is True


def test_track_list_and_track_state_agree_on_colour() -> None:
    song = grouped_song()
    listed = call(song, "get_track_list")[2]
    state = call(song, "get_track_state", {"track_index": 2})

    assert listed["color"] == state["color"] == 0x336699
    assert listed["color_index"] == state["color_index"] == 7


def test_track_list_still_withholds_mixer_state() -> None:
    """Mixer fields belong to ``get_track_state`` only."""

    song = grouped_song()
    for track in call(song, "get_track_list"):
        assert not set(track) & {"mute", "solo", "arm", "volume", "sends"}


def test_color_index_is_none_when_the_host_does_not_expose_it() -> None:
    song = FakeSong()
    del song.tracks[0].color_index
    assert call(song, "get_track_list")[0]["color_index"] is None


# ---------------------------------------------------------------------------
# Part B — set_track_color
# ---------------------------------------------------------------------------


def test_set_track_color_writes_palette_index_and_returns_observed_value() -> None:
    song = FakeSong()
    result = call(song, "set_track_color", {"track_index": 0, "color_index": 12})

    assert song.tracks[0].color_index == 12
    assert result["property"] == "color_index"
    assert result["color_index"] == 12
    assert result["track_id"] == "track:0"
    assert result["track_index"] == 0
    assert result["resolved"] == {"kind": "track", "track_index": 0, "track_name": "Bass"}


def test_set_track_color_writes_packed_rgb() -> None:
    song = FakeSong()
    result = call(song, "set_track_color", {"track_index": 0, "color": 0xFF8800})

    assert song.tracks[0].color == 0xFF8800
    assert result["property"] == "color"
    assert result["color"] == 0xFF8800


def test_set_track_color_does_not_touch_clips() -> None:
    song = FakeSong()
    clip = song.tracks[0].clip_slots[0].clip
    assert clip is not None
    before = getattr(clip, "color", None)

    call(song, "set_track_color", {"track_index": 0, "color_index": 4})

    assert getattr(clip, "color", None) == before


def test_set_track_color_requires_exactly_one_colour_source() -> None:
    song = FakeSong()
    with pytest.raises(RemoteError) as neither:
        call(song, "set_track_color", {"track_index": 0})
    assert neither.value.code == "INVALID_PARAMS"

    with pytest.raises(RemoteError) as both:
        call(song, "set_track_color", {"track_index": 0, "color": 1, "color_index": 1})
    assert both.value.code == "INVALID_PARAMS"


@pytest.mark.parametrize(
    "params",
    [
        {"track_index": 0, "color_index": -1},
        {"track_index": 0, "color_index": TRACK_COLOR_INDEX_MAX + 1},
        {"track_index": 0, "color": -1},
        {"track_index": 0, "color": 0x1000000},
    ],
)
def test_set_track_color_rejects_out_of_range_values(params: dict[str, Any]) -> None:
    song = FakeSong()
    original_index = song.tracks[0].color_index
    original_color = song.tracks[0].color

    with pytest.raises(RemoteError) as error:
        call(song, "set_track_color", params)

    assert error.value.code == "BAD_INPUT"
    assert song.tracks[0].color_index == original_index
    assert song.tracks[0].color == original_color


def test_set_track_color_rejects_non_integer_and_boolean_values() -> None:
    song = FakeSong()
    for value in ("12", 12.5, True):
        with pytest.raises(RemoteError) as error:
            call(song, "set_track_color", {"track_index": 0, "color_index": value})
        assert error.value.code == "INVALID_PARAMS"


def test_set_track_color_rejects_an_out_of_range_track_index() -> None:
    song = FakeSong()
    with pytest.raises(RemoteError) as error:
        call(song, "set_track_color", {"track_index": 99, "color_index": 1})
    assert error.value.code == "INVALID_PARAMS"


def test_set_track_color_reaches_return_and_master_tracks() -> None:
    """Return and master expose ``color``/``color_index`` in the LOM."""

    song = FakeSong()
    return_index = len(song.tracks)
    master_index = return_index + 1

    assert (
        call(song, "set_track_color", {"track_index": return_index, "color_index": 9})[
            "color_index"
        ]
        == 9
    )
    assert (
        call(song, "set_track_color", {"track_index": master_index, "color": 0x112233})["color"]
        == 0x112233
    )


def test_set_track_color_returns_wrong_type_when_property_is_absent() -> None:
    song = FakeSong()
    del song.tracks[0].color_index

    with pytest.raises(RemoteError) as error:
        call(song, "set_track_color", {"track_index": 0, "color_index": 3})

    assert error.value.code == "WRONG_TYPE"


def test_set_track_color_fails_verification_instead_of_retrying() -> None:
    """A host that swallows the write must surface, not be written to twice."""

    class StubbornTrack(FakeTrack):
        write_attempts = 0

        def __init__(self) -> None:
            super().__init__("Stubborn")

        @property  # type: ignore[misc]
        def color_index(self) -> int:
            return 0

        @color_index.setter
        def color_index(self, _value: int) -> None:
            self.write_attempts += 1

    song = FakeSong()
    track = StubbornTrack()
    # ``FakeTrack.__init__`` assigns the default colour; only the writes the
    # handler performs are interesting.
    track.write_attempts = 0
    song.tracks = [track]

    with pytest.raises(RemoteError) as error:
        call(song, "set_track_color", {"track_index": 0, "color_index": 5})

    assert error.value.code == "VERIFICATION_FAILED"
    assert track.write_attempts == 1


def test_set_track_color_is_an_allowed_single_undo_mutation() -> None:
    song = FakeSong()
    application = FakeApplication()

    execute_command(song, application, "set_track_color", {"track_index": 0, "color_index": 2})

    assert "set_track_color" in ALLOWED_MUTATIONS
    assert application.begin_count == 1
    assert application.end_count == 1


# ---------------------------------------------------------------------------
# Part C — track reordering is not available
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

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert "not exposed by the public Live Object Model" in str(error.value)
    assert error.value.hint is not None
    details = error.value.details
    assert details is not None
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
        # Target is not foldable → WRONG_TYPE wins over the cycle rule.
        ("move_track_to_group", {"track_index": 2, "group_track_index": 2}, "WRONG_TYPE"),
        # Target is foldable and is the track itself → cycle rule fires.
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
# Public surface — model validation and wrapper forwarding
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
