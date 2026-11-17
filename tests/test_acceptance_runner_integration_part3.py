"""Runner-level integration tests (part three) moved from the original module."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    run_live_acceptance,
)

from . import test_acceptance_runner_integration as _shared
from ._strict_fake import _READ_ONLY_TCP_COMMANDS, StrictFakeBridge

_inject_fast_offline_probes = _shared._inject_fast_offline_probes


def test_parameter_discovery_stale_list_device_params_and_small_range() -> None:
    """Verify micro range (0.0-0.001) and live readback computation."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "MicroDevice",
                "parameters": [
                    {
                        "name": "MicroParam",
                        "value": 0.001,
                        "min": 0.0,
                        "max": 0.001,
                        "is_enabled": True,
                        "is_quantized": False,
                    }
                ],
            }
        ]
    }
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "set_parameter_value")
    assert row["status"] == "live_passed"


def test_parameter_write_ignored_by_fake_causes_probe_failure() -> None:
    """Verify that if set_parameter_value fails to apply on host, the probe records failed."""

    class RefusingParamBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "set_parameter_value":
                return {"value": 0.0}
            return super().call(command_type, params, timeout=timeout)

    bridge = RefusingParamBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "set_parameter_value")
    assert row["status"] == "failed"


def test_load_device_to_track_preexisting_operator_causes_failure() -> None:
    """Verify that returning success without increasing device count fails load_device_to_track."""

    class NoOpLoadBridge(StrictFakeBridge):
        async def call_ws(self, method: str, params: Any = None, *, timeout: float = 2.0) -> Any:
            if method == "load_device_to_track":
                return {
                    "status": "loaded",
                    "track_index": params["track_index"],
                    "device_name": params["device_name"],
                    "device_index": 0,
                }
            return await super().call_ws(method, params, timeout=timeout)

    bridge = NoOpLoadBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "load_device_to_track")
    assert row["status"] == "failed"
    assert "did not increase device count by 1" in row["evidence"]


def test_create_track_existing_index_or_inconsistent_type_causes_failure() -> None:
    """Verify that returning existing track index for create_audio_track fails the probe."""

    class ExistingIndexTrackBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "create_audio_track":
                return {"track_index": 0}
            return super().call(command_type, params, timeout=timeout)

    bridge = ExistingIndexTrackBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "create_audio_track")
    assert row["status"] == "failed"
    assert "returned track_index 0, expected" in row["evidence"]


def test_live_fade_restore_uses_fallback_track_index() -> None:
    """Verify that when audio_track_index is invalid, live_fade uses fallback track for restore."""
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=99,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    assert statuses["live_fade"] == "live_passed"
    assert statuses["set_warp_state"] == "failed"


def test_small_parameter_range_write_failure() -> None:
    """Verify write failure on micro range (0.0 to 0.000001) is detected."""

    class RefusingMicroBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "set_parameter_value":
                return {"value": 0.0}
            return super().call(command_type, params, timeout=timeout)

    bridge = RefusingMicroBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "MicroDev",
                "parameters": [
                    {
                        "name": "MicroParam",
                        "value": 0.0,
                        "min": 0.0,
                        "max": 0.000001,
                        "is_enabled": True,
                        "is_quantized": False,
                    }
                ],
            }
        ]
    }
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "set_parameter_value")
    assert row["status"] == "failed"


@pytest.mark.parametrize(
    ("t_case", "expected_err"),
    [
        ("non_list_devs", "returned non-list"),
        ("negative_index", "is not Operator"),
    ],
)
def test_load_device_to_track_contract_robustness(t_case: str, expected_err: str) -> None:
    """Verify load_device_to_track fails when pre-query is non-list or index is negative."""

    class RobustnessBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "get_device_list" and t_case == "non_list_devs":
                return {"error": "invalid_track"}
            return super().call(command_type, params, timeout=timeout)

        async def call_ws(self, method: str, params: Any = None, *, timeout: float = 2.0) -> Any:
            if method == "load_device_to_track" and t_case == "negative_index":
                target = params["track_index"]
                for t in self.state["tracks"]:
                    if t["index"] == target:
                        t.setdefault("devices", []).append({"name": "Operator"})
                        break
                return {
                    "status": "loaded",
                    "track_index": target,
                    "device_name": params["device_name"],
                    "device_index": -1,
                }
            return await super().call_ws(method, params, timeout=timeout)

    bridge = RobustnessBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == "load_device_to_track")
    assert row["status"] == "failed"
    assert expected_err in row["evidence"]


def test_save_set_precedes_all_mutations_global_timeline() -> None:
    """Verify save_set appears in global timeline before first mutation."""
    bridge = StrictFakeBridge()
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    mutations = [
        t
        for t in bridge.timeline_calls
        if t[1] not in _READ_ONLY_TCP_COMMANDS and t[1] != "get_warp_state"
    ]
    assert mutations[0][1] == "save_set"

    save_idx = next(i for i, c in enumerate(bridge.timeline_calls) if c[1] == "save_set")
    warp_idx = next(i for i, c in enumerate(bridge.timeline_calls) if c[1] == "set_warp_state")
    load_idx = next(
        i for i, c in enumerate(bridge.timeline_calls) if c[1] == "load_device_to_track"
    )
    assert save_idx < warp_idx
    assert save_idx < load_idx


