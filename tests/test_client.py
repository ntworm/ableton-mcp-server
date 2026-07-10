from __future__ import annotations

import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ableton_mcp_server.client import Client
from ableton_mcp_server.errors import (
    BridgeTimeoutError,
    LiveUnavailableError,
    StaleReferenceError,
)


class FakeSocket:
    def __init__(self, response: bytes = b"") -> None:
        self.response = bytearray(response)
        self.sent = bytearray()
        self.timeout: float | None = None
        self.closed = False

    def setsockopt(self, *_args: Any) -> None:
        return None

    def connect(self, _address: tuple[str, int]) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def recv(self, size: int) -> bytes:
        if not self.response:
            return b""
        chunk = self.response[:size]
        del self.response[:size]
        return bytes(chunk)

    def close(self) -> None:
        self.closed = True


def connected_client(response: bytes) -> tuple[Client, FakeSocket]:
    client = Client()
    fake = FakeSocket(response)
    client._socket = fake
    client._connected = True
    return client, fake


def test_client_sends_exact_jsonl_and_returns_result() -> None:
    client, fake = connected_client(b'{"status": "ok", "result": {"tempo": 120}}\n')
    assert client.call("get_session_info") == {"tempo": 120}
    assert fake.sent == b'{"type": "get_session_info", "params": {}}\n'


def test_client_maps_error_envelope_to_typed_error_with_hint() -> None:
    client, _ = connected_client(
        b'{"status": "error", "code": "STALE_REFERENCE", '
        b'"message": "track:9 disappeared", "hint": "Refresh tracks"}\n'
    )
    with pytest.raises(StaleReferenceError) as exc_info:
        client.call("get_track_state", {"track_index": 9})
    assert str(exc_info.value) == "track:9 disappeared"
    assert exc_info.value.hint == "Refresh tracks"


def test_timeout_becomes_bridge_timeout_without_retrying_mutation() -> None:
    client = Client(reconnect=True, max_retries=3, backoff_factor=0)
    fake = MagicMock()
    fake.recv.side_effect = TimeoutError("late")
    client._socket = fake
    client._connected = True
    client._connect_socket = MagicMock()

    with pytest.raises(BridgeTimeoutError):
        client.call("set_tempo", {"tempo": 128.0}, timeout=0.01)
    client._connect_socket.assert_not_called()


def test_read_reconnects_once_after_connection_failure() -> None:
    client = Client(reconnect=True, max_retries=1, backoff_factor=0)
    failing = MagicMock()
    failing.sendall.side_effect = ConnectionError("lost")
    client._socket = failing
    client._connected = True
    recovered = FakeSocket(b'{"status": "ok", "result": [1]}\n')

    def reconnect() -> None:
        client._socket = recovered
        client._connected = True

    client._connect_socket = MagicMock(side_effect=reconnect)
    assert client.call("get_track_list") == [1]
    client._connect_socket.assert_called_once_with()


def test_mutation_connection_failure_is_typed_live_unavailable() -> None:
    client = Client(reconnect=True, max_retries=3, backoff_factor=0)
    failing = MagicMock()
    failing.sendall.side_effect = OSError(10053, "connection aborted")
    client._socket = failing
    client._connected = True

    with pytest.raises(LiveUnavailableError) as exc_info:
        client.call("set_tempo", {"tempo": 128.0})

    assert exc_info.value.code == "LIVE_UNAVAILABLE"
    assert "127.0.0.1:9888" in str(exc_info.value)
    assert exc_info.value.hint == "For mutations, inspect current Live state before retrying."


def test_bulk_uses_a_timeout_budget_scaled_to_its_item_count() -> None:
    client, fake = connected_client(b'{"status": "ok", "result": {"results": []}}\n')
    params = {"items": [{"name": f"M{index}", "time": index * 8} for index in range(15)]}

    assert client.call("bulk_create_cue_points", params) == {"results": []}

    assert fake.timeout > 6.0


def test_client_rejects_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Client(host="0.0.0.0")


@patch("ableton_mcp_server.client.socket.socket")
def test_connect_uses_tcp_loopback(mock_socket_factory: MagicMock) -> None:
    fake = FakeSocket()
    mock_socket_factory.return_value = fake
    client = Client(port=9999)
    client.connect()
    mock_socket_factory.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
    assert client.connected is True
