from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client as FastMCPClient

import ableton_mcp_server.server as server

FORWARD_CASES: list[tuple[Callable[..., Any], tuple[Any, ...], str, dict[str, Any]]] = [
    (server.get_session_info, (), "get_session_info", {}),
    (server.get_track_list, (), "get_track_list", {}),
    (server.get_track_state, (1,), "get_track_state", {"track_index": 1}),
    (server.get_locators, (), "get_locators", {}),
    (server.take_snapshot, (), "take_snapshot", {}),
    (server.get_control_surfaces, (), "get_control_surfaces", {}),
    (server.get_scenes, (), "get_scenes", {}),
    (server.get_scene_state, (2,), "get_scene_state", {"scene_index": 2}),
    (server.get_project_metadata, (), "get_project_metadata", {}),
    (server.get_loop_settings, (), "get_loop_settings", {}),
    (server.get_selected_context, (), "get_selected_context", {}),
    (server.get_clip_summary, (1,), "get_clip_summary", {"track_index": 1}),
    (
        server.get_clip_notes,
        (1, 2),
        "get_clip_notes",
        {"track_index": 1, "clip_index": 2},
    ),
    (server.get_device_list, (1,), "get_device_list", {"track_index": 1}),
    (
        server.get_parameter_value,
        (1, 2, "Cutoff"),
        "get_parameter_value",
        {"track_index": 1, "device_index": 2, "parameter_name": "Cutoff"},
    ),
    (
        server.set_parameter_value,
        (1, 2, "Cutoff", 0.75),
        "set_parameter_value",
        {
            "track_index": 1,
            "device_index": 2,
            "parameter_name": "Cutoff",
            "value": 0.75,
        },
    ),
    (server.get_routing, (1,), "get_routing", {"track_index": 1}),
    (server.get_browser_categories, (), "get_browser_categories", {}),
    (server.get_song_length, (), "get_song_length", {}),
    (server.live_find_track, ("Bass",), "live_find_track", {"query": "Bass"}),
    (
        server.list_device_params,
        ("track:1",),
        "list_device_params",
        {"track_id": "track:1"},
    ),
    (
        server.create_cue_point,
        ("Verse", 8),
        "create_cue_point",
        {"name": "Verse", "time": 8.0},
    ),
    (
        server.bulk_create_cue_points,
        ([{"name": "Verse", "time": 8}],),
        "bulk_create_cue_points",
        {"items": [{"name": "Verse", "time": 8.0}]},
    ),
    (server.delete_cue_point, (8,), "delete_cue_point", {"time": 8.0}),
    (
        server.set_current_song_time,
        (8,),
        "set_current_song_time",
        {"time": 8.0},
    ),
    (server.set_tempo, (128,), "set_tempo", {"tempo": 128.0}),
    (server.start_playback, (), "start_playback", {}),
    (server.stop_playback, (), "stop_playback", {}),
    (server.set_loop, (True,), "set_loop", {"enabled": True}),
    (server.set_loop_start, (4,), "set_loop_start", {"start_beat": 4.0}),
    (
        server.set_loop_length,
        (8,),
        "set_loop_length",
        {"length_beats": 8.0},
    ),
    (
        server.run_batch,
        ([{"type": "set_tempo", "params": {"tempo": 128.0}}],),
        "run_batch",
        {"commands": [{"type": "set_tempo", "params": {"tempo": 128.0}}]},
    ),
    (
        server.add_notes_to_clip,
        (0, 1, [{"pitch": 60, "start_time": 0, "duration": 1}]),
        "add_notes_to_clip",
        {
            "track_index": 0,
            "clip_index": 1,
            "notes": [
                {
                    "pitch": 60,
                    "start_time": 0.0,
                    "duration": 1.0,
                    "velocity": 100,
                    "mute": False,
                }
            ],
        },
    ),
    (server.fire_clip, (0, 1), "fire_clip", {"track_index": 0, "clip_index": 1}),
    (
        server.create_clip,
        (0, 1, 4),
        "create_clip",
        {"track_index": 0, "clip_index": 1, "length_beats": 4.0},
    ),
    (server.get_composition_structure, (), "get_composition_structure", {}),
    (
        server.diagnose_midi_clip,
        (0, 1, "C", "major"),
        "diagnose_midi_clip",
        {"track_index": 0, "clip_index": 1, "scale_root": "C", "scale_type": "major"},
    ),
    (
        server.create_midi_track,
        ("Bass", 1),
        "create_midi_track",
        {"name": "Bass", "index": 1},
    ),
    (server.rename_track, (0, "Drums"), "rename_track", {"track_index": 0, "new_name": "Drums"}),
]


