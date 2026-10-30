"""JSONL socket server and the request queue drained on Live's UI thread."""

from __future__ import annotations

import json
import queue
import socket
import threading
from collections.abc import Generator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from ._contracts import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ERROR_INVALID_PARAMS,
    ERROR_LIVE_UNAVAILABLE,
    ERROR_READ_ONLY_VIOLATION,
    ERROR_TIMEOUT,
    READ_ONLY_COMMANDS,
    request_timeout_seconds,
)
from .common import RemoteError, logger
from .dispatch import _request_steps

_MAX_FRAME_BYTES = 1024 * 1024


@dataclass
class QueuedRequest:
    command: str
    params: dict[str, Any]
    response_queue: queue.Queue[dict[str, Any]]


@dataclass
class ActiveRequest:
    request: QueuedRequest
    steps: Generator[None, None, Any]


class RequestProcessor:
    """Owns the UI-thread queue; socket threads only call :meth:`enqueue`."""

    def __init__(
        self,
        song: Any,
        application: Any,
        undo_target: Any = None,
        control_surface: Any = None,
    ) -> None:
        self.song = song
        self.application = application
        self.undo_target = undo_target if undo_target is not None else application
        self.control_surface = control_surface
        self.request_queue: queue.Queue[QueuedRequest] = queue.Queue()
        self.active_request: ActiveRequest | None = None

    def enqueue(self, request: QueuedRequest) -> None:
        self.request_queue.put(request)

    def process_pending(self, max_requests: int = 16) -> int:
        processed = 0
        while processed < max_requests:
            if self.active_request is None:
                try:
                    request = self.request_queue.get_nowait()
                except queue.Empty:
                    break
                self.active_request = ActiveRequest(
                    request,
                    _request_steps(
                        self.song,
                        self.application,
                        request.command,
                        request.params,
                        self.undo_target,
                        self.control_surface,
                    ),
                )
            active = self.active_request
            try:
                next(active.steps)
                break
            except StopIteration as completed:
                response = {"status": "ok", "result": completed.value}
            except RemoteError as error:
                response = error.to_envelope()
            except Exception as error:
                logger.exception("Unhandled Remote Script error for %s", active.request.command)
                response = RemoteError(ERROR_LIVE_UNAVAILABLE, str(error)).to_envelope()
            active.request.response_queue.put(response)
            self.active_request = None
            processed += 1
        return processed


class JsonlSocketServer:
    """Loopback-only JSONL listener that performs no Live API access."""

    def __init__(self, processor: RequestProcessor) -> None:
        self.processor = processor
        self.shutdown_event = threading.Event()
        self.server_socket: socket.socket | None = None
        self.thread = threading.Thread(
            target=self._serve, daemon=True, name="AbletonMCPServerSocket"
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.shutdown_event.set()
        if self.server_socket is not None:
            with suppress(OSError):
                self.server_socket.close()
        self.thread.join(timeout=1.0)

    def _serve(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket = server
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((DEFAULT_HOST, DEFAULT_PORT))
            server.listen(5)
            server.settimeout(0.5)
        except OSError as error:
            logger.error("Could not bind %s:%s: %s", DEFAULT_HOST, DEFAULT_PORT, error)
            return
        while not self.shutdown_event.is_set():
            try:
                connection, _address = server.accept()
                threading.Thread(
                    target=self._serve_client,
                    args=(connection,),
                    daemon=True,
                    name="AbletonMCPServerClient",
                ).start()
            except TimeoutError:
                continue
            except OSError:
                if not self.shutdown_event.is_set():
                    logger.exception("Socket accept failed")
                break

    def _drain_frames(self, connection: socket.socket, buffer: bytearray) -> None:
        """Answer every complete JSONL frame that ``buffer`` holds."""
        while b"\n" in buffer:
            line_end = buffer.index(b"\n")
            frame = bytes(buffer[:line_end])
            del buffer[: line_end + 1]
            if not frame.strip():
                continue
            response = self._handle_frame(frame)
            connection.sendall((json.dumps(response) + "\n").encode("utf-8"))

    def _serve_client(self, connection: socket.socket) -> None:
        buffer = bytearray()
        connection.settimeout(1.0)
        try:
            while not self.shutdown_event.is_set():
                try:
                    chunk = connection.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_FRAME_BYTES:
                    raise RemoteError(ERROR_INVALID_PARAMS, "JSONL frame exceeds 1 MiB.")
                self._drain_frames(connection, buffer)
        except RemoteError as error:
            connection.sendall((json.dumps(error.to_envelope()) + "\n").encode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            response = RemoteError(ERROR_INVALID_PARAMS, str(error)).to_envelope()
            with suppress(OSError):
                connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
        finally:
            with suppress(OSError):
                connection.close()

    def _handle_frame(self, frame: bytes) -> dict[str, Any]:
        request = json.loads(frame.decode("utf-8"))
        if not isinstance(request, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Request must be a JSON object.")
        command = request.get("type")
        params = request.get("params", {})
        if not isinstance(command, str) or not command.strip():
            raise RemoteError(ERROR_INVALID_PARAMS, "Request type must be a non-empty string.")
        if not isinstance(params, dict):
            raise RemoteError(ERROR_INVALID_PARAMS, "Request params must be an object.")
        if command.strip().lower() in READ_ONLY_COMMANDS:
            return RemoteError(
                ERROR_READ_ONLY_VIOLATION,
                "Command %r is blocked: creative mutation is not available." % command,
            ).to_envelope()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self.processor.enqueue(QueuedRequest(command, params, response_queue))
        try:
            return response_queue.get(timeout=request_timeout_seconds(command, params))
        except queue.Empty:
            return RemoteError(
                ERROR_TIMEOUT,
                "Command execution timed out waiting for Live's UI thread.",
            ).to_envelope()
