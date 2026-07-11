from __future__ import annotations

from unittest.mock import MagicMock, patch

import ableton_mcp_server.server as server
from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeBrowser, FakeClipSlot, FakeSong


def test_get_clip_info_reports_empty_slot() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]

    result = execute_command(
        song,
        FakeApplication(),
        "get_clip_info",
        {"track_index": 0, "clip_index": 0},
    )

    assert result == {"has_clip": False, "clip_id": None}


def test_get_clip_info_returns_stable_metadata() -> None:
    result = execute_command(
        FakeSong(),
        FakeApplication(),
        "get_clip_info",
        {"track_index": 0, "clip_index": 0},
    )

    assert result["has_clip"] is True
    assert result["clip_id"] == "track:0/clipslot:0/clip"
    assert result["name"] == "Clip"
    assert result["length"] == 4.0
    assert result["is_midi_clip"] is True
    assert result["is_audio_clip"] is False


def test_search_browser_is_case_insensitive_and_bounded() -> None:
    app = FakeApplication(browser=FakeBrowser.with_operator())

    result = execute_command(
        FakeSong(),
        app,
        "search_browser",
        {"query": "operator", "limit": 1},
    )

    assert result == [
        {
            "name": "Operator",
            "uri": "query:Instruments#Operator",
            "category": "instruments",
            "path": ["Instruments", "Operator"],
            "is_loadable": True,
        }
    ]


@patch("ableton_mcp_server.server._remote")
def test_get_session_overview_composes_existing_reads(mock_remote: MagicMock) -> None:
    mock_remote.side_effect = [
        {"tempo": 120.0},
        [{"id": "track:0"}],
        [{"index": 0, "name": "Verse"}],
    ]

    assert server.get_session_overview() == {
        "session": {"tempo": 120.0},
        "tracks": [{"id": "track:0"}],
        "scenes": [{"index": 0, "name": "Verse"}],
    }
    assert [call.args[0] for call in mock_remote.call_args_list] == [
        "get_session_info",
        "get_track_list",
        "get_scenes",
    ]


@patch("ableton_mcp_server.server.get_client")
def test_new_remote_read_tools_forward_exact_contract(mock_get_client: MagicMock) -> None:
    mock_get_client.return_value.call.return_value = [{"forwarded": True}]

    assert server.get_clip_info(1, 2) == [{"forwarded": True}]
    assert server.search_browser(" Operator ", "instruments", 25) == [{"forwarded": True}]
    assert mock_get_client.return_value.call.call_args_list[0].args == (
        "get_clip_info",
        {"track_index": 1, "clip_index": 2},
    )
    assert mock_get_client.return_value.call.call_args_list[1].args == (
        "search_browser",
        {"query": "Operator", "category_type": "instruments", "limit": 25},
    )
