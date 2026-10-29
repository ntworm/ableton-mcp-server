from __future__ import annotations

import queue
from collections.abc import Callable, Iterable
from typing import Any

from AbletonMCPServer_RemoteScript import QueuedRequest, RequestProcessor, execute_command
from tests.remote_fakes import FakeApplication, FakeClip, FakeClipSlot, FakeSong


def test_standalone_mutation_is_one_undo_step() -> None:
    app = FakeApplication()
    song = FakeSong()
    assert execute_command(song, app, "set_tempo", {"tempo": 128.0}) == {
        "tempo": 128.0,
        "resolved": {"kind": "tempo", "tempo": 128.0},
    }
    assert (app.begin_count, app.end_count) == (1, 1)


def test_dry_run_tempo_does_not_mutate_or_open_an_undo_step() -> None:
    app = FakeApplication()
    song = FakeSong()

    assert execute_command(song, app, "set_tempo", {"tempo": 128.0, "dry_run": True}) == {
        "tempo": 128.0,
        "committed": False,
        "resolved": {"kind": "tempo", "tempo": 128.0},
    }
    assert song.tempo == 120.0
    assert (app.begin_count, app.end_count) == (0, 0)


def test_batch_of_only_dry_runs_does_not_open_an_undo_step() -> None:
    app = FakeApplication()
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]

    result = execute_command(
        song,
        app,
        "run_batch",
        {
            "commands": [
                {"type": "set_tempo", "params": {"tempo": 128.0, "dry_run": True}},
                {
                    "type": "create_clip",
                    "params": {
                        "track_index": 0,
                        "clip_index": 0,
                        "length_beats": 4.0,
                        "dry_run": True,
                    },
                },
            ]
        },
    )

    assert result["completed"] == 2
    assert song.tempo == 120.0
    assert song.tracks[0].clip_slots[0].clip is None
    assert (app.begin_count, app.end_count) == (0, 0)


