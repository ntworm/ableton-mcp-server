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
from AbletonMCPServer_RemoteScript._contracts import DEFAULT_PORT, REALTIME_UDP_PORT
from AbletonMCPServer_RemoteScript.realtime_server import (
    MAX_QUEUED_COMMANDS,
    RealtimeUDPServer,
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


def test_serve_client_keeps_an_idle_persistent_connection_open() -> None:
    class TimeoutThenFrameSocket:
        def __init__(self) -> None:
            self.recv_count = 0
            self.sent = bytearray()
            self.closed = False

        def settimeout(self, _timeout: float) -> None:
            return None

        def recv(self, _size: int) -> bytes:
            self.recv_count += 1
            if self.recv_count == 1:
                raise TimeoutError("idle")
            if self.recv_count == 2:
                return b'{"type":"get_session_info","params":{}}\n'
            return b""

        def sendall(self, data: bytes) -> None:
            self.sent.extend(data)

        def close(self) -> None:
            self.closed = True

    processor = RequestProcessor(FakeSong(), FakeApplication())
    server = JsonlSocketServer(processor)
    connection = TimeoutThenFrameSocket()
    worker = threading.Thread(target=server._serve_client, args=(connection,))  # type: ignore[arg-type]
    worker.start()

    wait_for_request(processor)
    processor.process_pending()
    worker.join(timeout=1.0)

    response = json.loads(connection.sent.decode("utf-8"))
    assert response["status"] == "ok"
    assert response["result"]["tempo"] == 120.0
    assert connection.closed is True


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
        patch.object(RealtimeUDPServer, "start") as realtime_start,
        patch.object(RealtimeUDPServer, "stop") as realtime_stop,
        patch("AbletonMCPServer_RemoteScript._dbg") as debug,
    ):
        surface = create_instance(CInstance())
        assert isinstance(surface, AbletonMCPServer)
        start.assert_called_once_with()
        realtime_start.assert_called_once_with()
        surface.update_display()
        surface.disconnect()
        stop.assert_called_once_with()
        # Both listeners have to come down. Leaving the UDP socket bound stops
        # the next instance of the script from binding it.
        realtime_stop.assert_called_once_with()
        debug.assert_any_call(
            "startup endpoint=127.0.0.1:%d realtime=%d" % (DEFAULT_PORT, REALTIME_UDP_PORT)
        )


def _armed_server() -> RealtimeUDPServer:
    queue: list[tuple[Any, ...]] = []
    server = RealtimeUDPServer(REALTIME_UDP_PORT, queue)
    server.arm("tok", ["dev/1/param/2", "dev/1/param/3"])
    return server


def _packet(**fields: Any) -> bytes:
    return json.dumps(fields).encode("utf-8")


def test_realtime_drops_everything_until_it_is_armed() -> None:
    # An open UDP port on loopback is only acceptable because a packet does
    # nothing until a token has been handed out over the authenticated channel.
    queue: list[tuple[Any, ...]] = []
    server = RealtimeUDPServer(REALTIME_UDP_PORT, queue)
    server._handle_packet(_packet(token="tok", seq=1, op="parameter.set", ref="a", value=0.5))
    assert queue == []


def test_realtime_rejects_a_wrong_token_and_an_unarmed_reference() -> None:
    server = _armed_server()
    server._handle_packet(
        _packet(token="wrong", seq=1, op="parameter.set", ref="dev/1/param/2", value=0.5)
    )
    server._handle_packet(
        _packet(token="tok", seq=2, op="parameter.set", ref="dev/9/param/9", value=0.5)
    )
    assert server.callback_queue == []


def test_realtime_ignores_a_packet_that_arrives_late() -> None:
    # UDP reorders and duplicates. An older move is a stale packet, not a
    # correction, and applying it would jump the control backwards.
    server = _armed_server()
    server._handle_packet(
        _packet(token="tok", seq=5, op="parameter.set", ref="dev/1/param/2", value=0.9)
    )
    server._handle_packet(
        _packet(token="tok", seq=4, op="parameter.set", ref="dev/1/param/2", value=0.1)
    )
    assert server.callback_queue == [("parameter.set", "dev/1/param/2", 0.9)]


