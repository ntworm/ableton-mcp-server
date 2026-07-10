from __future__ import annotations

import queue
from typing import Any

from AbletonMCPServer_RemoteScript import QueuedRequest, RequestProcessor
from tests.remote_fakes import BeatTime, FakeApplication, FakeCuePoint, FakeSong


def call_across_ticks(
    song: FakeSong,
    application: FakeApplication,
    command: str,
    params: dict[str, Any],
    *,
    max_ticks: int = 24,
) -> dict[str, Any]:
    processor = RequestProcessor(song, application)
    response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest(command, params, response_queue))
    for _tick in range(max_ticks):
        processor.process_pending(max_requests=1)
        if not response_queue.empty():
            return response_queue.get_nowait()
        song.tick()
    raise AssertionError(f"{command} did not finish within {max_ticks} ticks")


def test_create_renames_existing_custom_beat_time_without_toggling() -> None:
    song = FakeSong(deferred_writes=True)
    song.cue_points.append(FakeCuePoint("Old", BeatTime(8.0)))
    response = call_across_ticks(
        song, FakeApplication(), "create_cue_point", {"name": "Verse", "time": 8.0}
    )
    assert response == {
        "status": "ok",
        "result": {"name": "Verse", "time": 8.0, "action": "renamed"},
    }
    assert song.toggle_count == 0


def test_create_moves_both_cursors_verifies_toggle_and_restores_them() -> None:
    song = FakeSong(deferred_writes=True)
    song._current_song_time = 2.0
    song._start_time = 2.0
    app = FakeApplication()

    response = call_across_ticks(
        song, app, "create_cue_point", {"name": "Verse", "time": 8.0}
    )

    assert response == {
        "status": "ok",
        "result": {"name": "Verse", "time": 8.0, "action": "created"},
    }
    assert [(cue.name, float(cue.time)) for cue in song.cue_points] == [("Verse", 8.0)]
    assert song.current_song_time == 2.0
    assert song.start_time == 2.0
    assert song.toggle_count == 1
    assert (app.begin_count, app.end_count) == (1, 1)


def test_create_does_not_toggle_when_cursor_never_reaches_target() -> None:
    song = FakeSong(stuck_writes=99, deferred_writes=True)
    response = call_across_ticks(
        song, FakeApplication(), "create_cue_point", {"name": "Verse", "time": 8.0}
    )
    assert response["status"] == "error"
    assert response["code"] == "PLAYHEAD_NOT_MOVED"
    assert song.toggle_count == 0


def test_delete_verifies_absence_and_restores_both_cursors() -> None:
    song = FakeSong(deferred_writes=True)
    song._current_song_time = 2.0
    song._start_time = 2.0
    song.cue_points.append(FakeCuePoint("Verse", BeatTime(8.0)))
    response = call_across_ticks(song, FakeApplication(), "delete_cue_point", {"time": 8.0})
    assert response == {"status": "ok", "result": {"deleted": True, "time": 8.0}}
    assert song.cue_points == []
    assert song.current_song_time == 2.0
    assert song.start_time == 2.0


def test_bulk_runs_each_cue_operation_across_ticks_and_collects_errors() -> None:
    song = FakeSong(stuck_writes=2, deferred_writes=True)
    response = call_across_ticks(
        song,
        FakeApplication(),
        "bulk_create_cue_points",
        {"items": [{"name": "A", "time": 0.0}, {"name": "B", "time": 8.0}]},
    )
    assert response["status"] == "ok"
    assert [item["status"] for item in response["result"]["results"]] == ["ok", "ok"]
    assert [(cue.name, float(cue.time)) for cue in song.cue_points] == [("A", 0.0), ("B", 8.0)]