def test_batch_uses_one_outer_undo_and_aborts_with_successful_prefix_persisting() -> None:
    app = FakeApplication()
    song = FakeSong()
    result = execute_command(
        song,
        app,
        "run_batch",
        {
            "commands": [
                {"type": "set_tempo", "params": {"tempo": 128.0}},
                {
                    "type": "create_clip",
                    "params": {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
                },
                {"type": "set_loop", "params": {"enabled": True}},
            ]
        },
    )
    assert song.tempo == 128.0
    assert song.loop is False
    assert result["completed"] == 1
    assert result["aborted_at"] == 1
    assert result["rolled_back"] is False
    assert (app.begin_count, app.end_count) == (1, 1)


def test_batch_closes_undo_step_when_unexpected_handler_error_occurs() -> None:
    app = FakeApplication()
    song = FakeSong()
    result = execute_command(
        song,
        app,
        "run_batch",
        {"commands": [{"type": "set_tempo", "params": {}}]},
    )
    assert result["aborted_at"] == 0
    assert result["results"][0]["code"] == "INVALID_PARAMS"
    assert (app.begin_count, app.end_count) == (1, 1)


def test_batch_advances_deferred_children_with_one_outer_undo() -> None:
    song = FakeSong(deferred_writes=True)
    song.tracks[0].clip_slots = [FakeClipSlot()]
    app = FakeApplication()
    processor = RequestProcessor(song, app)
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(
        QueuedRequest(
            "run_batch",
            {
                "commands": [
                    {"type": "set_tempo", "params": {"tempo": 128.0}},
                    {"type": "set_loop", "params": {"enabled": True}},
                    {
                        "type": "create_clip",
                        "params": {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
                    },
                    {
                        "type": "create_clip",
                        "params": {"track_index": 0, "clip_index": 0, "length_beats": 4.0},
                    },
                    {"type": "set_tempo", "params": {"tempo": 130.0}},
                ]
            },
            response_queue,
        )
    )

    for _tick in range(12):
        processor.process_pending(max_requests=1)
        if not response_queue.empty():
            break
        assert (app.begin_count, app.end_count) == (1, 0)
        song.tick()

    response = response_queue.get_nowait()
    assert response["status"] == "ok"
    result = response["result"]
    assert result["completed"] == 3  # type: ignore[index]
    assert result["aborted_at"] == 3  # type: ignore[index]
    assert result["rolled_back"] is False  # type: ignore[index]
    assert result["results"][0]["result"] == {  # type: ignore[index]
        "tempo": 128.0,
        "resolved": {"kind": "tempo", "tempo": 128.0},
    }
    assert result["results"][1]["result"] == {"loop": True}  # type: ignore[index]
    assert song.tempo == 128.0
    assert song.loop is True
    assert song.tracks[0].clip_slots[0].has_clip is True
    assert (app.begin_count, app.end_count) == (1, 1)


class _LiveUndoHistory:
    """What Live records, measured on 12.4.15 and 12.4.25 against TESTE_CODEX.

    Live ends a Remote Script's undo step when each call into the script
    returns. ``Song.begin_undo_step()`` does not carry the step into the next
    ``update_display()`` tick, and the surface's ``handle_undo_steps`` does not
    change that. Within one tick Live groups every change, bracketed or not.
    """

    def __init__(self) -> None:
        self.steps: list[list[str]] = []
        self._tick: list[str] = []

    def record(self, change: str) -> None:
        self._tick.append(change)

    def callback_returned(self) -> None:
        if self._tick:
            self.steps.append(self._tick)
        self._tick = []


class _LaneClip(FakeClip):
    def __init__(self, name: str, start: float, length: float = 4.0) -> None:
        super().__init__(name=name, length=length)
        self.is_session_clip = False
        self.start_time = start
        self.end_time = start + length
        self.muted = False
        self.looping = False


class _RecordedSlot(FakeClipSlot):
    def __init__(self, history: _LiveUndoHistory) -> None:
        super().__init__()
        self._history = history

    def create_clip(self, length: float) -> None:
        super().create_clip(length)
        self._history.record("create clip")
        clip = self.clip
        assert clip is not None
        add_new_notes = clip.add_new_notes

        def recorded_add_new_notes(payload: Iterable[Any]) -> list[int]:
            self._history.record("add notes")
            return add_new_notes(payload)

        clip.add_new_notes = recorded_add_new_notes  # type: ignore[method-assign]


class _LiveSong(FakeSong):
    """Track 0 holds one Arrangement copy; edits and tempo writes land in Live's history.

    Live 12.4.25 lists an Arrangement edit in the tick that made it.
    ``late_lane`` stands for a host that lists it only on the next tick.
    """

    def __init__(self, *, late_lane: bool = False) -> None:
        super().__init__()
        self.history = _LiveUndoHistory()
        self._late_edits: list[Callable[[], None]] = []
        track = self.tracks[0]
        track.clip_slots.append(_RecordedSlot(self.history))
        lane = [_LaneClip("Copy", 0.0)]
        track.arrangement_clips = lane  # type: ignore[attr-defined]

        def edit(change: str, apply: Callable[[], None]) -> None:
            self.history.record(change)
            if late_lane:
                self._late_edits.append(apply)
            else:
                apply()

        def delete_clip(clip: _LaneClip) -> None:
            edit("delete %s@%s" % (clip.name, clip.start_time), lambda: lane.remove(clip))

        def duplicate_clip_to_arrangement(clip: FakeClip, time: float) -> None:
            placed = _LaneClip(clip.name, float(time), clip.length)
            edit("duplicate %s@%s" % (clip.name, float(time)), lambda: lane.append(placed))

        track.delete_clip = delete_clip  # type: ignore[attr-defined]
        track.duplicate_clip_to_arrangement = duplicate_clip_to_arrangement  # type: ignore[attr-defined]

    @property
    def tempo(self) -> float:
        return self._tempo

    @tempo.setter
    def tempo(self, value: float) -> None:
        self._tempo = float(value)
        self.history.record("tempo %s" % float(value))

    def tick(self) -> None:
        for apply in self._late_edits:
            apply()
        self._late_edits = []
        super().tick()

    def begin_undo_step(self) -> None:
        return None

    def end_undo_step(self) -> None:
        return None


def _run_in_live_ticks(song: _LiveSong, command: str, params: dict[str, Any]) -> dict[str, Any]:
    processor = RequestProcessor(song, FakeApplication(), song)
    response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest(command, params, response_queue))
    for _tick in range(40):
        processor.process_pending()
        song.history.callback_returned()
        song.tick()
        if not response_queue.empty():
            return response_queue.get_nowait()
    raise AssertionError("request did not finish")


REPLACE_COPY_COMMANDS: list[dict[str, Any]] = [
    {"type": "delete_arrangement_clip", "params": {"track_index": 0, "clip_index": 0}},
    {
        "type": "duplicate_session_clip_to_arrangement",
        "params": {"track_index": 0, "clip_index": 0, "time": 236.0},
    },
    {"type": "set_current_song_time", "params": {"time": 260.0}},
]


def test_run_batch_of_arrangement_edits_is_one_live_undo_step() -> None:
    # The 29/10/2026 batch needed two Ctrl+Z while each edit waited a tick to
    # read the lane back; confirmed in their own tick, one Ctrl+Z undoes both.
    song = _LiveSong()

    response = _run_in_live_ticks(song, "run_batch", {"commands": REPLACE_COPY_COMMANDS})

    assert response["result"]["completed"] == 3
    assert song.history.steps == [["delete Copy@0.0", "duplicate Clip@236.0"]]


def test_arrangement_edits_wait_a_tick_when_the_lane_lists_them_late() -> None:
    # The confirmation still holds on such a host; the edits then split.
    song = _LiveSong(late_lane=True)

    response = _run_in_live_ticks(song, "run_batch", {"commands": REPLACE_COPY_COMMANDS})

    assert response["result"]["completed"] == 3
    assert response["result"]["aborted_at"] is None
    assert song.history.steps == [["delete Copy@0.0"], ["duplicate Clip@236.0"]]


def test_a_command_read_back_on_a_later_tick_closes_the_undo_step() -> None:
    # set_tempo confirms its write a tick later, so the edit after it lands in
    # the next step: one Ctrl+Z per such command.
    song = _LiveSong()
    commands = [
        {"type": "set_tempo", "params": {"tempo": 128.0}},
        {"type": "delete_arrangement_clip", "params": {"track_index": 0, "clip_index": 0}},
    ]

    response = _run_in_live_ticks(song, "run_batch", {"commands": commands})

    assert response["result"]["completed"] == 2
    assert song.history.steps == [["tempo 128.0"], ["delete Copy@0.0"]]


def test_commands_that_finish_in_one_tick_share_one_live_undo_step() -> None:
    # music_generate_* and groove_apply rely on this: the clip and its notes
    # are written in the same tick, so one Ctrl+Z removes both.
    song = _LiveSong()
    target = {"track_index": 0, "clip_index": 1}
    commands = [
        {"type": "create_clip", "params": {**target, "length_beats": 4.0}},
        {
            "type": "add_notes_to_clip",
            "params": {
                **target,
                "notes": [{"pitch": 36, "start_time": 0.0, "duration": 0.25, "velocity": 100}],
            },
        },
    ]

    response = _run_in_live_ticks(song, "run_batch", {"commands": commands})

    assert response["result"]["completed"] == 2
    assert song.history.steps == [["create clip", "add notes"]]


def test_move_arrangement_clip_is_one_live_undo_step() -> None:
    # The original is deleted only after the copy is listed, in the same tick.
    song = _LiveSong()

    response = _run_in_live_ticks(
        song, "move_arrangement_clip", {"track_index": 0, "clip_index": 0, "time": 32.0}
    )

    assert response["status"] == "ok"
    assert song.history.steps == [["duplicate Copy@32.0", "delete Copy@0.0"]]
