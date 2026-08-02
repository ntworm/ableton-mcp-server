from __future__ import annotations

import pytest

from ableton_mcp_server.client import Client
from ableton_mcp_server.errors import ReadOnlyViolation
from scripts.mock_remote_script import run_mock_server


def test_real_jsonl_socket_round_trip_is_stateful() -> None:
    server = run_mock_server(port=0)
    client = Client(port=server.port, reconnect=False)
    try:
        assert client.call("get_session_info")["tempo"] == 120.0
        assert client.call("set_tempo", {"tempo": 128.0}) == {
            "tempo": 128.0,
            "resolved": {"kind": "tempo", "tempo": 128.0},
        }
        assert client.call("take_snapshot")["tempo"] == 128.0
        assert client.call("live_find_track", {"query": "bass"}) == [
            {"id": "track:0", "index": 0, "name": "Bass", "type": "midi"}
        ]
        with pytest.raises(ReadOnlyViolation):
            client.call("delete_track", {"track_index": 0})
    finally:
        client.close()
        server.stop()


def test_mock_returns_unknown_command_error() -> None:
    server = run_mock_server(port=0)
    client = Client(port=server.port, reconnect=False)
    try:
        with pytest.raises(Exception, match="UNKNOWN_COMMAND|not implemented"):
            client.call("not_a_command")
    finally:
        client.close()
        server.stop()
