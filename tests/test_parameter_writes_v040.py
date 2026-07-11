from __future__ import annotations

import pytest

from ableton_mcp_server.models import RunBatchRequest
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeSong


def _params(*, name: str = "Filter Freq", value: float = 0.75) -> dict[str, object]:
    return {
        "track_index": 0,
        "device_index": 0,
        "parameter_name": name,
        "value": value,
    }


def test_set_parameter_value_writes_and_returns_observed_value() -> None:
    song = FakeSong()
    result = execute_command(song, FakeApplication(), "set_parameter_value", _params())

    assert result == {"target": 0.75, "value": 0.75, "is_quantized": False}
    assert song.tracks[0].devices[0].parameters[1].value == 0.75


def test_set_parameter_value_rejects_out_of_range_value() -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "set_parameter_value",
            _params(value=1.5),
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "outside [0.0, 1.0]" in str(error.value)


def test_set_parameter_value_suggests_close_parameter_name() -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(
            FakeSong(),
            FakeApplication(),
            "set_parameter_value",
            _params(name="Filter Frek"),
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "Filter Freq" in str(error.value)


def test_set_parameter_value_rejects_disabled_parameter() -> None:
    song = FakeSong()
    song.tracks[0].devices[0].parameters[1].is_enabled = False

    with pytest.raises(RemoteError) as error:
        execute_command(song, FakeApplication(), "set_parameter_value", _params())

    assert error.value.code == "WRONG_TYPE"
    assert "disabled" in str(error.value)


def test_set_parameter_value_is_valid_in_run_batch() -> None:
    request = RunBatchRequest(
        commands=[{"type": "set_parameter_value", "params": _params(value=0.5)}]
    )
    assert request.commands[0].type == "set_parameter_value"

    song = FakeSong()
    app = FakeApplication()
    result = execute_command(song, app, "run_batch", request.model_dump(mode="json"))
    assert result["completed"] == 1
    assert result["results"][0]["result"]["value"] == 0.5
    assert (app.begin_count, app.end_count) == (1, 1)
