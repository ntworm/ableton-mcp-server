from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from ableton_mcp_server.models import (
    AutomationPoint,
    SearchBrowserRequest,
    SetClipPropertiesRequest,
    SetParameterValueRequest,
)
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from tests.remote_fakes import FakeApplication, FakeBrowser, FakeClipSlot, FakeSong


def _assert_remote_error(command: str, params: dict[str, object], code: str) -> None:
    with pytest.raises(RemoteError) as error:
        execute_command(FakeSong(), FakeApplication(), command, params)
    assert error.value.code == code


def _automation_params() -> dict[str, object]:
    return {
        "track_index": 0,
        "clip_index": 0,
        "parameter_name": "Filter Freq",
        "automation_points": [{"time": 0.0, "value": 0.5}],
    }


def test_parameter_write_rejects_missing_device_without_suggestion() -> None:
    _assert_remote_error(
        "set_parameter_value",
        {
            "track_index": 0,
            "device_index": 99,
            "parameter_name": "Missing",
            "value": 0.5,
        },
        "INVALID_PARAMS",
    )
    _assert_remote_error(
        "set_parameter_value",
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_name": "Completely Unrelated",
            "value": 0.5,
        },
        "INVALID_PARAMS",
    )


def test_parameter_write_accepts_quantized_observed_value() -> None:
    song = FakeSong()
    parameter = song.tracks[0].devices[0].parameters[0]
    parameter.is_quantized = True
    result = execute_command(
        song,
        FakeApplication(),
        "set_parameter_value",
        {
            "track_index": 0,
            "device_index": 0,
            "parameter_name": "Device On",
            "value": 0.0,
        },
    )
    assert result["is_quantized"] is True


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"track_index": 0, "property": "unknown", "value": True}, "BAD_INPUT"),
        ({"track_index": 0, "property": "mute", "value": 1}, "INVALID_PARAMS"),
    ],
)
def test_track_property_remote_validation(params: dict[str, object], code: str) -> None:
    _assert_remote_error("set_track_property", params, code)


def test_clip_property_empty_slot_and_partial_updates() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]
    with pytest.raises(RemoteError) as error:
        execute_command(
            song,
            FakeApplication(),
            "set_clip_properties",
            {"track_index": 0, "clip_index": 0, "name": "Empty"},
        )
    assert error.value.code == "BAD_INPUT"

    result = execute_command(
        FakeSong(),
        FakeApplication(),
        "set_clip_properties",
        {"track_index": 0, "clip_index": 0, "loop_end": 12.0},
    )
    assert result["loop_end"] == 12.0

    renamed = execute_command(
        FakeSong(),
        FakeApplication(),
        "set_clip_properties",
        {"track_index": 0, "clip_index": 0, "name": "Only Name"},
    )
    assert renamed["name"] == "Only Name"


def test_automation_rejects_invalid_remote_shapes_and_targets() -> None:
    _assert_remote_error(
        "create_clip_automation",
        {**_automation_params(), "automation_points": []},
        "INVALID_PARAMS",
    )
    _assert_remote_error(
        "create_clip_automation",
        {**_automation_params(), "automation_points": ["bad"]},
        "INVALID_PARAMS",
    )
    _assert_remote_error(
        "create_clip_automation",
        {**_automation_params(), "parameter_name": "Missing"},
        "INVALID_PARAMS",
    )


def test_automation_rejects_empty_arrangement_and_disabled_targets() -> None:
    song = FakeSong()
    song.tracks[0].clip_slots = [FakeClipSlot()]
    with pytest.raises(RemoteError) as empty_error:
        execute_command(song, FakeApplication(), "create_clip_automation", _automation_params())
    assert empty_error.value.code == "BAD_INPUT"

    song = FakeSong()
    song.tracks[0].clip_slots[0].clip.is_session_clip = False
    with pytest.raises(RemoteError) as arrangement_error:
        execute_command(song, FakeApplication(), "create_clip_automation", _automation_params())
    assert arrangement_error.value.code == "WRONG_TYPE"

    song = FakeSong()
    song.tracks[0].devices[0].parameters[1].is_enabled = False
    with pytest.raises(RemoteError) as disabled_error:
        execute_command(song, FakeApplication(), "create_clip_automation", _automation_params())
    assert disabled_error.value.code == "WRONG_TYPE"


def test_automation_reports_insertion_and_readback_capability_failures() -> None:
    song = FakeSong()
    clip = song.tracks[0].clip_slots[0].clip
    clip.automation_envelope = lambda _parameter: object()
    clip.create_automation_envelope = lambda _parameter: object()
    clip.clear_envelope = lambda _parameter: None
    with pytest.raises(RemoteError) as insertion_error:
        execute_command(song, FakeApplication(), "create_clip_automation", _automation_params())
    assert insertion_error.value.code == "LIVE_UNAVAILABLE"

    class SilentEnvelope:
        def insert_step(self, _time: float, _duration: float, _value: float) -> None:
            return None

    song = FakeSong()
    clip = song.tracks[0].clip_slots[0].clip
    clip.automation_envelope = lambda _parameter: SilentEnvelope()
    clip.create_automation_envelope = lambda _parameter: SilentEnvelope()
    clip.clear_envelope = lambda _parameter: None
    clip.has_envelopes = False
    with pytest.raises(RemoteError) as readback_error:
        execute_command(song, FakeApplication(), "create_clip_automation", _automation_params())
    assert readback_error.value.code == "LIVE_UNAVAILABLE"


def test_browser_and_model_edge_validation() -> None:
    app = FakeApplication(browser=FakeBrowser.with_operator())
    with pytest.raises(RemoteError) as limit_error:
        execute_command(FakeSong(), app, "search_browser", {"query": "x", "limit": True})
    assert limit_error.value.code == "INVALID_PARAMS"

    with pytest.raises(RemoteError) as category_error:
        execute_command(
            FakeSong(),
            app,
            "search_browser",
            {"query": "x", "category_type": "unknown"},
        )
    assert category_error.value.code == "INVALID_PARAMS"

    for factory in (
        lambda: SearchBrowserRequest(query=" "),
        lambda: SearchBrowserRequest(query="x", category_type=" "),
        lambda: SetClipPropertiesRequest(track_index=0, clip_index=0),
        lambda: SetClipPropertiesRequest(track_index=0, clip_index=0, loop_start=2, loop_end=1),
        lambda: SetParameterValueRequest(
            track_index=0,
            device_index=0,
            parameter_name="x",
            value=math.nan,
        ),
        lambda: AutomationPoint(time=0, value=math.inf),
    ):
        with pytest.raises(ValidationError):
            factory()
