from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeClip, FakeClipSlot, FakeSong, FakeTrack


def test_get_composition_structure() -> None:
    song = FakeSong()
    # Add a second track with clip slot
    track2 = FakeTrack("Lead")
    track2.clip_slots = [FakeClipSlot(FakeClip("Synth", midi=True))]
    song.tracks.append(track2)

    app = FakeApplication()
    res = execute_command(song, app, "get_composition_structure", {})
    assert res["track_count"] == 4  # Bass + Return A + Master + Lead
    assert len(res["tracks"]) == 4
    assert res["scenes_count"] == 1
    assert res["unnamed_tracks_count"] == 1  # Master has default name
    assert (
        "track:3" in res["unnamed_tracks"]
    )  # Master is track:3 (Bass:0, Return A:1, Lead:2, Master:3)


def test_create_midi_track_guarded() -> None:
    song = FakeSong()
    app = FakeApplication()

    # Track limit is 96. Let's verify we can create a track under limit.
    res = execute_command(song, app, "create_midi_track", {"name": "Arp"})
    assert res["status"] == "created"
    assert res["name"] == "Arp"
    assert len(song.tracks) == 2  # Bass + Arp

    # Set track list to 96 tracks to trigger limit error
    song.tracks = [FakeTrack(f"Track {i}") for i in range(96)]
    from AbletonMCPServer_RemoteScript import RemoteError

    with pytest.raises(RemoteError) as exc_info:
        execute_command(song, app, "create_midi_track", {"name": "Too Many"})
    assert exc_info.value.code == "TRACK_LIMIT_REACHED"


def test_rename_track() -> None:
    song = FakeSong()
    app = FakeApplication()

    res = execute_command(song, app, "rename_track", {"track_index": 0, "new_name": "Sub Bass"})
    assert res["track_id"] == "track:0"
    assert res["old_name"] == "Bass"
    assert res["new_name"] == "Sub Bass"
    assert song.tracks[0].name == "Sub Bass"
