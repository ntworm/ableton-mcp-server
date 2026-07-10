from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class ProtocolError(Exception):
    """Raised when a JSONL request or response violates the bridge contract."""


@dataclass(frozen=True)
class Response:
    status: str
    result: Any = None
    code: str | None = None
    message: str | None = None
    hint: str | None = None


def _decode_object(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8").strip()
        if not text:
            raise ProtocolError("Empty JSONL frame")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Invalid JSONL frame: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolError("JSONL frame must be an object")
    return value


def encode_request(request_type: str, params: Mapping[str, Any] | None = None) -> bytes:
    if not request_type or not request_type.strip():
        raise ProtocolError("Request type must be a non-empty string")
    payload = {"type": request_type, "params": dict(params or {})}
    try:
        return (json.dumps(payload) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Request is not JSON serializable: {exc}") from exc


def decode_request(data: bytes) -> tuple[str, dict[str, Any]]:
    value = _decode_object(data)
    request_type = value.get("type")
    params = value.get("params", {})
    if not isinstance(request_type, str) or not request_type.strip():
        raise ProtocolError("Request is missing a non-empty 'type'")
    if not isinstance(params, dict):
        raise ProtocolError("Request 'params' must be an object")
    return request_type, params


def encode_response(response: Mapping[str, Any]) -> bytes:
    decode_response((json.dumps(dict(response)) + "\n").encode("utf-8"))
    return (json.dumps(dict(response)) + "\n").encode("utf-8")


def decode_response(data: bytes) -> Response:
    value = _decode_object(data)
    status = value.get("status")
    if status == "ok":
        if "result" not in value:
            raise ProtocolError("Success response is missing 'result'")
        return Response(status="ok", result=value["result"])
    if status == "error":
        code = value.get("code")
        message = value.get("message")
        hint = value.get("hint")
        if not isinstance(code, str) or not code:
            raise ProtocolError("Error response is missing 'code'")
        if not isinstance(message, str) or not message:
            raise ProtocolError("Error response is missing 'message'")
        if hint is not None and not isinstance(hint, str):
            raise ProtocolError("Error response 'hint' must be a string")
        return Response(status="error", code=code, message=message, hint=hint)
    raise ProtocolError("Response 'status' must be 'ok' or 'error'")
