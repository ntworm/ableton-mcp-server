"""Arrangement timeline: read placement, place, move, delete.

The Session grid and the Arrangement lane are different objects in the LOM.
``Track.arrangement_clips`` is a plain list — there is no setter for
``Clip.start_time`` — so placement happens through
``Track.duplicate_clip_to_arrangement`` and movement is a verified copy
followed by a delete.
"""

from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeClip, FakeSong


class ArrangementClip(FakeClip):
    def __init__(self, name: str, start: float, length: float = 4.0) -> None:
        super().__init__(name=name, length=length)
        self.is_session_clip = False
        self.start_time = start
        self.end_time = start + length
        self.muted = False
        self.looping = False


def _track_with_lane(song: FakeSong, clips: list[ArrangementClip]) -> None:
    """Give track 0 an Arrangement lane and the two methods Live exposes."""

    track = song.tracks[0]
    track.arrangement_clips = clips

    def duplicate_clip_to_arrangement(clip: object, time: float) -> None:
        length = float(getattr(clip, "length", 4.0))
        track.arrangement_clips.append(
            ArrangementClip(str(getattr(clip, "name", "Clip")), time, length)
        )

    def delete_clip(clip: object) -> None:
        track.arrangement_clips.remove(clip)

    track.duplicate_clip_to_arrangement = duplicate_clip_to_arrangement
    track.delete_clip = delete_clip


def test_get_arrangement_clips_reports_placement_sorted_by_start() -> None:
    song = FakeSong()
    _track_with_lane(song, [ArrangementClip("late", 32.0), ArrangementClip("early", 8.0, 16.0)])

    result = execute_command(song, FakeApplication(), "get_arrangement_clips", {"track_index": 0})

    assert result["clip_count"] == 2
    assert [clip["name"] for clip in result["clips"]] == ["early", "late"]
    first = result["clips"][0]
    assert (first["start_time"], first["end_time"], first["length_beats"]) == (8.0, 24.0, 16.0)
    # The listing is sorted by position, but clip_index stays the real handle
    # into Track.arrangement_clips — delete and move address that index, not
    # the display order.
    assert first["id"] == "track:0/arrangementclip:1"
    assert first["clip_index"] == 1


def test_get_arrangement_clips_refuses_a_host_without_the_lane() -> None:
    song = FakeSong()  # FakeTrack has no arrangement_clips by default

    with pytest.raises(RemoteError) as error:
        execute_command(song, FakeApplication(), "get_arrangement_clips", {"track_index": 0})

    assert error.value.code == "CAPABILITY_UNAVAILABLE"


def test_duplicate_session_clip_to_arrangement_places_and_keeps_the_source() -> None:
    song = FakeSong()
    _track_with_lane(song, [])
    source = song.tracks[0].clip_slots[0].clip

    result = execute_command(
        song,
        FakeApplication(),
        "duplicate_session_clip_to_arrangement",
        {"track_index": 0, "clip_index": 0, "time": 468.0},
    )

    assert result["placed"] is True
    assert result["arrangement_clip"]["start_time"] == 468.0
    assert result["clip_count"] == 1
    # the Session clip is a reusable source, not a donor
    assert song.tracks[0].clip_slots[0].clip is source


def test_duplicate_session_clip_to_arrangement_rejects_an_empty_slot() -> None:
    song = FakeSong()
    _track_with_lane(song, [])
    song.tracks[0].clip_slots[0].clip = None

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "duplicate_session_clip_to_arrangement",
            {"track_index": 0, "clip_index": 0, "time": 4.0},
        )

    assert error.value.code == "BAD_INPUT"


def test_move_arrangement_clip_leaves_one_clip_at_the_destination() -> None:
    song = FakeSong()
    _track_with_lane(song, [ArrangementClip("solo", 16.0)])

    result = execute_command(
        song,
        FakeApplication(),
        "move_arrangement_clip",
        {"track_index": 0, "clip_index": 0, "time": 96.0},
    )

    assert result["moved"] is True
    assert result["from_time"] == 16.0
    assert result["arrangement_clip"]["start_time"] == 96.0
    assert [clip.start_time for clip in song.tracks[0].arrangement_clips] == [96.0]


def test_delete_arrangement_clip_removes_only_the_named_index() -> None:
    song = FakeSong()
    _track_with_lane(song, [ArrangementClip("keep", 0.0), ArrangementClip("drop", 64.0)])

    result = execute_command(
        song,
        FakeApplication(),
        "delete_arrangement_clip",
        {"track_index": 0, "clip_index": 1},
    )

    assert result["deleted"] is True
    assert result["clip"]["name"] == "drop"
    assert [clip.name for clip in song.tracks[0].arrangement_clips] == ["keep"]


def test_delete_arrangement_clip_rejects_an_index_that_does_not_exist() -> None:
    song = FakeSong()
    _track_with_lane(song, [ArrangementClip("only", 0.0)])

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "delete_arrangement_clip",
            {"track_index": 0, "clip_index": 4},
        )

    assert error.value.code == "INVALID_PARAMS"
