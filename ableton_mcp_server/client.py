from __future__ import annotations

import socket
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from contracts import (
    ALLOWED_MUTATIONS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_WS_PORT,
    WEBSOCKET_TARGET_COMMANDS,
    request_timeout_seconds,
)

from .errors import BridgeTimeoutError, LiveUnavailableError, error_from_envelope
from .protocol import decode_response, encode_request
from .ws_client import WSClient


class Client:
    """Hybrid JSONL TCP + WebSocket client for the Live-side bridges.

    Commands listed in ``WEBSOCKET_TARGET_COMMANDS`` are routed to the
    Extension Host WebSocket bridge on ``ws_port``.  All other commands
    use the synchronous TCP JSONL bridge on ``tcp_port``.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        ws_port: int = DEFAULT_WS_PORT,
        reconnect: bool = True,
        max_retries: int = 3,
        backoff_factor: float = 0.05,
    ) -> None:
        if host != DEFAULT_HOST:
            raise ValueError("Ableton bridge host must be loopback 127.0.0.1")
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self.reconnect = reconnect
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._socket: socket.socket | None = None
        self._connected = False
        self._recv_buffer = bytearray()
        self._lock = threading.Lock()
        self._ws_client = WSClient(host=host, port=ws_port)

    @property
    def connected(self) -> bool:
        return self._connected

    def is_ws_command(self, command_type: str) -> bool:
        """Return True if the command should be routed over WebSocket."""
        return command_type.strip().lower() in WEBSOCKET_TARGET_COMMANDS

    def connect(self) -> None:
        if not self._connected:
            self._connect_socket()

    def _connect_socket(self) -> None:
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.connect((self.host, self.port))
        except Exception:
            sock.close()
            raise
        self._socket = sock
        self._connected = True

    def close(self) -> None:
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
        self._socket = None
        self._connected = False
        self._recv_buffer.clear()

    def _read_line(self, timeout: float) -> bytes:
        sock = self._socket
        if sock is None:
            raise ConnectionError("Socket is not connected")
        sock.settimeout(timeout)
        while b"\n" not in self._recv_buffer:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Socket connection closed by Remote Script")
            self._recv_buffer.extend(chunk)
        line_end = self._recv_buffer.index(b"\n")
        frame = bytes(self._recv_buffer[: line_end + 1])
        del self._recv_buffer[: line_end + 1]
        return frame

    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Synchronous TCP call to the Remote Script bridge (port 9888)."""
        retries = 0
        may_retry = command_type not in ALLOWED_MUTATIONS
        request_params = dict(params or {})
        effective_timeout = (
            request_timeout_seconds(command_type, request_params) if timeout is None else timeout
        )
        with self._lock:
            while True:
                try:
                    if not self._connected:
                        self._connect_socket()
                    if self._socket is None:
                        raise ConnectionError("Socket is not connected")
                    self._socket.sendall(encode_request(command_type, request_params))
                    response = decode_response(self._read_line(effective_timeout))
                    if response.status == "ok":
                        return response.result
                    assert response.code is not None
                    assert response.message is not None
                    raise error_from_envelope(
                        response.code,
                        response.message,
                        response.hint,
                        response.details,
                    )
                except TimeoutError as exc:
                    self.close()
                    raise BridgeTimeoutError(
                        f"Command {command_type!r} timed out after {effective_timeout} seconds",
                        "For mutations, inspect current state before retrying.",
                    ) from exc
                except (ConnectionError, OSError) as exc:
                    self.close()
                    if may_retry and self.reconnect and retries < self.max_retries:
                        retries += 1
                        if self.backoff_factor:
                            time.sleep(self.backoff_factor * (2 ** (retries - 1)))
                        continue
                    hint = (
                        "Verify that Live is running and AbletonMCPServer is enabled."
                        if may_retry
                        else "For mutations, inspect current Live state before retrying."
                    )
                    raise LiveUnavailableError(
                        f"Command {command_type!r} failed at {self.host}:{self.port}: {exc}",
                        hint,
                    ) from exc

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> Any:
        """Async WebSocket call to the Extension Host bridge (port 9889)."""
        return await self._ws_client.call(method, params, timeout=timeout)
