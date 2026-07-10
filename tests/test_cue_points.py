from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import PlayheadNotMovedError, execute_command
from tests.remote_fakes import BeatTime, FakeApplication, FakeCuePoint, FakeSong


def test_create_renames_existing_custom_beat_time_without_toggling() -> None:
    song = FakeSong()
    song.cue_points.append(FakeCuePoint("Old", BeatTime(8.0)))
    result = execute_command(
        song, FakeApplication(), "create_cue_point", {"name": "Verse", "time": 8.0}
    )
    assert result == {"name": "Verse", "time": 8.0, "action": "renamed"}
    assert song.toggle_count == 0


def test_create_toggles_only_after_playhead_verification() -> None:
    song = FakeSong(stuck_writes=99)
    with pytest.raises(PlayheadNotMovedError):
        execute_command(song, FakeApplication(), "create_cue_point", {"name": "Verse", "time": 8.0})
    assert song.toggle_count == 0


def test_create_and_delete_use_move_toggle_and_restore_previous_time() -> None:
    song = FakeSong()
    song._current_song_time = 2.0
    app = FakeApplication()
    created = execute_command(song, app, "create_cue_point", {"name": "Verse", "time": 8.0})
    assert created == {"name": "Verse", "time": 8.0, "action": "created"}
    assert song.current_song_time == 2.0
    deleted = execute_command(song, app, "delete_cue_point", {"time": 8.0})
    assert deleted == {"deleted": True, "time": 8.0}
    assert song.current_song_time == 2.0


def test_bulk_delegates_and_collects_item_errors() -> None:
    song = FakeSong(stuck_writes=99)
    result = execute_command(
        song,
        FakeApplication(),
        "bulk_create_cue_points",
        {"items": [{"name": "A", "time": 0.0}, {"name": "B", "time": 8.0}]},
    )
    assert result["results"][0]["status"] == "ok"
    assert result["results"][1]["status"] == "error"
    assert result["results"][1]["code"] == "PLAYHEAD_NOT_MOVED"
