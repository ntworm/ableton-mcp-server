from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from AbletonMCPServer_RemoteScript import (
    AbletonMCPServer,
    JsonlSocketServer,
    QueuedRequest,
    RemoteError,
    RequestProcessor,
    create_instance,
)
from tests.remote_fakes import FakeApplication, FakeSong


def wait_for_request(processor: RequestProcessor) -> None:
    deadline = time.monotonic() + 1.0
    while processor.request_queue.empty() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert not processor.request_queue.empty()


def test_handle_frame_round_trip_crosses_ui_processor_boundary() -> None:
    processor = RequestProcessor(FakeSong(), FakeApplication())
    server = JsonlSocketServer(processor)
    result: list[dict[str, Any]] = []
    worker = threading.Thread(
        target=lambda: result.append(
            server._handle_frame(b'{"type":"get_session_info","params":{}}')
        )
    )
    worker.start()
    wait_for_request(processor)
    processor.process_pending()
    worker.join(timeout=1.0)
    assert result[0]["status"] == "ok"
    assert result[0]["result"]["tempo"] == 120.0


@pytest.mark.parametrize(
    "frame",
    [
        b"[]",
        b'{"params":{}}',
        b'{"type":"get_session_info","params":[]}',
    ],
)
def test_handle_frame_rejects_invalid_envelopes(frame: bytes) -> None:
    server = JsonlSocketServer(RequestProcessor(FakeSong(), FakeApplication()))
    with pytest.raises(RemoteError) as exc_info:
        server._handle_frame(frame)
    assert exc_info.value.code == "INVALID_PARAMS"


def test_serve_client_reads_jsonl_and_writes_response() -> None:
    processor = RequestProcessor(FakeSong(), FakeApplication())
    server = JsonlSocketServer(processor)
    client_socket, server_socket = socket.socketpair()
    worker = threading.Thread(target=server._serve_client, args=(server_socket,))
    worker.start()
    client_socket.sendall(b'{"type":"get_track_list","params":{}}\n')
    wait_for_request(processor)
    processor.process_pending()
    client_socket.settimeout(1.0)
    response = json.loads(client_socket.recv(4096).decode("utf-8"))
    assert response["status"] == "ok"
    assert response["result"][0]["id"] == "track:0"
    server.shutdown_event.set()
    client_socket.close()
    worker.join(timeout=1.0)


def test_processor_maps_unexpected_lom_exception_to_live_unavailable() -> None:
    processor = RequestProcessor(FakeSong(), FakeApplication())
    response_queue: Any = __import__("queue").Queue(maxsize=1)
    processor.enqueue(QueuedRequest("get_session_info", {}, response_queue))
    with patch(
        "AbletonMCPServer_RemoteScript.COMMAND_HANDLERS",
        {"get_session_info": lambda *_args: (_ for _ in ()).throw(RuntimeError("Live busy"))},
    ):
        processor.process_pending()
    response = response_queue.get_nowait()
    assert response["code"] == "LIVE_UNAVAILABLE"


def test_fallback_control_surface_lifecycle_delegates_to_socket_server() -> None:
    class CInstance:
        song = FakeSong()
        application = FakeApplication()

    with (
        patch.object(JsonlSocketServer, "start") as start,
        patch.object(JsonlSocketServer, "stop") as stop,
    ):
        surface = create_instance(CInstance())
        assert isinstance(surface, AbletonMCPServer)
        start.assert_called_once_with()
        surface.update_display()
        surface.disconnect()
        stop.assert_called_once_with()
