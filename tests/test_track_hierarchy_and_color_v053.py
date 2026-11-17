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
    ALLOWED_MUTATIONS,
    TRACK_COLOR_INDEX_MAX,
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


def __getattr__(name: str) -> Any:
    """Expose the tests moved to ``test_track_hierarchy_and_color_v053_part2``.

    The lookup is lazy so the two modules never import each other while
    they load, and so pytest does not collect the same test twice.
    """
    from . import test_track_hierarchy_and_color_v053_part2 as _part2

    return getattr(_part2, name)
