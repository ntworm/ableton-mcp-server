from __future__ import annotations

import queue

from AbletonMCPServer_RemoteScript import (
    PLAYHEAD_MOVE_RETRIES,
    QueuedRequest,
    RequestProcessor,
)
from tests.remote_fakes import FakeApplication, FakeSong


def test_request_waits_until_main_thread_processor_drains_queue() -> None:
    song = FakeSong()
    app = FakeApplication()
    processor = RequestProcessor(song, app)
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest("get_session_info", {}, response_queue))
    assert response_queue.empty()

    assert processor.process_pending(max_requests=1) == 1
    response = response_queue.get_nowait()
    assert response["status"] == "ok"
    assert response["result"]["tempo"] == 120.0  # type: ignore[index]


def test_processor_returns_typed_error_envelope_without_throwing_to_socket() -> None:
    processor = RequestProcessor(FakeSong(), FakeApplication())
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest("delete_track", {}, response_queue))
    processor.process_pending(max_requests=1)
    response = response_queue.get_nowait()
    assert response["status"] == "error"
    assert response["code"] == "READ_ONLY_VIOLATION"


def test_deferred_transport_write_completes_on_later_ui_tick() -> None:
    song = FakeSong(deferred_writes=True)
    app = FakeApplication()
    processor = RequestProcessor(song, app)
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest("set_current_song_time", {"time": 8.0}, response_queue))

    processor.process_pending(max_requests=1)
    assert response_queue.empty()
    assert song.current_song_time == 0.0
    assert (app.begin_count, app.end_count) == (1, 0)

    song.tick()
    processor.process_pending(max_requests=1)
    response = response_queue.get_nowait()
    assert response == {"status": "ok", "result": {"current_song_time": 8.0}}
    assert (app.begin_count, app.end_count) == (1, 1)


def test_deferred_boolean_mutations_return_confirmed_state() -> None:
    song = FakeSong(deferred_writes=True)
    app = FakeApplication()
    processor = RequestProcessor(song, app)

    for command, params, expected in (
        ("start_playback", {}, {"is_playing": True}),
        ("stop_playback", {}, {"is_playing": False}),
        ("set_loop", {"enabled": True}, {"loop": True}),
    ):
        response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        processor.enqueue(QueuedRequest(command, params, response_queue))
        processor.process_pending(max_requests=1)
        assert response_queue.empty()
        song.tick()
        processor.process_pending(max_requests=1)
        assert response_queue.get_nowait() == {"status": "ok", "result": expected}

    assert (app.begin_count, app.end_count) == (3, 3)


def test_all_numeric_transport_writes_wait_for_observed_state() -> None:
    song = FakeSong(deferred_writes=True)
    processor = RequestProcessor(song, FakeApplication())

    for command, params, expected in (
        (
            "set_tempo",
            {"tempo": 128.0},
            {"tempo": 128.0, "resolved": {"kind": "tempo", "tempo": 128.0}},
        ),
        ("set_loop_start", {"start_beat": 4.0}, {"loop_start": 4.0}),
        ("set_loop_length", {"length_beats": 8.0}, {"loop_length": 8.0}),
    ):
        response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        processor.enqueue(QueuedRequest(command, params, response_queue))
        processor.process_pending(max_requests=1)
        assert response_queue.empty()
        song.tick()
        processor.process_pending(max_requests=1)
        assert response_queue.get_nowait() == {"status": "ok", "result": expected}


def test_playhead_failure_is_reported_only_after_tick_retries() -> None:
    song = FakeSong(stuck_writes=99, deferred_writes=True)
    app = FakeApplication()
    processor = RequestProcessor(song, app)
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest("set_current_song_time", {"time": 8.0}, response_queue))

    for _attempt in range(PLAYHEAD_MOVE_RETRIES):
        processor.process_pending(max_requests=1)
        assert response_queue.empty()
        song.tick()

    processor.process_pending(max_requests=1)
    response = response_queue.get_nowait()
    assert response["status"] == "error"
    assert response["code"] == "PLAYHEAD_NOT_MOVED"
    assert song.transport_write_attempts == PLAYHEAD_MOVE_RETRIES
    assert (app.begin_count, app.end_count) == (1, 1)


def test_playhead_recovers_from_a_six_tick_live_transition() -> None:
    song = FakeSong(stuck_writes=6, deferred_writes=True)
    processor = RequestProcessor(song, FakeApplication())
    response_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
    processor.enqueue(QueuedRequest("set_current_song_time", {"time": 8.0}, response_queue))

    for _tick in range(12):
        processor.process_pending(max_requests=1)
        if not response_queue.empty():
            break
        song.tick()

    assert response_queue.get_nowait() == {
        "status": "ok",
        "result": {"current_song_time": 8.0},
    }
    assert song.transport_write_attempts == 7