def test_realtime_applies_an_xy_move_whole_or_not_at_all() -> None:
    server = _armed_server()
    server._handle_packet(
        _packet(
            token="tok", seq=1, op="xy.set",
            xRef="dev/1/param/2", x=0.25, yRef="dev/9/param/9", y=0.75,
        )
    )
    # One axis unarmed means the pad would land somewhere nobody pointed at.
    assert server.callback_queue == []
    server._handle_packet(
        _packet(
            token="tok", seq=2, op="xy.set",
            xRef="dev/1/param/2", x=0.25, yRef="dev/1/param/3", y=0.75,
        )
    )
    assert server.callback_queue == [
        ("parameter.set", "dev/1/param/2", 0.25),
        ("parameter.set", "dev/1/param/3", 0.75),
    ]


def test_realtime_survives_malformed_input() -> None:
    server = _armed_server()
    for data in (b"\xff\xfe", b"not json", b"[1, 2, 3]", b'"a string"'):
        server._handle_packet(data)
    assert server.callback_queue == []


def test_realtime_queue_is_bounded_and_keeps_the_newest_moves() -> None:
    # Live drains at roughly 10 Hz. A controller sending faster must not grow
    # the queue without limit, and the value that matters is the latest one.
    server = _armed_server()
    for seq in range(MAX_QUEUED_COMMANDS + 20):
        server._handle_packet(
            _packet(
                token="tok", seq=seq, op="parameter.set",
                ref="dev/1/param/2", value=float(seq),
            )
        )
    assert len(server.callback_queue) == MAX_QUEUED_COMMANDS
    assert server.callback_queue[-1][2] == float(MAX_QUEUED_COMMANDS + 19)


def test_disarming_closes_the_channel_again() -> None:
    server = _armed_server()
    server.disarm()
    server._handle_packet(
        _packet(token="tok", seq=1, op="parameter.set", ref="dev/1/param/2", value=0.5)
    )
    assert server.callback_queue == []


def test_realtime_binds_and_releases_its_port() -> None:
    # The reload path: stop() must not return while the socket is still bound,
    # or the next instance of the script cannot bind the same port.
    queue: list[tuple[Any, ...]] = []
    server = RealtimeUDPServer(REALTIME_UDP_PORT, queue)
    server.start()
    deadline = time.monotonic() + 2.0
    while server.sock is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.sock is not None
    server.stop()
    assert not server.is_alive()

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", REALTIME_UDP_PORT))
    finally:
        probe.close()


def test_emergency_stop_reaches_the_song_through_the_drain() -> None:
    # The song attribute on a ControlSurface is a callable. Reading through it
    # without resolving it first is why the emergency stop did nothing.
    class CInstance:
        song = FakeSong()
        application = FakeApplication()

    with (
        patch.object(JsonlSocketServer, "start"),
        patch.object(JsonlSocketServer, "stop"),
        patch.object(RealtimeUDPServer, "start"),
        patch.object(RealtimeUDPServer, "stop"),
        patch("AbletonMCPServer_RemoteScript._dbg"),
    ):
        surface = create_instance(CInstance())
        surface._song.start_playing()
        assert surface._song.is_playing is True

        surface._realtime_queue.append(("emergency-stop",))
        surface.update_display()
        assert surface._realtime_queue == []
        assert surface._song.is_playing is False


def test_emergency_stop_works_when_song_is_a_method_as_it_is_in_live() -> None:
    # Live exposes song as a callable on the control surface, not as the object.
    # Reading stop_playing off the callable finds nothing and the emergency stop
    # silently does nothing, which is the failure mode this pins.
    real_song = FakeSong()

    class CInstance:
        application = FakeApplication()

        @staticmethod
        def song() -> FakeSong:
            return real_song

    with (
        patch.object(JsonlSocketServer, "start"),
        patch.object(JsonlSocketServer, "stop"),
        patch.object(RealtimeUDPServer, "start"),
        patch.object(RealtimeUDPServer, "stop"),
        patch("AbletonMCPServer_RemoteScript._dbg"),
    ):
        surface = create_instance(CInstance())
        assert callable(surface.song)
        real_song.start_playing()

        surface._realtime_queue.append(("emergency-stop",))
        surface.update_display()
        assert real_song.is_playing is False
