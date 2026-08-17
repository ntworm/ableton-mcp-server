"""v0.5.4 — plugin preset access and the Configure-gate hint.

Live exposes a plugin's parameters only after the user adds them through the
device's Configure button, so an unconfigured plugin looks parameterless to
every automation surface. These tests pin two consequences: device reads say
so explicitly instead of returning a bare empty list, and preset selection —
the one plugin surface that needs no Configure step — is routed and verified
like any other mutation.
"""

from __future__ import annotations

import pytest

from ableton_mcp_server import models
from ableton_mcp_server.catalog import TOOL_CATALOG
from AbletonMCPServer_RemoteScript import RemoteError, execute_command
from contracts import (
    ALLOWED_MUTATIONS,
    PLUGIN_NOT_CONFIGURED,
    READ_COMMANDS,
    is_plugin_device_class,
)
from tests.remote_fakes import FakeApplication, FakePluginDevice, FakeSong


def _song_with_plugin(**kwargs: object) -> FakeSong:
    song = FakeSong()
    song.tracks[0].devices.append(FakePluginDevice(**kwargs))  # type: ignore[arg-type]
    return song


def _run(song: FakeSong, command: str, params: dict[str, object]) -> object:
    return execute_command(song, FakeApplication(), command, params)


# ---------------------------------------------------------------------------
# Configure-gate reporting
# ---------------------------------------------------------------------------


def test_get_device_list_flags_unconfigured_plugin() -> None:
    devices = _run(_song_with_plugin(), "get_device_list", {"track_index": 0})

    assert isinstance(devices, list)
    plugin = devices[1]
    assert plugin["class_name"] == "PluginDevice"
    assert plugin["plugin_state"]["status"] == "not_configured"
    assert plugin["plugin_state"]["configured_parameter_count"] == 0
    assert plugin["plugin_state"]["hint"] == PLUGIN_NOT_CONFIGURED
    assert "Configure" in plugin["plugin_state"]["message"]


def test_get_device_list_reports_configured_plugin_without_hint() -> None:
    devices = _run(_song_with_plugin(configured=True), "get_device_list", {"track_index": 0})

    assert isinstance(devices, list)
    state = devices[1]["plugin_state"]
    assert state["status"] == "configured"
    assert state["configured_parameter_count"] == 1
    assert "hint" not in state


def test_native_device_carries_no_plugin_state() -> None:
    devices = _run(FakeSong(), "get_device_list", {"track_index": 0})

    assert isinstance(devices, list)
    assert "plugin_state" not in devices[0]


def test_list_device_params_carries_plugin_state() -> None:
    entries = _run(_song_with_plugin(), "list_device_params", {"track_id": "track:0"})

    assert isinstance(entries, list)
    assert "plugin_state" not in entries[0]
    assert entries[1]["plugin_state"]["hint"] == PLUGIN_NOT_CONFIGURED


def test_set_parameter_value_on_unconfigured_plugin_explains_configure() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(),
            "set_parameter_value",
            {
                "track_index": 0,
                "device_index": 1,
                "parameter_name": "Master Volume",
                "value": 0.5,
            },
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "exposes no configured parameters" in str(error.value)
    assert error.value.details == {
        "hint_code": PLUGIN_NOT_CONFIGURED,
        "class_name": "PluginDevice",
    }


def test_get_parameter_value_on_configured_plugin_still_resolves() -> None:
    result = _run(
        _song_with_plugin(configured=True),
        "get_parameter_value",
        {"track_index": 0, "device_index": 1, "parameter_name": "Master Volume"},
    )

    assert isinstance(result, dict)
    assert result["name"] == "Master Volume"
    assert result["id"] == "track:0/device:1/param:1"


def test_native_device_missing_parameter_keeps_close_match_suggestion() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            FakeSong(),
            "get_parameter_value",
            {"track_index": 0, "device_index": 0, "parameter_name": "Filter Frek"},
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "Did you mean: Filter Freq?" in str(error.value)
    assert error.value.details is None


# ---------------------------------------------------------------------------
# get_plugin_presets
# ---------------------------------------------------------------------------


def test_get_plugin_presets_returns_names_and_selection() -> None:
    result = _run(
        _song_with_plugin(selected_preset_index=2),
        "get_plugin_presets",
        {"track_index": 0, "device_index": 1},
    )

    assert result == {
        "id": "track:0/device:1",
        "track_index": 0,
        "device_index": 1,
        "track_name": "Bass",
        "device_name": "Superior Drummer 3",
        "class_name": "PluginDevice",
        "presets": ["Default", "Rock Kit", "Jazz Kit"],
        "preset_count": 3,
        "selected_preset_index": 2,
        "plugin_state": {
            "configured_parameter_count": 0,
            "status": "not_configured",
            "hint": PLUGIN_NOT_CONFIGURED,
            "message": result["plugin_state"]["message"],  # type: ignore[index]
        },
    }


def test_get_plugin_presets_rejects_native_device() -> None:
    with pytest.raises(RemoteError) as error:
        _run(FakeSong(), "get_plugin_presets", {"track_index": 0, "device_index": 0})

    assert error.value.code == "WRONG_TYPE"
    assert "not a plugin" in str(error.value)


def test_get_plugin_presets_rejects_missing_device_index() -> None:
    with pytest.raises(RemoteError) as error:
        _run(_song_with_plugin(), "get_plugin_presets", {"track_index": 0, "device_index": 9})

    assert error.value.code == "INVALID_PARAMS"
    assert "Device index 9 does not exist." in str(error.value)


