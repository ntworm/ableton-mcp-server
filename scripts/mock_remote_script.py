"""The mock Remote Script: it answers the commands of the client over a socket."""

from __future__ import annotations

import argparse
import copy
import json
import socket
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import (  # noqa: E402
    CAPABILITY_EVIDENCE,
    DEFAULT_HOST,
    READ_ONLY_COMMANDS,
    UNSUPPORTED_CAPABILITIES,
)
from scripts.mock_remote_handlers import MockCommandHandlers  # noqa: E402

# Identity plus hierarchy/colour. Mixer state stays out of ``get_track_list``
# and is only reachable through ``get_track_state``.
TRACK_LIST_KEYS: tuple[str, ...] = (
    "id",
    "index",
    "name",
    "type",
    "color",
    "color_index",
    "is_group_track",
    "is_grouped",
    "group_track_index",
    "group_track_id",
    "is_visible",
    "fold_state",
)


def _default_track() -> dict[str, Any]:
    """Return the single track of the default mock Set."""
    return {
        "id": "track:0",
        "index": 0,
        "name": "Bass",
        "type": "midi",
        "color": 0x336699,
        "color_index": 3,
        "is_group_track": False,
        "is_grouped": False,
        "group_track_index": None,
        "group_track_id": None,
        "is_visible": True,
        "fold_state": 0,
        "devices": [
            {
                "id": "track:0/device:0",
                "name": "Operator",
                "parameters": [
                    {
                        "id": "track:0/device:0/param:0",
                        "name": "Device On",
                        "value": 1.0,
                        "min": 0.0,
                        "max": 1.0,
                    }
                ],
            }
        ],
        "clip_slots": [
            {
                "id": "track:0/clipslot:0",
                "clip_id": "track:0/clipslot:0/clip",
                "index": 0,
                "has_clip": True,
                "clip_name": "Bass Loop",
                "length_beats": 4.0,
                "is_playing": False,
                "notes": [
                    {
                        "pitch": 36,
                        "start_time": 0.0,
                        "duration": 1.0,
                        "velocity": 100,
                        "mute": False,
                    }
                ],
            }
        ],
    }


def default_snapshot() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "captured_at_unix_ms": 1719878400000,
        "live_version": "12.4.5",
        "tempo": 120.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "is_playing": False,
        "current_song_time": 0.0,
        "loop": False,
        "loop_start": 0.0,
        "loop_length": 4.0,
        "song_length": 64.25,
        "tracks": [_default_track()],
        "control_surfaces": [{"name": "MockRemoteScript", "type": "remote_script"}],
        "browser_categories_count": 7,
        "locators": [],
        "scenes": [{"index": 0, "name": "Verse", "is_empty": False}],
        "selected_context": {"selected_track_id": "track:0", "selected_track_index": 0},
        "project_metadata": {"song_name": "Mock Set", "file_path": "", "is_dirty": False},
        "loop_settings": {"loop": False, "loop_start": 0.0, "loop_length": 4.0},
    }