@patch("ableton_mcp_server.server.bridge_status")
def test_bridge_status_tool_probes_the_backend_without_forwarding(
    mock_status: MagicMock,
) -> None:
    mock_status.return_value = {"status": "ok", "bridge_available": True}
    assert server.get_bridge_status() == {"status": "ok", "bridge_available": True}
    mock_status.assert_called_once_with(server.get_client(), tool_count=58)


@pytest.mark.parametrize(("function", "args", "command", "params"), FORWARD_CASES)
@patch("ableton_mcp_server.server.get_client")
def test_remote_tools_validate_and_forward_exact_contract(
    mock_get_client: MagicMock,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    command: str,
    params: dict[str, Any],
) -> None:
    client = MagicMock()
    client.call.return_value = {"forwarded": command}
    mock_get_client.return_value = client
    assert function(*args) == {"forwarded": command}
    client.call.assert_called_once_with(command, params)


def test_diff_tool_is_local_and_deterministic() -> None:
    assert server.diff_snapshots_tool({"tempo": 120.0}, {"tempo": 128.0}) == {
        "added": [],
        "removed": [],
        "changed": [{"path": "tempo", "before": 120.0, "after": 128.0}],
    }


@pytest.mark.asyncio
@patch("ableton_mcp_server.server._remote_ws")
async def test_websocket_tools_validate_and_forward_exact_contract(
    mock_remote_ws: MagicMock,
) -> None:
    mock_remote_ws.side_effect = [
        {"warping": True},
        {"warping": False},
        {"device_id": "track:0/device:1"},
    ]

    assert json.loads(await server.get_warp_state(0, 1)) == {"warping": True}
    assert json.loads(await server.set_warp_state(0, 1, False, "complex")) == {
        "warping": False
    }
    assert json.loads(await server.load_device_to_track(0, " Operator ")) == {
        "device_id": "track:0/device:1"
    }
    assert [call.args for call in mock_remote_ws.await_args_list] == [
        ("get_warp_state", {"track_index": 0, "clip_index": 1}),
        (
            "set_warp_state",
            {
                "track_index": 0,
                "clip_index": 1,
                "warping": False,
                "warp_mode": "complex",
            },
        ),
        ("load_device_to_track", {"track_index": 0, "device_uri": "Operator"}),
    ]


@pytest.mark.asyncio
@patch("ableton_mcp_server.server.get_client")
async def test_empty_remote_list_remains_an_explicit_json_array_over_mcp(
    mock_get_client: MagicMock,
) -> None:
    mock_get_client.return_value.call.return_value = []

    async with FastMCPClient(server.mcp) as client:
        result = await client.call_tool(
            "get_clip_notes",
            {"track_index": 0, "clip_index": 0},
            raise_on_error=False,
        )

    assert result.is_error is False
    assert result.data == []
    assert [block.text for block in result.content if block.type == "text"] == ["[]"]


@pytest.mark.asyncio
@patch("ableton_mcp_server.server.get_client")
async def test_expected_bridge_error_is_a_typed_mcp_result_not_framework_failure(
    mock_get_client: MagicMock,
) -> None:
    from ableton_mcp_server.errors import WrongTypeError

    mock_get_client.return_value.call.side_effect = [
        WrongTypeError("Track has no Session clip slots."),
        {"tempo": 120.0},
    ]

    async with FastMCPClient(server.mcp) as client:
        rejected = await client.call_tool(
            "get_clip_summary", {"track_index": 3}, raise_on_error=False
        )
        recovered = await client.call_tool("get_session_info", {}, raise_on_error=False)

    assert rejected.is_error is True
    assert rejected.structured_content == {
        "status": "error",
        "code": "WRONG_TYPE",
        "message": "Track has no Session clip slots.",
    }
    assert recovered.is_error is False
    assert recovered.data == {"tempo": 120.0}


@patch("ableton_mcp_server.server.find_ableton_log_path")
def test_log_tool_limits_lines_and_reads_locally(mock_find: MagicMock, tmp_path: Any) -> None:
    log = tmp_path / "Log.txt"
    log.write_text("one\ntwo\nthree\n", encoding="utf-8")
    mock_find.return_value = log
    assert server.get_ableton_logs(2) == "two\nthree\n"


def test_every_tool_docstring_has_contract_sections() -> None:
    assert len(server.PUBLIC_TOOL_FUNCTIONS) == 58
    for function in server.PUBLIC_TOOL_FUNCTIONS:
        docstring = function.__doc__ or ""
        assert "Side effects:" in docstring, function.__name__
        assert "Example:" in docstring, function.__name__
        assert "Edge cases:" in docstring, function.__name__