def test_get_plugin_presets_reports_empty_preset_list() -> None:
    result = _run(
        _song_with_plugin(presets=[]),
        "get_plugin_presets",
        {"track_index": 0, "device_index": 1},
    )

    assert isinstance(result, dict)
    assert result["presets"] == []
    assert result["preset_count"] == 0


# ---------------------------------------------------------------------------
# set_plugin_preset
# ---------------------------------------------------------------------------


def test_set_plugin_preset_by_index_writes_and_verifies() -> None:
    song = _song_with_plugin()
    result = _run(
        song, "set_plugin_preset", {"track_index": 0, "device_index": 1, "preset_index": 1}
    )

    assert result == {
        "id": "track:0/device:1",
        "selected_preset_index": 1,
        "preset_name": "Rock Kit",
        "previous_preset_index": 0,
        "preset_count": 3,
        "resolved": {
            "kind": "device",
            "track_index": 0,
            "device_index": 1,
            "track_name": "Bass",
            "device_name": "Superior Drummer 3",
        },
    }
    assert song.tracks[0].devices[1].selected_preset_index == 1


def test_set_plugin_preset_by_name_resolves_index() -> None:
    song = _song_with_plugin()
    result = _run(
        song,
        "set_plugin_preset",
        {"track_index": 0, "device_index": 1, "preset_name": "Jazz Kit"},
    )

    assert isinstance(result, dict)
    assert result["selected_preset_index"] == 2
    assert song.tracks[0].devices[1].selected_preset_index == 2


def test_set_plugin_preset_requires_exactly_one_selector() -> None:
    for params in (
        {"track_index": 0, "device_index": 1},
        {"track_index": 0, "device_index": 1, "preset_index": 1, "preset_name": "Rock Kit"},
    ):
        with pytest.raises(RemoteError) as error:
            _run(_song_with_plugin(), "set_plugin_preset", params)
        assert error.value.code == "INVALID_PARAMS"
        assert "exactly one of 'preset_index' or 'preset_name'" in str(error.value)


def test_set_plugin_preset_rejects_out_of_range_index() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 1, "preset_index": 7},
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "outside [0, 2]" in str(error.value)


def test_set_plugin_preset_suggests_close_preset_name() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 1, "preset_name": "Rock Kti"},
        )

    assert error.value.code == "INVALID_PARAMS"
    assert "Did you mean: Rock Kit?" in str(error.value)


def test_set_plugin_preset_refuses_ambiguous_name() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(presets=["Kit", "Kit"]),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 1, "preset_name": "Kit"},
        )

    assert error.value.code == "AMBIGUOUS_MATCH"
    assert "use 'preset_index'" in str(error.value)


def test_set_plugin_preset_refuses_plugin_without_presets() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(presets=[]),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 1, "preset_index": 0},
        )

    assert error.value.code == "CAPABILITY_UNAVAILABLE"
    assert "exposes no presets" in str(error.value)


def test_set_plugin_preset_retries_once_then_verifies() -> None:
    song = _song_with_plugin(stuck_writes=1)
    result = _run(
        song, "set_plugin_preset", {"track_index": 0, "device_index": 1, "preset_index": 1}
    )

    assert isinstance(result, dict)
    assert result["selected_preset_index"] == 1
    assert song.tracks[0].devices[1].write_attempts == 2


def test_set_plugin_preset_fails_when_host_never_lands_the_write() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            _song_with_plugin(stuck_writes=5),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 1, "preset_index": 1},
        )

    assert error.value.code == "VERIFICATION_FAILED"
    assert "requested 1" in str(error.value)


def test_set_plugin_preset_rejects_native_device() -> None:
    with pytest.raises(RemoteError) as error:
        _run(
            FakeSong(),
            "set_plugin_preset",
            {"track_index": 0, "device_index": 0, "preset_index": 0},
        )

    assert error.value.code == "WRONG_TYPE"


# ---------------------------------------------------------------------------
# Contracts, models and catalog wiring
# ---------------------------------------------------------------------------


def test_commands_are_routed_with_the_right_risk() -> None:
    assert "get_plugin_presets" in READ_COMMANDS
    assert "set_plugin_preset" in ALLOWED_MUTATIONS
    assert "get_plugin_presets" not in ALLOWED_MUTATIONS


def test_catalog_registers_both_tools() -> None:
    entries = {item.name: item for item in TOOL_CATALOG}
    assert entries["get_plugin_presets"].risk.value == "read"
    assert entries["set_plugin_preset"].risk.value == "reversible"
    assert entries["set_plugin_preset"].reversible is True


def test_is_plugin_device_class_covers_vst_and_audio_unit() -> None:
    assert is_plugin_device_class("PluginDevice")
    assert is_plugin_device_class("AuPluginDevice")
    assert not is_plugin_device_class("Operator")


def test_model_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError, match="exactly one of preset_index or preset_name"):
        models.SetPluginPresetRequest(track_index=0, device_index=1)
    with pytest.raises(ValueError, match="exactly one of preset_index or preset_name"):
        models.SetPluginPresetRequest(
            track_index=0, device_index=1, preset_index=0, preset_name="Rock Kit"
        )

    request = models.SetPluginPresetRequest(
        track_index=0, device_index=1, preset_name="  Rock Kit "
    )
    assert request.preset_name == "Rock Kit"


def test_model_rejects_blank_preset_name() -> None:
    with pytest.raises(ValueError):
        models.SetPluginPresetRequest(track_index=0, device_index=1, preset_name="   ")