@pytest.mark.parametrize(
    ("tool_name", "subclass_behavior"),
    [
        ("create_audio_track", "existing_index"),
        ("create_audio_track", "wrong_type"),
        ("create_audio_track", "no_count_increase"),
        ("create_midi_track", "existing_index"),
        ("create_midi_track", "wrong_type"),
        ("create_midi_track", "no_count_increase"),
    ],
)
def test_track_creation_negative_matrix(tool_name: str, subclass_behavior: str) -> None:
    """Verify track creation negative cases result in probe failure."""

    class TrackCreationBadBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == tool_name:
                if subclass_behavior == "existing_index":
                    return {"track_index": 0}
                if subclass_behavior == "no_count_increase":
                    return {"track_index": 99}
                if subclass_behavior == "wrong_type":
                    opp_type = "midi" if tool_name == "create_audio_track" else "audio"
                    self.state["tracks"].append(
                        {
                            "index": 99,
                            "type": opp_type,
                            "name": "WrongTypeTrack",
                            "id": "track:99",
                            "devices": [],
                        }
                    )
                    return {"track_index": 99}
            if command_type == "get_track_list" and subclass_behavior == "no_count_increase":
                return [
                    {k: t[k] for k in ("id", "index", "name", "type") if k in t}
                    for t in self.state["tracks"]
                ]
            return super().call(command_type, params, timeout=timeout)

    bridge = TrackCreationBadBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            profiles=("mutations",),
        )
    )
    cert = result["certification"]
    row = next(r for r in cert["tools"] if r["tool"] == tool_name)
    assert row["status"] == "failed"


def test_save_set_api_unavailable_recorded_as_manual_required_and_release_ready() -> None:
    """Verify save_set api_available=false is manual_required and permits release_ready."""

    class ApiUnavailSaveBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "save_set":
                return {
                    "saved": False,
                    "api_available": False,
                    "gui_workflow": {"save": ["File -> Save"]},
                }
            return super().call(command_type, params, timeout=timeout)

    bridge = ApiUnavailSaveBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    save_row = next(r for r in cert["tools"] if r["tool"] == "save_set")
    assert save_row["status"] == "manual_required"
    assert "Host does not expose Song.save API" in save_row["evidence"]
    assert cert["release_ready"] is True


def test_track_creation_insertion_with_return_and_master_tracks() -> None:
    """Verify track creation inserts regular tracks at pre_regular_count and shifts returns."""
    bridge = StrictFakeBridge()
    bridge.state["tracks"].extend(
        [
            {"index": 3, "type": "return", "name": "A-Reverb", "id": "track:3", "devices": []},
            {"index": 4, "type": "return", "name": "B-Delay", "id": "track:4", "devices": []},
            {"index": 5, "type": "master", "name": "Main", "id": "track:5", "devices": []},
        ]
    )
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    audio_row = next(r for r in cert["tools"] if r["tool"] == "create_audio_track")
    midi_row = next(r for r in cert["tools"] if r["tool"] == "create_midi_track")
    assert audio_row["status"] == "live_passed"
    assert midi_row["status"] == "live_passed"
    assert cert["release_ready"] is True


def test_duplicate_track_names_do_not_redirect_cleanup() -> None:
    """Cleanup must preserve original objects even when Live track names collide."""
    bridge = StrictFakeBridge()
    regular = bridge.state["tracks"][0]
    regular.update({"name": "DUPLICATE", "mute": False, "solo": True, "arm": False})
    return_track = {
        "index": 3,
        "type": "return",
        "name": "DUPLICATE",
        "id": "track:3",
        "mute": True,
        "solo": False,
        "arm": True,
        "devices": [],
    }
    bridge.state["tracks"].extend(
        [
            return_track,
            {
                "index": 4,
                "type": "master",
                "name": "Main",
                "id": "track:4",
                "mute": False,
                "solo": False,
                "arm": False,
                "devices": [],
            },
        ]
    )
    expected_regular = {key: regular[key] for key in ("mute", "solo", "arm")}
    expected_return = {key: return_track[key] for key in ("mute", "solo", "arm")}

    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            fire_clip=True,
        )
    )

    assert {key: regular[key] for key in expected_regular} == expected_regular
    assert {key: return_track[key] for key in expected_return} == expected_return
    assert result["certification"]["release_ready"] is True


def test_structural_track_creation_runs_after_cleanup_mutations() -> None:
    """No reversible cleanup write may run after the first new track is inserted."""
    bridge = StrictFakeBridge()
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=0,
            fire_clip=True,
        )
    )

    commands = [command for _route, command, _params in bridge.timeline_calls]
    first_create = commands.index("create_audio_track")
    reversible_writes = {
        "stop_playback",
        "set_loop",
        "set_loop_start",
        "set_loop_length",
        "set_tempo",
        "set_current_song_time",
        "delete_cue_point",
        "set_track_property",
        "live_fade",
        "set_parameter_value",
        "set_warp_state",
    }
    writes_after_creation = [
        command for command in commands[first_create + 1 :] if command in reversible_writes
    ]
    assert writes_after_creation == []
