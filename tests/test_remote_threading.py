from __future__ import annotations

import queue

from AbletonMCPServer_RemoteScript import QueuedRequest, RequestProcessor
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
