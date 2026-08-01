from __future__ import annotations

import argparse
import copy
import json
import socket
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from contracts import DEFAULT_HOST, READ_ONLY_COMMANDS


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
        "tracks": [
            {
                "id": "track:0",
                "index": 0,
                "name": "Bass",
                "type": "midi",
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
        ],
        "control_surfaces": [{"name": "MockRemoteScript", "type": "remote_script"}],
        "browser_categories_count": 7,
        "locators": [],
        "scenes": [{"index": 0, "name": "Verse", "is_empty": False}],
        "selected_context": {"selected_track_id": "track:0", "selected_track_index": 0},
        "project_metadata": {"song_name": "Mock Set", "file_path": "", "is_dirty": False},
        "loop_settings": {"loop": False, "loop_start": 0.0, "loop_length": 4.0},
    }


@dataclass
class MockRemoteScript:
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
        reads = self._handle_read(command, params)
        if reads is not None:
            return reads
        mutations = self._handle_mutation(command, params)
        if mutations is not None:
            return mutations
        return self.error("UNKNOWN_COMMAND", f"Command {command!r} is not implemented")

    def _handle_read(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if command == "take_snapshot":
            return self.ok(copy.deepcopy(self.snapshot))
        if command == "get_session_info":
            return self.ok(
                {
                    key: self.snapshot[key]
                    for key in (
                        "tempo",
                        "signature_numerator",
                        "signature_denominator",
                        "is_playing",
                        "current_song_time",
                    )
                }
            )
        if command == "get_track_list":
            return self.ok(
                [
                    {key: track[key] for key in ("id", "index", "name", "type")}
                    for track in self.snapshot["tracks"]
                ]
            )
        if command == "get_track_state":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track)) if track else self._missing("track")
        if command == "get_device_list":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track["devices"])) if track else self._missing("track")
        if command == "get_parameter_value":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            device_index = params.get("device_index")
            if not isinstance(device_index, int) or device_index >= len(track["devices"]):
                return self._missing("device")
            name = params.get("parameter_name")
            parameter = next(
                (
                    item
                    for item in track["devices"][device_index]["parameters"]
                    if item["name"] == name
                ),
                None,
            )
            return self.ok(copy.deepcopy(parameter)) if parameter else self._missing("parameter")
        if command == "get_clip_summary":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track["clip_slots"])) if track else self._missing("track")
        if command == "get_clip_notes":
            slot = self._slot(params)
            return self.ok(copy.deepcopy(slot.get("notes", []))) if slot else self._missing("clip")
        if command == "get_control_surfaces":
            return self.ok(copy.deepcopy(self.snapshot["control_surfaces"]))
        if command == "get_browser_categories":
            return self.ok(
                [
                    "Sounds",
                    "Drums",
                    "Instruments",
                    "Audio Effects",
                    "MIDI Effects",
                    "Plugins",
                    "Samples",
                ]
            )
        if command == "get_routing":
            return self.ok(
                {
                    "input_routing": "Ext. In",
                    "input_sub_routing": "1/2",
                    "output_routing": "Master",
                    "output_sub_routing": "1/2",
                }
            )
        if command == "get_locators":
            return self.ok(copy.deepcopy(self.snapshot["locators"]))
        if command == "get_scenes":
            return self.ok(copy.deepcopy(self.snapshot["scenes"]))
        if command == "get_scene_state":
            index = params.get("scene_index")
            scenes = self.snapshot["scenes"]
            return (
                self.ok(copy.deepcopy(scenes[index]))
                if isinstance(index, int) and index < len(scenes)
                else self._missing("scene")
            )
        if command == "get_project_metadata":
            return self.ok(copy.deepcopy(self.snapshot["project_metadata"]))
        if command == "get_loop_settings":
            return self.ok(copy.deepcopy(self.snapshot["loop_settings"]))
        if command == "get_selected_context":
            return self.ok(copy.deepcopy(self.snapshot["selected_context"]))
        if command == "get_song_length":
            return self.ok({"song_length": self.snapshot["song_length"]})
        if command == "live_find_track":
            query = str(params.get("query", "")).casefold()
            tracks = [
                {key: track[key] for key in ("id", "index", "name", "type")}
                for track in self.snapshot["tracks"]
                if query in track["name"].casefold()
            ]
            return self.ok(tracks)
        if command == "list_device_params":
            track = next(
                (
                    track
                    for track in self.snapshot["tracks"]
                    if track["id"] == params.get("track_id")
                ),
                None,
            )
            if not track:
                return self.error("STALE_REFERENCE", "Track path no longer resolves")
            return self.ok(
                [
                    {
                        "device_id": device["id"],
                        "device_name": device["name"],
                        "parameters": copy.deepcopy(device["parameters"]),
                    }
                    for device in track["devices"]
                ]
            )
        return None

    def _handle_mutation(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if command == "set_tempo":
            self.snapshot["tempo"] = float(params["tempo"])
            return self.ok(
                {
                    "tempo": self.snapshot["tempo"],
                    "resolved": {"kind": "tempo", "tempo": self.snapshot["tempo"]},
                }
            )
        if command == "set_parameter_value":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            device_index = params.get("device_index")
            if not isinstance(device_index, int) or device_index >= len(track["devices"]):
                return self._missing("device")
            device = track["devices"][device_index]
            parameter_name = params.get("parameter_name")
            parameter = next(
                (item for item in device["parameters"] if item["name"] == parameter_name),
                None,
            )
            if parameter is None:
                return self._missing("parameter")
            requested = float(params["value"])
            parameter["value"] = requested
            return self.ok(
                {
                    "target": requested,
                    "value": parameter["value"],
                    "is_quantized": parameter["is_quantized"],
                    "resolved": {
                        "kind": "device",
                        "track_index": track["index"],
                        "device_index": device_index,
                        "parameter_name": parameter_name,
                        "track_name": track["name"],
                        "device_name": device["name"],
                    },
                }
            )
        if command == "set_current_song_time":
            self.snapshot["current_song_time"] = float(params["time"])
            return self.ok({"current_song_time": self.snapshot["current_song_time"]})
        if command in ("start_playback", "stop_playback"):
            self.snapshot["is_playing"] = command == "start_playback"
            return self.ok({"is_playing": self.snapshot["is_playing"]})
        if command == "set_loop":
            self.snapshot["loop"] = bool(params["enabled"])
            self.snapshot["loop_settings"]["loop"] = self.snapshot["loop"]
            return self.ok({"loop": self.snapshot["loop"]})
        if command in ("set_loop_start", "set_loop_length"):
            key = "loop_start" if command.endswith("start") else "loop_length"
            param = "start_beat" if key == "loop_start" else "length_beats"
            self.snapshot[key] = float(params[param])
            self.snapshot["loop_settings"][key] = self.snapshot[key]
            return self.ok({key: self.snapshot[key]})
        if command == "create_cue_point":
            target = float(params["time"])
            cue = next(
                (item for item in self.snapshot["locators"] if abs(item["time"] - target) < 0.01),
                None,
            )
            action = "renamed" if cue else "created"
            if cue is None:
                cue = {"name": str(params["name"]), "time": target}
                self.snapshot["locators"].append(cue)
            else:
                cue["name"] = str(params["name"])
            return self.ok({**cue, "action": action})
        if command == "bulk_create_cue_points":
            results = []
            for index, item in enumerate(params["items"]):
                response = self._handle_mutation("create_cue_point", item)
                assert response is not None
                results.append({"index": index, "status": "ok", "result": response["result"]})
            return self.ok({"results": results})
        if command == "delete_cue_point":
            target = float(params["time"])
            cue = next(
                (item for item in self.snapshot["locators"] if abs(item["time"] - target) < 0.01),
                None,
            )
            if cue:
                self.snapshot["locators"].remove(cue)
            return self.ok({"deleted": cue is not None, "time": target})
        if command == "fire_clip":
            slot = self._slot(params)
            if not slot:
                return self._missing("clip")
            slot["is_playing"] = True
            return self.ok({"fired": True, "clip_id": slot["clip_id"]})
        if command == "add_notes_to_clip":
            slot = self._slot(params)
            if not slot:
                return self._missing("clip")
            slot.setdefault("notes", []).extend(copy.deepcopy(params["notes"]))
            return self.ok({"added": len(params["notes"]), "clip_id": slot["clip_id"]})
        if command == "create_clip":
            track = self._track(params.get("track_index"))
            clip_index = params.get("clip_index")
            if (
                not track
                or not isinstance(clip_index, int)
                or clip_index >= len(track["clip_slots"])
            ):
                return self._missing("clip slot")
            slot = track["clip_slots"][clip_index]
            if slot["has_clip"]:
                return self.error("BAD_INPUT", "Clip slot is not empty")
            slot.update(
                {
                    "clip_id": f"track:{track['index']}/clipslot:{clip_index}/clip",
                    "has_clip": True,
                    "length_beats": float(params["length_beats"]),
                    "notes": [],
                }
            )
            return self.ok(
                {
                    "created": True,
                    "clip_id": slot["clip_id"],
                    "length_beats": slot["length_beats"],
                    "resolved": {
                        "kind": "clip",
                        "track_index": track["index"],
                        "clip_index": clip_index,
                        "track_name": track["name"],
                        "clip_id": slot["clip_id"],
                    },
                }
            )
        if command == "run_batch":
            results = []
            completed = 0
            aborted_at = None
            for index, subcommand in enumerate(params["commands"]):
                response = self.handle(subcommand["type"], subcommand.get("params", {}))
                if response["status"] == "error":
                    results.append({"index": index, **response})
                    aborted_at = index
                    break
                results.append({"index": index, "status": "ok", "result": response["result"]})
                completed += 1
            return self.ok(
                {
                    "results": results,
                    "completed": completed,
                    "aborted_at": aborted_at,
                    "rolled_back": False,
                }
            )
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
