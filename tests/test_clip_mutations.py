from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeClipSlot, FakeSong


def test_create_clip_requires_empty_midi_slot_and_returns_clip_path() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]
    result = execute_command(
        song,
        FakeApplication(),
        "create_clip",
        {"track_index": 0, "clip_index": 0, "length_beats": 8.0},
    )
    assert result == {
        "created": True,
        "clip_id": "track:0/clipslot:0/clip",
        "length_beats": 8.0,
    }


def test_create_clip_rejects_occupied_slot() -> None:
    with pytest.raises(RemoteError) as exc_info:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "create_clip",
            {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
        )
    assert exc_info.value.code == "BAD_INPUT"


def test_fire_clip_and_add_notes_use_python_remote_script_lom_types() -> None:
    song = FakeSong()
    app = FakeApplication()
    fired = execute_command(song, app, "fire_clip", {"track_index": 0, "clip_index": 0})
    assert fired == {"fired": True, "clip_id": "track:0/clipslot:0/clip"}
    slot = song.tracks[0].clip_slots[0]
    assert slot.fire_count == 1

    added = execute_command(
        song,
        app,
        "add_notes_to_clip",
        {
            "track_index": 0,
            "clip_index": 0,
            "notes": [{"pitch": 64, "start_time": 1.0, "duration": 0.5, "velocity": 90}],
        },
    )
    assert added["added"] == 1
    assert slot.clip is not None
    assert len(slot.clip.add_payloads) == 1
    specifications = slot.clip.add_payloads[0]
    assert len(specifications) == 1
    specification = specifications[0]
    assert specification.pitch == 64
    assert specification.start_time == 1.0
    assert specification.duration == 0.5
    assert specification.velocity == 90
    assert specification.mute is False
