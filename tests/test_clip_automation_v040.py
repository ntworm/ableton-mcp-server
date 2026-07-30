from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import ableton_mcp_server.server as server
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def _params(parameter_name: str = "Filter Freq") -> dict[str, object]:
    return {
        "track_index": 0,
        "clip_index": 0,
        "parameter_name": parameter_name,
        "automation_points": [
            {"time": 2.0, "value": 0.8},
            {"time": 0.0, "value": 0.2},
        ],
    }


def test_create_clip_automation_clears_and_inserts_sorted_steps() -> None:
    song = FakeSong()

    result = execute_command(
        song,
        FakeApplication(),
        "create_clip_automation",
        _params(),
    )

    assert result == {
        "parameter_name": "Filter Freq",
        "points_written": 2,
        "times": [0.0, 2.0],
        "clip_id": "track:0/clipslot:0/clip",
    }
    clip = song.tracks[0].clip_slots[0].clip
    parameter = song.tracks[0].devices[0].parameters[1]
    assert clip.automation_envelope(parameter).steps == [
        (0.0, 0.0, 0.2),
        (2.0, 0.0, 0.8),
    ]


def test_create_clip_automation_resolves_mixer_alias() -> None:
    result = execute_command(
        FakeSong(),
        FakeApplication(),
        "create_clip_automation",
        _params("volume"),
    )
    assert result["parameter_name"] == "Volume"


def test_create_clip_automation_rejects_out_of_bounds_value() -> None:
    params = _params()
    params["automation_points"] = [{"time": 0.0, "value": 2.0}]

    with pytest.raises(RemoteError) as error:
        execute_command(FakeSong(), FakeApplication(), "create_clip_automation", params)

    assert error.value.code == "INVALID_PARAMS"


def test_create_clip_automation_reports_missing_host_capability() -> None:
    song = FakeSong()
    clip = song.tracks[0].clip_slots[0].clip
    clip.automation_envelope = None
    clip.create_automation_envelope = None

    with pytest.raises(RemoteError) as error:
        execute_command(song, FakeApplication(), "create_clip_automation", _params())

    assert error.value.code == "LIVE_UNAVAILABLE"
    assert "automation envelope" in str(error.value).lower()


@patch("ableton_mcp_server.server.get_client")
def test_create_clip_automation_forwards_exact_contract(mock_get_client: MagicMock) -> None:
    mock_get_client.return_value.call.return_value = {"ok": True}

    assert server.create_clip_automation(
        1,
        2,
        "Filter Freq",
        [{"time": 0, "value": 0.5}],
    ) == {"ok": True}
    mock_get_client.return_value.call.assert_called_once_with(
        "create_clip_automation",
        {
            "track_index": 1,
            "clip_index": 2,
            "parameter_name": "Filter Freq",
            "automation_points": [{"time": 0.0, "value": 0.5}],
        },
    )
