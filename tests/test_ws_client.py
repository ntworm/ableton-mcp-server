from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from ableton_mcp_server.client import Client
from ableton_mcp_server.errors import ExtensionUnavailableError
from ableton_mcp_server.ws_client import WSClient


@pytest.mark.asyncio
async def test_ws_client_success() -> None:
    client = WSClient()

    # Mock websockets connect and connection objects
    mock_connection = AsyncMock()
    mock_connection.__aenter__.return_value = mock_connection
    mock_connection.recv = AsyncMock(
        return_value=json.dumps(
            {"jsonrpc": "2.0", "result": {"warping": True, "warp_mode": "complex"}, "id": 1}
        )
    )
    mock_connection.send = AsyncMock()

    with patch("websockets.asyncio.client.connect", return_value=mock_connection) as mock_connect:
        res = await client.call("get_warp_state", {"track_index": 0, "clip_index": 0})
        assert res["warping"] is True
        assert res["warp_mode"] == "complex"

        # Verify it was called with the correct URI and payload
        mock_connect.assert_called_once_with(
            "ws://127.0.0.1:9889", open_timeout=3.0, close_timeout=2.0
        )
        sent_payload = json.loads(mock_connection.send.call_args[0][0])
        assert sent_payload["method"] == "get_warp_state"
        assert sent_payload["params"] == {"track_index": 0, "clip_index": 0}


@pytest.mark.asyncio
async def test_ws_client_error_response() -> None:
    client = WSClient()

    mock_connection = AsyncMock()
    mock_connection.__aenter__.return_value = mock_connection
    mock_connection.recv = AsyncMock(
        return_value=json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "Clip is not an audio clip"},
                "id": 1,
            }
        )
    )

    with (
        patch("websockets.asyncio.client.connect", return_value=mock_connection),
        pytest.raises(Exception, match="Clip is not an audio clip"),
    ):
        await client.call("get_warp_state", {"track_index": 0, "clip_index": 0})


@pytest.mark.asyncio
async def test_ws_client_preserves_structured_extension_error() -> None:
    client = WSClient()
    from ableton_mcp_server.errors import CapabilityUnavailableError

    mock_connection = AsyncMock()
    mock_connection.__aenter__.return_value = mock_connection
    mock_connection.recv = AsyncMock(
        return_value=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "Audio clip warp markers are read-only",
                    "data": {
                        "code": "CAPABILITY_UNAVAILABLE",
                        "hint": "Use get_warp_state",
                    },
                },
            }
        )
    )

    with patch("websockets.asyncio.client.connect", return_value=mock_connection):
        with pytest.raises(CapabilityUnavailableError) as exc_info:
            await client.call("get_warp_state", {"track_index": 0, "clip_index": 0})

    assert exc_info.value.code == "CAPABILITY_UNAVAILABLE"
    assert exc_info.value.hint == "Use get_warp_state"


@pytest.mark.asyncio
async def test_ws_client_unreachable() -> None:
    client = WSClient(port=9999)

    # Simulate connection failure (OSError)
    with patch("websockets.asyncio.client.connect", side_effect=OSError("Connection refused")):
        with pytest.raises(ExtensionUnavailableError) as exc_info:
            await client.call("get_warp_state", {"track_index": 0, "clip_index": 0})

        assert exc_info.value.code == "EXTENSION_UNAVAILABLE"
        assert "9999" in str(exc_info.value)


def test_hybrid_client_routing() -> None:
    client = Client()
    # verify routing checks
    assert client.is_ws_command("get_warp_state")
    assert client.is_ws_command("set_warp_state")
    assert client.is_ws_command("load_device_to_track")
    assert not client.is_ws_command("get_session_info")
    assert not client.is_ws_command("create_midi_track")
