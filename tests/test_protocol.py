from __future__ import annotations

import pytest

from ableton_mcp_server.protocol import (
    ProtocolError,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)


def test_request_round_trip_preserves_jsonl_envelope() -> None:
    encoded = encode_request("set_tempo", {"tempo": 128.0})
    assert encoded == b'{"type": "set_tempo", "params": {"tempo": 128.0}}\n'
    assert decode_request(encoded) == ("set_tempo", {"tempo": 128.0})


def test_success_response_round_trip() -> None:
    encoded = encode_response({"status": "ok", "result": {"tempo": 128.0}})
    response = decode_response(encoded)
    assert response.status == "ok"
    assert response.result == {"tempo": 128.0}
    assert response.code is None
    assert response.hint is None


def test_error_response_preserves_hint() -> None:
    response = decode_response(
        b'{"status": "error", "code": "STALE_REFERENCE", '
        b'"message": "track:9 is stale", "hint": "Re-list tracks"}\n'
    )
    assert response.code == "STALE_REFERENCE"
    assert response.message == "track:9 is stale"
    assert response.hint == "Re-list tracks"


@pytest.mark.parametrize(
    "payload",
    [
        b"\n",
        b"[]\n",
        b'{"params": {}}\n',
        b'{"type": "get_session_info", "params": []}\n',
        b'{"status": "maybe", "result": null}\n',
        b'{"status": "error", "message": "missing code"}\n',
    ],
)
def test_invalid_envelopes_raise_protocol_error(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        if b'"status"' in payload:
            decode_response(payload)
        else:
            decode_request(payload)
