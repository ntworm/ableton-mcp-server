from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from AbletonMCPServer_RemoteScript import (
    RemoteError,
    _dbg,
    _safe,
    execute_command,
)
from tests.remote_fakes import FakeApplication, FakeClip, FakeClipSlot, FakeSong


def test_remote_error_envelope_includes_optional_hint() -> None:
    error = RemoteError("CODE", "message", "recover")
    assert error.to_envelope() == {
        "status": "error",
        "code": "CODE",
        "message": "message",
        "hint": "recover",
    }


def test_verbose_logging_uses_stable_mcp_server_prefix() -> None:
    with (
        patch("AbletonMCPServer_RemoteScript._VERBOSE", True),
        patch("AbletonMCPServer_RemoteScript.logger.info") as info,
    ):
        _dbg("startup endpoint=127.0.0.1:9888")
    info.assert_called_once_with("[MCP-Server] %s", "startup endpoint=127.0.0.1:9888")
    assert RemoteError("CODE", "message").to_envelope() == {
        "status": "error",
        "code": "CODE",
        "message": "message",
    }


def test_safe_catches_live_style_runtime_errors() -> None:
    def fail() -> Any:
        raise RuntimeError("property unavailable")

    assert _safe(fail, "fallback") == "fallback"


@pytest.mark.parametrize(
    ("command", "params", "code"),
    [
        ("get_track_state", {"track_index": 99}, "INVALID_PARAMS"),
        ("list_device_params", {"track_id": "track:99"}, "STALE_REFERENCE"),
        ("list_device_params", {"track_id": "bad"}, "BAD_INPUT"),
        ("get_clip_summary", {"track_index": 1}, "WRONG_TYPE"),
        ("get_scene_state", {"scene_index": 9}, "INVALID_PARAMS"),
        (
            "get_parameter_value",
            {"track_index": 0, "device_index": 9, "parameter_name": "x"},
            "INVALID_PARAMS",
        ),
        (
            "get_parameter_value",
            {"track_index": 0, "device_index": 0, "parameter_name": "missing"},
            "INVALID_PARAMS",
        ),
        ("delete_track", {}, "READ_ONLY_VIOLATION"),
        ("future_command", {}, "UNKNOWN_COMMAND"),
    ],
)
def test_dispatcher_returns_precise_error_categories(
    command: str, params: dict[str, object], code: str
) -> None:
    with pytest.raises(RemoteError) as exc_info:
        execute_command(FakeSong(), FakeApplication(), command, params)
    assert exc_info.value.code == code


def test_playback_loop_and_tempo_mutations_return_observed_state() -> None:
    song = FakeSong()
    app = FakeApplication()
    assert execute_command(song, app, "start_playback", {}) == {"is_playing": True}
    assert execute_command(song, app, "stop_playback", {}) == {"is_playing": False}
    assert execute_command(song, app, "set_loop", {"enabled": True}) == {"loop": True}
    assert execute_command(song, app, "set_tempo", {"tempo": 140}) == {"tempo": 140.0}
    assert (app.begin_count, app.end_count) == (4, 4)


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("set_loop", {"enabled": 1}),
        ("set_tempo", {"tempo": 1000}),
        ("set_tempo", {"tempo": float("nan")}),
        ("create_clip", {"track_index": 1, "clip_index": 0, "length_beats": 4}),
        ("add_notes_to_clip", {"track_index": 0, "clip_index": 0, "notes": []}),
    ],
)
def test_mutation_validation_fails_before_lom_call(command: str, params: dict[str, object]) -> None:
    with pytest.raises(RemoteError):
        execute_command(FakeSong(), FakeApplication(), command, params)


def test_audio_clip_note_read_and_write_are_wrong_type() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot(FakeClip(midi=False))]
    with pytest.raises(RemoteError, match="not a MIDI"):
        execute_command(
            song, FakeApplication(), "get_clip_notes", {"track_index": 0, "clip_index": 0}
        )
    with pytest.raises(RemoteError, match="requires a MIDI"):
        execute_command(
            song,
            FakeApplication(),
            "add_notes_to_clip",
            {
                "track_index": 0,
                "clip_index": 0,
                "notes": [{"pitch": 60, "start_time": 0, "duration": 1}],
            },
        )


def test_cue_delete_miss_and_bulk_bad_item() -> None:
    song = FakeSong()
    app = FakeApplication()
    assert execute_command(song, app, "delete_cue_point", {"time": 8}) == {
        "deleted": False,
        "reason": "no cue at time",
    }
    bulk = execute_command(song, app, "bulk_create_cue_points", {"items": ["bad"]})
    assert bulk["results"][0]["code"] == "INVALID_PARAMS"


def test_batch_rejects_nested_and_non_object_subcommands() -> None:
    song = FakeSong()
    app = FakeApplication()
    nested = execute_command(
        song,
        app,
        "run_batch",
        {"commands": [{"type": "run_batch", "params": {}}]},
    )
    assert nested["aborted_at"] == 0
    assert nested["results"][0]["code"] == "BAD_INPUT"
    malformed = execute_command(song, app, "run_batch", {"commands": ["bad"]})
    assert malformed["results"][0]["code"] == "INVALID_PARAMS"
