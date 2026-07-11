from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import ableton_mcp_server.server as server
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def test_set_track_property_verifies_boolean_attribute() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "set_track_property",
        {"track_index": 0, "property": "mute", "value": True},
    )

    assert result == {"property": "mute", "value": True}
    assert song.tracks[0].mute is True


def test_set_track_property_rejects_arm_on_special_track() -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "set_track_property",
            {"track_index": 1, "property": "arm", "value": True},
        )

    assert error.value.code == "WRONG_TYPE"


def test_set_clip_properties_updates_loop_and_name() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "set_clip_properties",
        {
            "track_index": 0,
            "clip_index": 0,
            "loop_start": 1.0,
            "loop_end": 8.0,
            "name": "Verse Loop",
        },
    )

    assert result == {
        "loop_start": 1.0,
        "loop_end": 8.0,
        "name": "Verse Loop",
        "clip_id": "track:0/clipslot:0/clip",
    }


def test_set_clip_properties_rejects_invalid_final_interval() -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "set_clip_properties",
            {
                "track_index": 0,
                "clip_index": 0,
                "loop_start": 8.0,
                "loop_end": 4.0,
            },
        )

    assert error.value.code == "BAD_INPUT"


def test_set_clip_properties_requires_at_least_one_change() -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "set_clip_properties",
            {"track_index": 0, "clip_index": 0},
        )

    assert error.value.code == "INVALID_PARAMS"


@patch("ableton_mcp_server.server.get_client")
def test_property_tools_forward_exact_contract(mock_get_client: MagicMock) -> None:
    mock_get_client.return_value.call.return_value = {"ok": True}

    assert server.set_track_property(1, "solo", True) == {"ok": True}
    assert server.set_clip_properties(1, 2, loop_start=1, name=" Verse ") == {"ok": True}
    assert [call.args for call in mock_get_client.return_value.call.call_args_list] == [
        ("set_track_property", {"track_index": 1, "property": "solo", "value": True}),
        (
            "set_clip_properties",
            {"track_index": 1, "clip_index": 2, "loop_start": 1.0, "name": "Verse"},
        ),
    ]