@dataclass
class MockRemoteScript(MockCommandHandlers):
    snapshot: dict[str, Any] = field(default_factory=default_snapshot)

    def ok(self, result: Any) -> dict[str, Any]:
        return {"status": "ok", "result": result}

    def error(self, code: str, message: str, hint: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "error", "code": code, "message": message}
        if hint:
            result["hint"] = hint
        return result

    def handle(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        if command in READ_ONLY_COMMANDS:
            return self.error(
                "READ_ONLY_VIOLATION",
                f"Command {command!r} is blocked: creative mutation is not available.",
            )
        if command in UNSUPPORTED_CAPABILITIES:
            envelope = self.error(
                "CAPABILITY_UNAVAILABLE",
                UNSUPPORTED_CAPABILITIES[command],
                "The request is well-formed; Live's public API has no operation that "
                "performs it. Nothing was changed in the Set.",
            )
            envelope["details"] = {
                **CAPABILITY_EVIDENCE[command],
                "request": dict(params),
                "applied": False,
            }
            return envelope
        reads = self._handle_read(command, params)
        if reads is not None:
            return reads
        mutations = self._handle_mutation(command, params)
        if mutations is not None:
            return mutations
        return self.error("UNKNOWN_COMMAND", f"Command {command!r} is not implemented")

    def _handle_read(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer a read command with the group handler that owns it."""
        for handler in (
            self._read_track_list,
            self._read_session,
            self._read_tracks,
            self._read_devices,
            self._read_diagnostics,
            self._read_project,
            self._read_queries,
        ):
            response = handler(command, params)
            if response is not None:
                return response
        return None

    def _read_track_list(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the track list read command."""
        if command == "get_track_list":
            return self.ok(
                [
                    {key: track[key] for key in TRACK_LIST_KEYS if key in track}
                    for track in self.snapshot["tracks"]
                ]
            )
        return None

    def _handle_mutation(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer a mutation command with the group handler that owns it."""
        for handler in (
            self._mutate_transport,
            self._mutate_device,
            self._mutate_clip_color,
            self._mutate_track_color,
            self._mutate_cue_point,
            self._mutate_cue_points,
            self._mutate_clips,
            self._mutate_clip_creation,
            self._mutate_batch,
        ):
            response = handler(command, params)
            if response is not None:
                return response
        return None

    def _track(self, index: Any) -> dict[str, Any] | None:
        if not isinstance(index, int):
            return None
        return next((track for track in self.snapshot["tracks"] if track["index"] == index), None)

    def _slot(self, params: dict[str, Any]) -> dict[str, Any] | None:
        track = self._track(params.get("track_index"))
        index = params.get("clip_index")
        if (
            not track
            or not isinstance(index, int)
            or index < 0
            or index >= len(track["clip_slots"])
        ):
            return None
        slot = track["clip_slots"][index]
        return slot if slot["has_clip"] else None

    def _missing(self, resource: str) -> dict[str, Any]:
        return self.error("INVALID_PARAMS", f"Requested {resource} does not exist")


@dataclass
class MockServerHandle:
    port: int
    server: socket.socket
    shutdown_event: threading.Event
    thread: threading.Thread

    def stop(self) -> None:
        self.shutdown_event.set()
        with suppress(OSError):
            self.server.close()
        self.thread.join(timeout=2.0)


def _serve_client(connection: socket.socket, remote: MockRemoteScript) -> None:
    buffer = bytearray()
    try:
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            while b"\n" in buffer:
                end = buffer.index(b"\n")
                frame = bytes(buffer[:end])
                del buffer[: end + 1]
                request = json.loads(frame.decode("utf-8"))
                response = remote.handle(request.get("type", ""), request.get("params", {}))
                connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
    finally:
        connection.close()


def run_mock_server(
    host: str = DEFAULT_HOST,
    port: int = 0,
    snapshot: dict[str, Any] | None = None,
) -> MockServerHandle:
    if host != DEFAULT_HOST:
        raise ValueError("Mock server is loopback-only")
    remote = MockRemoteScript(
        copy.deepcopy(snapshot) if snapshot is not None else default_snapshot()
    )
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    server.settimeout(0.2)
    actual_port = int(server.getsockname()[1])
    shutdown_event = threading.Event()

    def listen() -> None:
        while not shutdown_event.is_set():
            try:
                connection, _ = server.accept()
                threading.Thread(
                    target=_serve_client, args=(connection, remote), daemon=True
                ).start()
            except TimeoutError:
                continue
            except OSError:
                break

    thread = threading.Thread(target=listen, daemon=True, name="MockRemoteScript")
    thread.start()
    return MockServerHandle(actual_port, server, shutdown_event, thread)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9889)
    args = parser.parse_args()
    server = run_mock_server(port=args.port)
    print(f"Mock Remote Script listening on {DEFAULT_HOST}:{server.port}")
    try:
        server.thread.join()
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
