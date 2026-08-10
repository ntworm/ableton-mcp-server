from __future__ import annotations

import queue

from AbletonMCPServer_RemoteScript import QueuedRequest, RequestProcessor, execute_command
from tests.remote_fakes import FakeApplication, FakeClipSlot, FakeSong


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
