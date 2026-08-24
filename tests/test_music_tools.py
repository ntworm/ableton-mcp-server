from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.tools import ToolResult
from mcp.types import TextContent

import ableton_mcp_server.server as server


def _payload(result: ToolResult) -> Any:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return json.loads(content.text)


@patch("ableton_mcp_server.server.get_client")
def test_generation_without_apply_never_touches_the_bridge(
    mock_get_client: MagicMock,
) -> None:
    result = _payload(server.music_generate_drum_groove(bars=2, seed=5))

    assert result["applied"] is False
    assert result["notes"]
    assert result["traits_applied"] == []
    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_apply_writes_the_clip_and_the_notes_in_one_undo_step(
    mock_get_client: MagicMock,
) -> None:
    mock_get_client.return_value.call.return_value = {"ok": True}

    _payload(
        server.music_generate_drum_groove(
            bars=1, seed=5, apply=True, track_index=3, clip_index=2
        )
    )

    command, request = mock_get_client.return_value.call.call_args.args
    assert command == "run_batch"
    assert [entry["type"] for entry in request["commands"]] == [
        "create_clip",
        "add_notes_to_clip",
    ]
    assert request["commands"][0]["params"]["track_index"] == 3
    assert request["commands"][0]["params"]["clip_index"] == 2


@patch("ableton_mcp_server.server.get_client")
def test_apply_is_refused_without_a_target_slot(mock_get_client: MagicMock) -> None:
    with pytest.raises(Exception, match="track_index"):
        server.music_generate_drum_groove(bars=1, seed=5, apply=True)

    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_bass_generation_reaches_the_engine(mock_get_client: MagicMock) -> None:
    result = _payload(server.music_generate_bass(bars=2, seed=5, root_midi=40))

    assert {note["pitch"] % 12 for note in result["notes"]} == {40 % 12}
    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_plan_production_is_offline_and_reports_gaps(
    mock_get_client: MagicMock,
) -> None:
    result = _payload(server.music_plan_production(prompt="a track at 128 bpm"))

    assert result["bpm"] == 128.0
    assert "bars" in result["unresolved"]
    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_traits_reach_the_engine_and_are_reported_by_name(
    mock_get_client: MagicMock,
) -> None:
    """Traits used to be inert and the response said so. They are live now, and
    the response names exactly which axes moved the notes."""
    plain = _payload(server.music_generate_drum_groove(bars=2, seed=5))
    shaped = _payload(
        server.music_generate_drum_groove(
            bars=2, seed=5, traits={"space": 0.8, "groove": 1.0}
        )
    )

    assert shaped["notes"] != plain["notes"]
    assert set(shaped["traits_applied"]) == {"space", "groove"}
    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_bass_accepts_traits_too(mock_get_client: MagicMock) -> None:
    shaped = _payload(
        server.music_generate_bass(
            bars=4, seed=5, root_midi=40, traits={"weirdness": 1.0}
        )
    )

    assert shaped["traits_applied"] == ["weirdness"]
    assert {int(note["pitch"]) % 12 for note in shaped["notes"]} == {40 % 12}
    mock_get_client.assert_not_called()


@patch("ableton_mcp_server.server.get_client")
def test_an_aborted_batch_is_not_reported_as_applied(
    mock_get_client: MagicMock,
) -> None:
    """A real Live run exposed this: ``create_clip`` refuses an occupied slot,
    the batch aborts with nothing written, and the response still claimed the
    notes had been applied."""
    mock_get_client.return_value.call.return_value = {
        "results": [
            {
                "index": 0,
                "status": "error",
                "code": "BAD_INPUT",
                "message": "Clip slot is not empty.",
            }
        ],
        "completed": 0,
        "aborted_at": 0,
        "rolled_back": False,
    }

    result = _payload(
        server.music_generate_drum_groove(
            bars=1, seed=5, apply=True, track_index=0, clip_index=0
        )
    )

    assert result["applied"] is False
    assert result["bridge"]["results"][0]["message"] == "Clip slot is not empty."
