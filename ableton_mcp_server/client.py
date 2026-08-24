from __future__ import annotations

import socket
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from contracts import (
    ALLOWED_MUTATIONS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_WS_PORT,
    WEBSOCKET_TARGET_COMMANDS,
    request_timeout_seconds,
)

from .errors import (
    BridgeEpochMismatchError,
    BridgePreSendError,
    BridgeTimeoutError,
    BridgeTransportAmbiguousError,
    LiveUnavailableError,
    error_from_envelope,
)
from .protocol import ProtocolError, Response, decode_response, encode_request
from .ws_client import WSClient


class BridgeContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["bridge.contract.v1"] = "bridge.contract.v1"
    owner: Literal["AbletonMCPServer_RemoteScript"] = "AbletonMCPServer_RemoteScript"
    protocol_version: Literal["bridge.v1"] = "bridge.v1"
    capabilities: dict[str, str] = Field(default_factory=dict)


class CapabilitySnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    port: int = Field(ge=1, le=65535)
    connection_epoch: int = Field(ge=0)
    contract: BridgeContractV1
    fetched_at: float
    freshness: Literal["fresh", "stale"]


@dataclass(frozen=True)
class ConnectionSnapshot:
    host: str
    port: int
    connected: bool
    connection_epoch: int


T = TypeVar("T")


@dataclass(frozen=True)
class AtEpochCallResultV1(Generic[T]):
    value: T
    receipt: Any | None
    epoch_used: int
    transport_state: Literal["received"] = "received"


@dataclass(frozen=True)
class BridgeReceiptStateV1:
    """Minimal receipt state retained for business-error envelopes."""

    state: Literal["preview", "rejected", "committed", "partial", "unknown"]


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
        self._lock = threading.RLock()
        self._connection_epoch = 0
        self._capability_cache: dict[tuple[str, int, int], CapabilitySnapshotV1] = {}
        self._ws_client = WSClient(host=host, port=ws_port)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def connection_epoch(self) -> int:
        return self._connection_epoch

    @property
    def connection_snapshot(self) -> ConnectionSnapshot:
        with self._lock:
            return ConnectionSnapshot(self.host, self.port, self._connected, self._connection_epoch)

    def is_ws_command(self, command_type: str) -> bool:
        """Return True if the command should be routed over WebSocket."""
        return command_type.strip().lower() in WEBSOCKET_TARGET_COMMANDS

    def connect(self) -> None:
        with self._lock:
            if not self._connected:
                self._connect_socket()

    def _connect_socket(self) -> None:
        self._close_locked(increment=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.connect((self.host, self.port))
        except Exception:
            sock.close()
            raise
        self._socket = sock
        self._connected = True
        self._connection_epoch += 1

    def close(self) -> None:
        with self._lock:
            self._close_locked(increment=True)

    def _close_locked(self, *, increment: bool) -> None:
        had_socket = self._socket is not None or self._connected
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
        self._socket = None
        self._connected = False
        self._recv_buffer.clear()
        if increment and had_socket:
            self._connection_epoch += 1

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
                    self._close_locked(increment=True)
                    raise BridgeTimeoutError(
                        f"Command {command_type!r} timed out after {effective_timeout} seconds",
                        "For mutations, inspect current state before retrying.",
                    ) from exc
                except (ConnectionError, OSError) as exc:
                    self._close_locked(increment=True)
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

    def call_at_epoch(
        self,
        expected_epoch: int,
        action: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> AtEpochCallResultV1[Any]:
        """Send one request while holding the connection epoch lock.

        This path intentionally has no reconnect or retry.  After ``sendall``
        begins, a transport failure is ambiguous and callers must inspect the
        target before deciding what to do next.
        """

        request_params = dict(params or {})
        with self._lock:
            if not self._connected or self._socket is None:
                raise BridgeEpochMismatchError("disconnected", bytes_sent=0)
            if self._connection_epoch != expected_epoch:
                raise BridgeEpochMismatchError("epoch_mismatch", bytes_sent=0)
            try:
                encoded = encode_request(action, request_params)
            except (ProtocolError, TypeError, ValueError) as error:
                raise BridgePreSendError(bytes_sent=0) from error
            effective_timeout = (
                request_timeout_seconds(action, request_params) if timeout is None else timeout
            )
            try:
                self._socket.sendall(encoded)
                response = decode_response(self._read_line(effective_timeout))
            except (TimeoutError, ConnectionError, OSError, ProtocolError) as error:
                self._close_locked(increment=True)
                raise BridgeTransportAmbiguousError() from error
            value: Any = response.result if response.status == "ok" else response
            return AtEpochCallResultV1(
                value=value,
                receipt=_extract_receipt(response),
                epoch_used=self._connection_epoch,
            )

    def cache_capability_snapshot(self, snapshot: CapabilitySnapshotV1) -> None:
        if snapshot.host != self.host or snapshot.port != self.port:
            return
        if snapshot.connection_epoch != self.connection_epoch:
            return
        self._capability_cache[(snapshot.host, snapshot.port, snapshot.connection_epoch)] = snapshot

    def get_capability_snapshot(self, now: float | None = None) -> CapabilitySnapshotV1 | None:
        key = (self.host, self.port, self.connection_epoch)
        snapshot = self._capability_cache.get(key)
        if snapshot is None or not self.connected:
            return None
        current = time.monotonic() if now is None else now
        age = current - snapshot.fetched_at
        if age < 0 or age > 5.0:
            return None
        return snapshot.model_copy(update={"freshness": "fresh"})

    def capability_for_epoch(
        self, expected_epoch: int, now: float | None = None
    ) -> CapabilitySnapshotV1:
        snapshot = self.get_capability_snapshot(now)
        if snapshot is None or snapshot.connection_epoch != expected_epoch:
            raise BridgeEpochMismatchError("epoch_mismatch", bytes_sent=0)
        return snapshot

    def get_capability_status(self, now: float | None = None) -> BridgeContractV1 | None:
        cached = self.get_capability_snapshot(now)
        if cached is not None:
            return cached.contract
        try:
            session_info = self.call("get_session_info", {})
            from .diagnostics import bridge_status

            status = bridge_status(self, session_info=session_info)
            raw_contract = status.get("bridge_contract")
            if not isinstance(raw_contract, Mapping):
                return None
            contract = BridgeContractV1.model_validate(raw_contract)
            fetched_at = time.monotonic() if now is None else now
            self.cache_capability_snapshot(
                CapabilitySnapshotV1(
                    host=self.host,
                    port=self.port,
                    connection_epoch=self.connection_epoch,
                    contract=contract,
                    fetched_at=fetched_at,
                    freshness="fresh",
                )
            )
            return contract
        except Exception:
            return None

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> Any:
        """Async WebSocket call to the Extension Host bridge (port 9889)."""
        return await self._ws_client.call(method, params, timeout=timeout)


def _extract_receipt(response: Response) -> Any | None:
    value: Any = response.result if response.status == "ok" else response.details
    if not isinstance(value, Mapping):
        return None
    candidate = value.get("receipt", value)
    if not isinstance(candidate, Mapping):
        return None
    if "state" not in candidate:
        if response.status == "error" and response.code:
            return BridgeReceiptStateV1(state="rejected")
        return None
    try:
        from .groove_intelligence.apply import ApplyReceiptV1

        return ApplyReceiptV1.model_validate(candidate)
    except Exception:
        state = candidate.get("state")
        if state in {"preview", "rejected", "committed", "partial", "unknown"}:
            return BridgeReceiptStateV1(state=state)
        return None
