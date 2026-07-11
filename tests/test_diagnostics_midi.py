from __future__ import annotations

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import (
    FakeApplication,
    FakeClip,
    FakeClipSlot,
    FakeNote,
    FakeSong,
)


def test_diagnose_midi_clip_empty() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot(None)]  # empty slot
    app = FakeApplication()

    res = execute_command(song, app, "diagnose_midi_clip", {"track_index": 0, "clip_index": 0})
    assert res["note_count"] == 0
    assert not res["has_overlaps"]
    assert "Clip slot is empty." in res["recommendations"]


def test_diagnose_midi_clip_overlaps() -> None:
    song = FakeSong()
    clip = FakeClip("Test Clip", midi=True)
    # Add two overlapping notes on pitch 60
    clip.notes = [
        FakeNote(60, 0.0, 1.0, 100),
        FakeNote(60, 0.5, 1.0, 100),  # starts before first note ends
    ]
    song.tracks[0].clip_slots = [FakeClipSlot(clip)]
    app = FakeApplication()

    res = execute_command(song, app, "diagnose_midi_clip", {"track_index": 0, "clip_index": 0})
    assert res["note_count"] == 2
    assert res["has_overlaps"]
    assert res["overlaps_count"] == 1
    assert any("overlapping" in r for r in res["recommendations"])


def test_diagnose_midi_clip_scale_and_drift() -> None:
    song = FakeSong()
    clip = FakeClip("Test Clip", midi=True)
    # Add notes: C (60) is in C Major, but C# (61) is not.
    # C# (61) has start time 1.07 which is drifted from 1.0.
    clip.notes = [
        FakeNote(60, 0.0, 1.0, 100),
        FakeNote(61, 1.07, 1.0, 100),
    ]
    song.tracks[0].clip_slots = [FakeClipSlot(clip)]
    app = FakeApplication()

    res = execute_command(
        song,
        app,
        "diagnose_midi_clip",
        {
            "track_index": 0,
            "clip_index": 0,
            "scale_root": "C",
            "scale_type": "major",
        },
    )
    assert res["note_count"] == 2
    assert len(res["notes_outside_scale"]) == 1
    assert res["notes_outside_scale"][0]["pitch"] == 61
    assert res["notes_outside_scale"][0]["note_name"] == "C#"
    assert res["timing_drift_detected"]
    assert any("outside the C major scale" in r for r in res["recommendations"])
    assert any("Timing drift detected" in r for r in res["recommendations"])
