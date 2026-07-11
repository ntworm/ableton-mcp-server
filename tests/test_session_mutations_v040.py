from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import ableton_mcp_server.server as server
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeClip, FakeClipSlot, FakeSong


def test_delete_clip_removes_occupied_slot() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "delete_clip",
        {"track_index": 0, "clip_index": 0},
    )

    assert result == {"deleted": True, "clip_id": "track:0/clipslot:0/clip"}
    assert song.tracks[0].clip_slots[0].clip is None


def test_delete_clip_rejects_empty_slot() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "delete_clip",
            {"track_index": 0, "clip_index": 0},
        )

    assert error.value.code == "BAD_INPUT"


def test_clear_clip_notes_returns_observed_delta() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "clear_clip_notes",
        {"track_index": 0, "clip_index": 0},
    )

    assert result == {
        "cleared": True,
        "notes_removed": 1,
        "clip_id": "track:0/clipslot:0/clip",
    }
    assert song.tracks[0].clip_slots[0].clip.notes == []


def test_clear_clip_notes_rejects_audio_clip() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot(FakeClip(midi=False))]

    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "clear_clip_notes",
            {"track_index": 0, "clip_index": 0},
        )

    assert error.value.code == "WRONG_TYPE"


def test_fire_scene_calls_scene_fire() -> None:
    song = FakeSong()

    result = execute_command(song, FakeApplication(), "fire_scene", {"scene_index": 0})

    assert result == {"fired": True, "scene_index": 0, "name": "Verse"}
    assert song.scenes[0].fire_count == 1


@patch("ableton_mcp_server.server.get_client")
def test_simple_mutation_tools_forward_exact_contract(mock_get_client: MagicMock) -> None:
    mock_get_client.return_value.call.return_value = {"ok": True}

    assert server.delete_clip(1, 2) == {"ok": True}
    assert server.clear_clip_notes(1, 2) == {"ok": True}
    assert server.fire_scene(3) == {"ok": True}
    assert [call.args for call in mock_get_client.return_value.call.call_args_list] == [
        ("delete_clip", {"track_index": 1, "clip_index": 2}),
        ("clear_clip_notes", {"track_index": 1, "clip_index": 2}),
        ("fire_scene", {"scene_index": 3}),
    ]
