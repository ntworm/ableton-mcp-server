from __future__ import annotations

from AbletonMCPServer_RemoteScript import execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def call(command: str, params: dict[str, object] | None = None) -> object:
    return execute_command(FakeSong(), FakeApplication(), command, params or {})


def test_session_track_and_project_reads() -> None:
    session = call("get_session_info")
    assert isinstance(session, dict)
    assert session["tempo"] == 120.0
    assert session["signature_numerator"] == 4

    tracks = call("get_track_list")
    assert isinstance(tracks, list)
    assert [track["type"] for track in tracks] == ["midi", "return", "master"]
    assert tracks[0]["id"] == "track:0"

    metadata = call("get_project_metadata")
    assert metadata == {
        "song_name": "Debug Set",
        "file_path": r"C:\Music\Debug Set.als",
        "is_dirty": False,
    }
    assert call("get_song_length") == {"song_length": 64.25}


def test_track_device_parameter_clip_and_routing_reads() -> None:
    track = call("get_track_state", {"track_index": 0})
    assert isinstance(track, dict)
    assert track["id"] == "track:0"
    assert track["devices"][0]["id"] == "track:0/device:0"
    assert track["clip_slots"][0]["id"] == "track:0/clipslot:0"

    devices = call("get_device_list", {"track_index": 0})
    assert devices[0]["parameters"][1]["id"] == "track:0/device:0/param:1"

    parameter = call(
        "get_parameter_value",
        {"track_index": 0, "device_index": 0, "parameter_name": "Filter Freq"},
    )
    assert parameter["value"] == 0.5

    clips = call("get_clip_summary", {"track_index": 0})
    assert clips[0]["clip_id"] == "track:0/clipslot:0/clip"
    notes = call("get_clip_notes", {"track_index": 0, "clip_index": 0})
    assert notes == [
        {"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100, "mute": False}
    ]
    assert call("get_routing", {"track_index": 0})["output_routing"] == "Master"


def test_context_scene_locator_browser_and_control_surface_reads() -> None:
    assert call("get_selected_context")["selected_track_id"] == "track:0"
    assert call("get_scenes") == [{"index": 0, "name": "Verse", "is_empty": False}]
    scene = call("get_scene_state", {"scene_index": 0})
    assert scene["clip_slots"][0]["track_id"] == "track:0"
    assert call("get_locators") == []
    assert "Instruments" in call("get_browser_categories")
    assert call("get_control_surfaces")[0]["type"] == "remote_script"
    assert call("get_loop_settings") == {
        "loop": False,
        "loop_start": 0.0,
        "loop_length": 4.0,
    }


def test_path_reads_resolve_against_current_state() -> None:
    matches = call("live_find_track", {"query": "bass"})
    assert matches == [
        {
            "id": "track:0",
            "index": 0,
            "name": "Bass",
            "type": "midi",
            "color": 0x336699,
            "color_index": 0,
            "is_group_track": False,
            "is_grouped": False,
            "group_track_index": None,
            "group_track_id": None,
            "is_visible": True,
            "fold_state": 0,
        }
    ]
    params = call("list_device_params", {"track_id": "track:0"})
    assert params[0]["device_id"] == "track:0/device:0"
    assert params[0]["parameters"][0]["id"] == "track:0/device:0/param:0"


def test_snapshot_has_epoch_timestamp_and_all_debug_sections(monkeypatch: object) -> None:
    monkeypatch.setattr("AbletonMCPServer_RemoteScript.time.time", lambda: 123.456)  # type: ignore[attr-defined]
    snapshot = call("take_snapshot")
    assert snapshot["captured_at_unix_ms"] == 123456
    assert snapshot["live_version"] == "12.4.5"
    assert snapshot["locators"] == []
    assert snapshot["scenes"][0]["name"] == "Verse"
