from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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
]


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


@patch("ableton_mcp_server.server.find_ableton_log_path")
def test_log_tool_limits_lines_and_reads_locally(mock_find: MagicMock, tmp_path: Any) -> None:
    log = tmp_path / "Log.txt"
    log.write_text("one\ntwo\nthree\n", encoding="utf-8")
    mock_find.return_value = log
    assert server.get_ableton_logs(2) == "two\nthree\n"


def test_every_tool_docstring_has_contract_sections() -> None:
    assert len(server.PUBLIC_TOOL_FUNCTIONS) == 36
    for function in server.PUBLIC_TOOL_FUNCTIONS:
        docstring = function.__doc__ or ""
        assert "Side effects:" in docstring, function.__name__
        assert "Example:" in docstring, function.__name__
        assert "Edge cases:" in docstring, function.__name__
