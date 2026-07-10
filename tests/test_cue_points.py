from __future__ import annotations

import queue
from typing import Any

from AbletonMCPServer_RemoteScript import QueuedRequest, RequestProcessor
from tests.remote_fakes import BeatTime, FakeApplication, FakeCuePoint, FakeSong


class LaggyCuePoint:
    def __init__(self, time: float, *, rename_delay_ticks: int) -> None:
        self._name = "1"
        self._pending_name: str | None = None
        self._rename_ticks = rename_delay_ticks
        self.time = BeatTime(time)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if self._pending_name != value:
            self._pending_name = value

    def tick(self) -> None:
        if self._pending_name is None:
            return
        self._rename_ticks -= 1
        if self._rename_ticks <= 0:
            self._name = self._pending_name
            self._pending_name = None


class DroppedRenameCuePoint:
    def __init__(self, name: str, time: float, *, dropped_writes: int) -> None:
        self._name = name
        self.time = BeatTime(time)
        self.dropped_writes = dropped_writes
        self.write_count = 0

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self.write_count += 1
        if self.write_count > self.dropped_writes:
            self._name = value


class LaggyCueSong(FakeSong):
    def __init__(self, *, toggle_delay_ticks: int, rename_delay_ticks: int) -> None:
        super().__init__(deferred_writes=True)
        self._toggle_delay_ticks = toggle_delay_ticks
        self._rename_delay_ticks = rename_delay_ticks
        self._pending_toggle_ticks: int | None = None

    def set_or_delete_cue(self) -> None:
        self.toggle_count += 1
        self._pending_toggle_ticks = self._toggle_delay_ticks

    def tick(self) -> None:
        super().tick()
        for cue in self.cue_points:
            if isinstance(cue, LaggyCuePoint):
                cue.tick()
        if self._pending_toggle_ticks is None:
            return
        self._pending_toggle_ticks -= 1
        if self._pending_toggle_ticks <= 0:
            existing = next(
                (
                    cue
                    for cue in self.cue_points
                    if abs(float(cue.time) - self.start_time) < 0.01
                ),
                None,
            )
            if existing is None:
                self.cue_points.append(
                    LaggyCuePoint(
                        self.start_time,
                        rename_delay_ticks=self._rename_delay_ticks,
                    )
                )
            else:
                self.cue_points.remove(existing)
            self._pending_toggle_ticks = None


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


def test_existing_cue_rename_retries_dropped_idempotent_writes() -> None:
    song = FakeSong(deferred_writes=True)
    cue = DroppedRenameCuePoint("Old", 8.0, dropped_writes=3)
    song.cue_points.append(cue)  # type: ignore[arg-type]

    response = call_across_ticks(
        song,
        FakeApplication(),
        "create_cue_point",
        {"name": "Verse", "time": 8.0},
        max_ticks=24,
    )

    assert response == {
        "status": "ok",
        "result": {"name": "Verse", "time": 8.0, "action": "renamed"},
    }
    assert cue.name == "Verse"
    assert cue.write_count == 4
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


def test_create_holds_target_until_laggy_toggle_and_rename_are_observed() -> None:
    song = LaggyCueSong(toggle_delay_ticks=4, rename_delay_ticks=4)
    song._current_song_time = 2.0
    song._start_time = 2.0

    response = call_across_ticks(
        song,
        FakeApplication(),
        "create_cue_point",
        {"name": "Verse", "time": 8.0},
        max_ticks=40,
    )

    assert response == {
        "status": "ok",
        "result": {"name": "Verse", "time": 8.0, "action": "created"},
    }
    assert [(cue.name, float(cue.time)) for cue in song.cue_points] == [("Verse", 8.0)]
    assert song.current_song_time == 2.0
    assert song.start_time == 2.0


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


def test_delete_waits_for_laggy_toggle_before_restoring_cursors() -> None:
    song = LaggyCueSong(toggle_delay_ticks=4, rename_delay_ticks=0)
    song._current_song_time = 2.0
    song._start_time = 2.0
    song.cue_points.append(LaggyCuePoint(8.0, rename_delay_ticks=0))

    response = call_across_ticks(
        song,
        FakeApplication(),
        "delete_cue_point",
        {"time": 8.0},
        max_ticks=24,
    )

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


def test_bulk_restores_cursors_once_instead_of_between_every_item() -> None:
    song = FakeSong(deferred_writes=True)
    items = [{"name": f"M{index}", "time": float(index * 8)} for index in range(5)]

    response = call_across_ticks(
        song,
        FakeApplication(),
        "bulk_create_cue_points",
        {"items": items},
        max_ticks=80,
    )

    assert response["status"] == "ok"
    assert [item["status"] for item in response["result"]["results"]] == ["ok"] * 5
    assert song.transport_write_attempts <= 6
    assert song.current_song_time == 0.0
    assert song.start_time == 0.0
