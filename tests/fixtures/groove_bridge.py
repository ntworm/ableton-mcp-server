"""Deterministic bridge fixtures for epoch and guarded-apply tests."""

from __future__ import annotations

import json
from typing import Any

from ableton_mcp_server.client import Client

OK_RESPONSE = b'{"status":"ok","result":{"state":"committed"}}\n'


class FakeSocket:
    def __init__(
        self,
        bridge: NewBridgeFixture,
        *,
        epoch: int,
        response: bytes | None = None,
        session_info: dict[str, object] | None = None,
    ) -> None:
        self.bridge = bridge
        self.epoch = epoch
        self._response = bytearray()
        self.batch_response = response
        self.session_info = session_info
        self.sent: list[bytes] = []
        self.send_calls = 0
        self.raise_after_send = False
        self.closed = False

    def settimeout(self, _timeout: float) -> None:
        return None

    def sendall(self, payload: bytes) -> None:
        self.send_calls += 1
        self.sent.append(payload)
        self.bridge.sent_bytes += len(payload)
        if self.raise_after_send:
            raise ConnectionError("post-send fixture failure")
        request = json.loads(payload.decode("utf-8"))
        if request.get("type") == "get_session_info":
            result = self.session_info or self.bridge.get_session_info()
            self._response.extend(json.dumps({"status": "ok", "result": result}).encode() + b"\n")
        elif request.get("type") == "run_batch":
            result = self.bridge.dispatch({"type": "run_batch", **request.get("params", {})})
            if self.batch_response is not None:
                self._response.extend(self.batch_response)
                self.batch_response = None
                return
            if result.get("code"):
                self._response.extend(json.dumps({"status": "error", **result}).encode() + b"\n")
            else:
                self._response.extend(
                    json.dumps({"status": "ok", "result": result}).encode() + b"\n"
                )

    def recv(self, size: int) -> bytes:
        if not self._response:
            return b""
        chunk = self._response[:size]
        del self._response[:size]
        return bytes(chunk)

    def close(self) -> None:
        self.closed = True


class NewBridgeFixture:
    def __init__(
        self,
        capabilities: dict[str, str] | None,
        occupied: set[tuple[int, int]] | None = None,
        session_info: dict[str, object] | None = None,
    ) -> None:
        self.capabilities = dict(capabilities) if capabilities is not None else None
        self.occupied = set(occupied or set())
        self._session_info = dict(session_info or {})
        self.begin_undo_calls = 0
        self.command_calls: list[dict[str, Any]] = []
        self.sent_bytes = 0
        self.dispatch_calls = 0
        self.session_info_calls = 0
        self.precondition_evaluations: list[tuple[int, int]] = []
        self.last_preconditions: list[dict[str, Any]] = []
        self.swap_occupancy = False

    def capable_status(self, epoch: int = 1) -> dict[str, object]:
        result: dict[str, object] = {
            "tempo": 120.0,
            "current_song_time": 0.0,
            "is_playing": False,
            "connection_epoch": epoch,
        }
        if self.capabilities is not None:
            result["bridge_contract"] = {
                "schema_version": "bridge.contract.v1",
                "owner": "AbletonMCPServer_RemoteScript",
                "protocol_version": "bridge.v1",
                "capabilities": dict(self.capabilities),
            }
        result.update(self._session_info)
        return result

    def get_session_info(self) -> dict[str, object]:
        self.session_info_calls += 1
        return self.capable_status()

    def dispatch(self, request: dict[str, object]) -> dict[str, object]:
        self.dispatch_calls += 1
        if request.get("type") != "run_batch":
            return {"code": "UNKNOWN_COMMAND", "message": "fixture only implements run_batch"}
        params = request
        commands = params.get("commands")
        preconditions = params.get("preconditions", [])
        if not isinstance(commands, list) or not commands:
            return {"code": "INVALID_PARAMS", "message": "commands required"}
        if preconditions and (
            self.capabilities is None or self.capabilities.get("run_batch_preconditions") != "v1"
        ):
            return {"code": "PRECONDITION_UNSUPPORTED", "message": "capability required"}
        if not isinstance(preconditions, list):
            return {"code": "PRECONDITION_INVALID", "message": "preconditions must be a list"}
        self.last_preconditions = [item for item in preconditions if isinstance(item, dict)]
        first_failure: dict[str, object] | None = None
        for index, item in enumerate(preconditions):
            if (
                not isinstance(item, dict)
                or item.get("type") != "slot_empty"
                or item.get("version") != "v1"
            ):
                first_failure = {
                    "code": "PRECONDITION_INVALID",
                    "message": "invalid precondition",
                    "bridge_stage": "precondition",
                    "index": index,
                }
                continue
            item_params = item.get("params")
            if not isinstance(item_params, dict):
                first_failure = first_failure or {
                    "code": "PRECONDITION_INVALID",
                    "message": "invalid params",
                    "bridge_stage": "precondition",
                    "index": index,
                }
                continue
            key = (int(item_params.get("track_index", -1)), int(item_params.get("clip_index", -1)))
            self.precondition_evaluations.append(key)
            if self.swap_occupancy:
                self.occupied.add(key)
            if key in self.occupied:
                first_failure = first_failure or {
                    "code": "PRECONDITION_FAILED",
                    "message": "slot is not empty",
                    "bridge_stage": "precondition",
                    "index": index,
                }
        if first_failure is not None:
            return first_failure
        self.begin_undo_calls += 1
        results: list[dict[str, object]] = []
        for index, command in enumerate(commands):
            if not isinstance(command, dict):
                results.append({"index": index, "status": "error", "code": "INVALID_PARAMS"})
                return {
                    "results": results,
                    "completed": index,
                    "aborted_at": index,
                    "rolled_back": False,
                }
            self.command_calls.append(command)
            command_type = command.get("type")
            if command_type == "create_clip":
                result = {"clip_ref": "clip:3:2"}
                results.append({"index": index, "status": "ok", "result": result})
            elif command_type == "add_notes_to_clip":
                results.append(
                    {
                        "index": index,
                        "status": "ok",
                        "result": {"added": len(command.get("params", {}).get("notes", []))},
                    }
                )
            else:
                results.append({"index": index, "status": "ok", "result": {}})
        return {
            "results": results,
            "completed": len(results),
            "aborted_at": None,
            "rolled_back": False,
            "state": "committed",
        }

    def connected_client(
        self,
        epoch: int,
        response: bytes | None = None,
        session_info: dict[str, object] | None = None,
    ) -> tuple[Client, FakeSocket]:
        client = Client(reconnect=False)
        fake_socket = FakeSocket(self, epoch=epoch, response=response, session_info=session_info)
        client._socket = fake_socket
        client._connected = True
        client._connection_epoch = epoch
        return client, fake_socket

    def connected_client_object(self) -> Client:
        return self.connected_client(1)[0]

    def precondition_failed_response(self) -> bytes:
        return (
            b'{"status":"error","code":"PRECONDITION_FAILED",'
            b'"message":"slot is not empty",'
            b'"details":{"bridge_stage":"precondition"}}\n'
        )


def capable_status(epoch: int = 1) -> dict[str, object]:
    return NewBridgeFixture({"run_batch_preconditions": "v1"}).capable_status(epoch)


def precondition_failed_response() -> bytes:
    return NewBridgeFixture({"run_batch_preconditions": "v1"}).precondition_failed_response()


__all__ = ["FakeSocket", "NewBridgeFixture", "capable_status", "precondition_failed_response"]
