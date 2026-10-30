"""Ableton Live MIDI Remote Script for the Ableton MCP Server.

Socket work runs in background threads. Every Live Object Model access is
dispatched by :meth:`AbletonMCPServer.update_display` on Live's main thread.
"""

from __future__ import annotations

from typing import Any

from ._contracts import PLAYHEAD_MOVE_RETRIES, REALTIME_UDP_PORT
from .common import ControlSurface, Live, RemoteError, _dbg, _safe
from .dispatch import _command_steps, execute_command
from .lifecycle import GUI_LIFECYCLE_WORKFLOW, live_fade_steps, quit_ableton_steps
from .realtime_server import RealtimeUDPServer
from .socket_server import JsonlSocketServer, QueuedRequest, RequestProcessor
from .transport import (
    _verified_attribute_boolean_steps,
    _verified_attribute_numeric_steps,
    _verified_attribute_string_steps,
)

# v0.5.0 — runtime identity tag surfaced in `get_bridge_status`.
# The base upstream did not ship one; v0.5.0 establishes the convention.
REMOTE_SCRIPT_RUNTIME_VERSION = "set-lifecycle-and-fade-1"


def _resolve_undo_target(*candidates: Any) -> Any:
    for candidate in candidates:
        if candidate is None:
            continue
        if callable(
            _safe(lambda candidate=candidate: candidate.begin_undo_step, None)
        ) and callable(_safe(lambda candidate=candidate: candidate.end_undo_step, None)):
            return candidate
    return candidates[-1]


class AbletonMCPServer(ControlSurface):
    def __init__(self, c_instance: Any) -> None:
        super().__init__(c_instance)
        application = (
            Live.Application.get_application() if Live is not None else c_instance.application
        )
        song = self.song() if callable(self.song) else self.song
        undo_target = _resolve_undo_target(c_instance, self, application, song)
        self._processor = RequestProcessor(song, application, undo_target, self)

        self._song = song
        self._realtime_queue = []
        self._realtime_server = RealtimeUDPServer(REALTIME_UDP_PORT, self._realtime_queue)
        self._realtime_server.start()
        self._socket_server = JsonlSocketServer(self._processor)
        self._socket_server.start()
        _dbg("startup endpoint=127.0.0.1:9888 realtime=%d" % REALTIME_UDP_PORT)
        self.show_message(
            "AbletonMCPServer: Active on 127.0.0.1:9888 / UDP:%d" % REALTIME_UDP_PORT
        )

    def update_display(self) -> None:
        super().update_display()
        self._processor.process_pending()
        self._drain_realtime_queue()

    def _drain_realtime_queue(self) -> None:
        """Apply queued realtime moves. Only ever called on Live's own thread."""

        while self._realtime_queue:
            command = self._realtime_queue.pop(0)
            if command[0] == "parameter.set":
                # Not yet applied: the arming handshake that would say which
                # parameter a ref names is not built, so nothing can resolve it.
                _dbg("Realtime write: %s -> %s" % (command[1], command[2]))
            elif command[0] == "emergency-stop":
                _dbg("Realtime emergency stop")
                stop_playing = getattr(self._song, "stop_playing", None)
                if callable(stop_playing):
                    stop_playing()

    def disconnect(self) -> None:
        self._socket_server.stop()
        self._realtime_server.stop()
        super().disconnect()


def create_instance(c_instance: Any) -> AbletonMCPServer:
    return AbletonMCPServer(c_instance)


__all__ = [
    "AbletonMCPServer",
    "GUI_LIFECYCLE_WORKFLOW",
    "JsonlSocketServer",
    "PLAYHEAD_MOVE_RETRIES",
    "QueuedRequest",
    "REMOTE_SCRIPT_RUNTIME_VERSION",
    "RemoteError",
    "RequestProcessor",
    "_command_steps",
    "_dbg",
    "_safe",
    "_verified_attribute_boolean_steps",
    "_verified_attribute_numeric_steps",
    "_verified_attribute_string_steps",
    "create_instance",
    "execute_command",
    "live_fade_steps",
    "quit_ableton_steps",
]
