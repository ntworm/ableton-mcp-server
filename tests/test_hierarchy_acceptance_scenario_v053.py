"""The mandatory hierarchy acceptance scenario, executed end to end.

The scenario asks for a Set with ``@ PADS``, ``@ PADS 2`` (with children), a
piano group and a loose ``> PIANO`` track, then for the children of
``@ PADS 2`` to be moved into ``@ PADS`` and the piano tracks to be gathered
into one group.

Every step runs through the real command dispatcher. The moves are refused —
Live's public API has no operation that performs them — and this module pins
down what that refusal must guarantee: nothing deleted, nothing renamed, no
clip, device, note or automation touched, and the track order unchanged.

The Set is built from fakes rather than a real ``.als`` because the same API
gap makes the Set itself unbuildable over MCP: there is no LOM call that
creates a Group Track either.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import (
    FakeApplication,
    FakeAutomationEnvelope,
    FakeClip,
    FakeClipSlot,
    FakeDevice,
    FakeNote,
    FakeSong,
    FakeTrack,
)


def call(song: FakeSong, command: str, params: dict[str, object] | None = None) -> Any:
    return execute_command(song, FakeApplication(), command, params or {})


def scenario_song() -> FakeSong:
    """Build the Set described by the acceptance case.

    Index layout (regular tracks):

    0 ``@ PADS``        group, empty
    1 ``@ PADS 2``      group, holds 2 and 3
    2 ``Pad Warm``      child of 1, one clip with notes and a device
    3 ``Pad Bright``    child of 1, one clip with notes and a device
    4 ``@ PIANO GRP``   group, holds 5
    5 ``Piano Body``    child of 4
    6 ``> PIANO``       loose, not grouped
    """

    song = FakeSong()
    pads = FakeTrack("@ PADS", midi=False, is_foldable=True, color_index=1)
    pads_two = FakeTrack("@ PADS 2", midi=False, is_foldable=True, color_index=2)
    piano_group = FakeTrack("@ PIANO GRP", midi=False, is_foldable=True, color_index=3)

    def child(name: str, parent: FakeTrack, pitch: int) -> FakeTrack:
        clip = FakeClip(name=f"{name} Clip")
        clip.notes = [FakeNote(pitch, 0.0, 1.0, 100), FakeNote(pitch + 7, 1.0, 1.0, 90)]
        # An automation envelope on the clip, so "automations preserved" is
        # checked against something that actually exists.
        envelope = FakeAutomationEnvelope()
        envelope.insert_step(0.0, 1.0, 0.5)
        track = FakeTrack(name, midi=True, group_track=parent, clip_slots=[FakeClipSlot(clip)])
        clip._automation_envelopes[track.mixer_device.volume] = envelope  # noqa: SLF001
        clip.has_envelopes = True
        track.devices = [FakeDevice("Operator"), FakeDevice("Reverb")]
        return track

    warm = child("Pad Warm", pads_two, 60)
    bright = child("Pad Bright", pads_two, 64)
    piano_body = child("Piano Body", piano_group, 48)
    loose_piano = FakeTrack("> PIANO", midi=True, color_index=9)

    song.tracks = [pads, pads_two, warm, bright, piano_group, piano_body, loose_piano]
    return song


def full_state(song: FakeSong) -> list[dict[str, Any]]:
    """Snapshot everything the operation is required to preserve."""

    state: list[dict[str, Any]] = []
    for index, track in enumerate(song.tracks):
        mixer = track.mixer_device
        clips: list[dict[str, Any]] = []
        for slot in track.clip_slots:
            clip = slot.clip
            if clip is None:
                clips.append({"empty": True})
                continue
            clips.append(
                {
                    "name": clip.name,
                    "color": clip.color,
                    "color_index": clip.color_index,
                    "length": clip.length,
                    "loop_start": clip.loop_start,
                    "loop_end": clip.loop_end,
                    "notes": [
                        (note.pitch, note.start_time, note.duration, note.velocity, note.mute)
                        for note in clip.notes
                    ],
                    "has_envelopes": clip.has_envelopes,
                    "envelope_steps": [
                        list(envelope.steps) for envelope in clip._automation_envelopes.values()
                    ],
                }
            )
        state.append(
            {
                "index": index,
                "name": track.name,
                "devices": [device.name for device in track.devices],
                "clips": clips,
                "volume": mixer.volume.value,
                "panning": mixer.panning.value,
                "sends": [send.value for send in mixer.sends],
                "mute": track.mute,
                "solo": track.solo,
                "arm": track.arm,
                "input_routing": track.input_routing_type.display_name,
                "output_routing": track.output_routing_type.display_name,
                "color": track.color,
                "color_index": track.color_index,
                "fold_state": track.fold_state,
                "is_grouped": track.is_grouped,
                "is_foldable": track.is_foldable,
                "group": None if track.group_track is None else track.group_track.name,
            }
        )
    return state


def test_scenario_set_is_shaped_as_the_acceptance_case_requires() -> None:
    song = scenario_song()
    tracks = call(song, "get_track_list")

    by_name = {track["name"]: track for track in tracks}
    assert by_name["@ PADS"]["is_group_track"] is True
    assert by_name["@ PADS 2"]["is_group_track"] is True
    assert by_name["@ PIANO GRP"]["is_group_track"] is True
    assert by_name["Pad Warm"]["group_track_id"] == "track:1"
    assert by_name["Pad Bright"]["group_track_id"] == "track:1"
    assert by_name["Piano Body"]["group_track_id"] == "track:4"
    assert by_name["> PIANO"]["is_grouped"] is False


def test_moving_pads_2_children_into_pads_is_refused_and_changes_nothing() -> None:
    """Steps 1-3 and 5-7 of the acceptance case."""

    song = scenario_song()
    before_state = copy.deepcopy(full_state(song))
    before_list = call(song, "get_track_list")

    for child_index in (2, 3):
        with pytest.raises(RemoteError) as error:
            call(
                song,
                "move_track_to_group",
                {"track_index": child_index, "group_track_index": 0},
            )
        assert error.value.code == "CAPABILITY_UNAVAILABLE"
        assert error.value.details is not None
        assert error.value.details["applied"] is False

    # Step 2: @ PADS 2 still exists — nothing is ever deleted.
    assert [track.name for track in song.tracks].count("@ PADS 2") == 1
    # Step 3: every child still reports its original parent.
    after_list = call(song, "get_track_list")
    assert {track["name"]: track["group_track_id"] for track in after_list} == {
        track["name"]: track["group_track_id"] for track in before_list
    }
    # Steps 5 and 7: clips, devices, notes, automation, names, mixer, routing
    # and colours are byte-identical; the diff is empty.
    assert full_state(song) == before_state
    # Step 6: the order is unchanged.
    assert [track["index"] for track in after_list] == [track["index"] for track in before_list]
    assert [track["name"] for track in after_list] == [track["name"] for track in before_list]


def test_gathering_the_piano_tracks_into_one_group_is_refused() -> None:
    """Step 4: > PIANO into the piano group, and merging the two groups."""

    song = scenario_song()
    before_state = copy.deepcopy(full_state(song))

    with pytest.raises(RemoteError) as move_error:
        call(song, "move_track_to_group", {"track_index": 6, "group_track_index": 4})
    assert move_error.value.code == "CAPABILITY_UNAVAILABLE"

    with pytest.raises(RemoteError) as merge_error:
        call(song, "merge_groups", {"source_group_index": 1, "destination_group_index": 4})
    assert merge_error.value.code == "CAPABILITY_UNAVAILABLE"

    assert full_state(song) == before_state


def test_reordering_the_scenario_set_is_refused_and_order_is_stable() -> None:
    song = scenario_song()
    before = [track["index"] for track in call(song, "get_track_list")]

    with pytest.raises(RemoteError) as error:
        call(song, "reorder_tracks", {"order": [6, 5, 4, 3, 2, 1, 0]})
    assert error.value.code == "CAPABILITY_UNAVAILABLE"

    assert [track["index"] for track in call(song, "get_track_list")] == before


def test_ungrouping_a_pad_is_refused_without_deleting_the_group() -> None:
    song = scenario_song()
    before_state = copy.deepcopy(full_state(song))

    with pytest.raises(RemoteError) as error:
        call(song, "ungroup_track", {"track_index": 2})

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert full_state(song) == before_state


def test_what_the_scenario_can_actually_do_over_mcp() -> None:
    """The supported half of the acceptance case: rename and recolour.

    Track and clip colours and names are writable, so the parts of the
    scenario that do not require moving a track succeed and are verified by
    readback.
    """

    song = scenario_song()

    assert call(song, "set_track_color", {"track_index": 0, "color_index": 26})["color_index"] == 26
    assert call(song, "rename_track", {"track_index": 0, "new_name": "@ PADS ALL"})["new_name"] == (
        "@ PADS ALL"
    )
    clip_result = call(
        song, "set_clip_color", {"track_index": 2, "clip_index": 0, "color_index": 5}
    )
    assert clip_result["color_index"] == 5

    # The recolour touched exactly one clip and left its notes alone.
    warm_clip = song.tracks[2].clip_slots[0].clip
    bright_clip = song.tracks[3].clip_slots[0].clip
    assert warm_clip is not None and bright_clip is not None
    assert warm_clip.color_index == 5
    assert bright_clip.color_index == 0
    assert [note.pitch for note in warm_clip.notes] == [60, 67]


def test_scenario_diagnostic_lists_every_clip_target() -> None:
    song = scenario_song()
    report = call(song, "diagnose_clip_targets", {})

    # Four child/loose tracks carry one clip each; the three groups carry the
    # default FakeTrack slot, and the return/master pair carry none.
    assert report["session_clip_count"] >= 4
    named = {clip["name"] for track in report["tracks"] for clip in track["session_clips"]}
    assert {"Pad Warm Clip", "Pad Bright Clip", "Piano Body Clip"} <= named
