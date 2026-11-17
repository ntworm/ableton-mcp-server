"""Runner-level integration tests (part two) moved from the original module."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    AcceptanceSafetyError,
    run_live_acceptance,
)

from . import test_acceptance_runner_integration as _shared
from ._strict_fake import StrictFakeBridge

_inject_fast_offline_probes = _shared._inject_fast_offline_probes


def test_acceptance_probes_isolation_from_clip_automation_failure() -> None:
    """FASE 2 Regression Guard.

    Prove that if `create_clip_automation` fails, it does not cascade/abort
    other independent probes. They should be attempted, and only tools dependent
    on create_clip should be skipped cleanly with a clear status/message.
    """
    bridge = StrictFakeBridge()
    # Inject failure ONLY for create_clip_automation
    bridge.fail_tool = "create_clip_automation"

    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is False

    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    # create_clip_automation failed
    assert statuses["create_clip_automation"] == "failed"
    # start_playback, stop_playback, rename_track, etc. succeeded!
    assert statuses["start_playback"] == "live_passed"
    assert statuses["stop_playback"] == "live_passed"
    assert statuses["rename_track"] == "live_passed"
    assert statuses["save_set"] == "live_passed"


def test_release_ready_policy_matrix() -> None:
    """FASE 4 Policy Matrix verification.

    Verify that:
    1. host_unavailable blocks release_ready.
    2. environment_unavailable blocks except build_extension.
    3. manual_required blocks except quit_ableton.
    """
    from ableton_mcp_server.certification import CertificationReport, Verification

    # 1. Standard report with only allowed exceptions: quit_ableton as manual_required
    # and build_extension as environment_unavailable (or offline_passed)
    report1 = CertificationReport(
        tool_names=("quit_ableton", "build_extension", "get_session_info")
    )
    report1.record(Verification("quit_ableton", "manual_required", "reason"))
    report1.record(Verification("build_extension", "environment_unavailable", "reason"))
    report1.record(Verification("get_session_info", "live_passed", "reason"))
    # finish should have release_ready = True
    assert report1.finish()["release_ready"] is True

    # 2. host_unavailable blocks
    report2 = CertificationReport(
        tool_names=("quit_ableton", "build_extension", "get_session_info")
    )
    report2.record(Verification("quit_ableton", "manual_required", "reason"))
    report2.record(Verification("build_extension", "environment_unavailable", "reason"))
    report2.record(Verification("get_session_info", "host_unavailable", "reason"))
    assert report2.finish()["release_ready"] is False

    # 3. environment_unavailable blocks for non-build_extension
    report3 = CertificationReport(
        tool_names=("quit_ableton", "build_extension", "get_session_info")
    )
    report3.record(Verification("quit_ableton", "manual_required", "reason"))
    report3.record(Verification("build_extension", "environment_unavailable", "reason"))
    report3.record(Verification("get_session_info", "environment_unavailable", "reason"))
    assert report3.finish()["release_ready"] is False

    # 4. manual_required blocks for non-quit_ableton
    report4 = CertificationReport(
        tool_names=("quit_ableton", "build_extension", "get_session_info")
    )
    report4.record(Verification("quit_ableton", "manual_required", "reason"))
    report4.record(Verification("build_extension", "environment_unavailable", "reason"))
    report4.record(Verification("get_session_info", "manual_required", "reason"))
    assert report4.finish()["release_ready"] is False


def test_save_set_order_and_fresh_set_checking() -> None:
    """Verify that save_set executes before other mutations.

    Also verify that preflight blocks a Set edited since it was opened.
    """
    bridge = StrictFakeBridge()
    # 1. Verify preflight safety check blocks when the undo history is not empty
    bridge.state["can_undo"] = True
    with pytest.raises(AcceptanceSafetyError, match=r"undo history \(can_undo=True\)"):
        asyncio.run(
            run_live_acceptance(
                bridge,
                confirm_project_name="TESTE_CODEX",
                track_index=0,
                clip_index=3,
                audio_track_index=2,
                audio_clip_index=0,
                fire_clip=True,
            )
        )


def test_preflight_undo_state_missing_or_ambiguous() -> None:
    """Verify that metadata missing can_undo or non-False value raises error."""

    class MissingUndoStateBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "get_project_metadata":
                return {"song_name": "TESTE_CODEX"}
            return super().call(command_type, params, timeout=timeout)

    bridge = MissingUndoStateBridge()
    with pytest.raises(AcceptanceSafetyError, match=r"undo history \(can_undo=None\)"):
        asyncio.run(
            run_live_acceptance(
                bridge,
                confirm_project_name="TESTE_CODEX",
                track_index=0,
                clip_index=3,
                audio_track_index=1,
                audio_clip_index=0,
            )
        )

    # 2. Reset and verify the order of calls
    bridge = StrictFakeBridge()
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            fire_clip=True,
        )
    )

    calls = [c[0] for c in bridge.tcp_calls]
    save_set_idx = calls.index("save_set")
    create_cue_idx = calls.index("create_cue_point")
    set_tempo_idx = calls.index("set_tempo")
    create_audio_idx = calls.index("create_audio_track")

    assert save_set_idx < create_cue_idx
    assert save_set_idx < set_tempo_idx
    assert save_set_idx < create_audio_idx


def test_parameter_discovery_case1_first_disabled_second_enabled() -> None:
    """Case 1: First parameter is disabled, second is enabled."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [
                    {
                        "name": "DisabledParam",
                        "value": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                        "is_enabled": False,
                        "is_quantized": False,
                    },
                    {
                        "name": "EnabledParam",
                        "value": 0.3,
                        "min": 0.0,
                        "max": 1.0,
                        "is_enabled": True,
                        "is_quantized": False,
                    },
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
    restored = bridge.state["device_parameters"]["track:0"][0]["parameters"][1]["value"]
    assert abs(restored - 0.3) < 0.01


def test_parameter_discovery_case2_already_at_max() -> None:
    """Case 2: First parameter is already at 1.0.

    Verification should choose a different target value.
    """
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [
                    {
                        "name": "MaxParam",
                        "value": 1.0,
                        "min": 0.0,
                        "max": 1.0,
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
    set_calls = [c for c in bridge.tcp_calls if c[0] == "set_parameter_value"]
    assert len(set_calls) >= 2
    assert abs(float(set_calls[0][1]["value"]) - 0.0) < 0.01


def test_parameter_discovery_case3_non_standard_range() -> None:
    """Case 3: Non-standard range (e.g. 100 to 20000)."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [
                    {
                        "name": "FreqParam",
                        "value": 1000.0,
                        "min": 100.0,
                        "max": 20000.0,
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
    set_calls = [c for c in bridge.tcp_calls if c[0] == "set_parameter_value"]
    target = float(set_calls[0][1]["value"])
    assert target in (100.0, 20000.0)


def test_parameter_discovery_case4_quantized() -> None:
    """Case 4: Quantized parameter."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [
                    {
                        "name": "QuantParam",
                        "value": 2.0,
                        "min": 0.0,
                        "max": 5.0,
                        "is_enabled": True,
                        "is_quantized": True,
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
    set_calls = [c for c in bridge.tcp_calls if c[0] == "set_parameter_value"]
    target = float(set_calls[0][1]["value"])
    assert target in (0.0, 5.0)


def test_parameter_discovery_case5_none_writable() -> None:
    """Case 5: Absence of writable parameters (should record environment_unavailable)."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [],
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
    assert row["status"] == "environment_unavailable"
    assert "no writable parameter found" in row["evidence"].lower()


def test_parameter_discovery_case6_proof_of_change() -> None:
    """Case 6: Verification that a real change occurred and was restored."""
    bridge = StrictFakeBridge()
    bridge.state["device_parameters"] = {
        "track:0": [
            {
                "device_name": "DeviceA",
                "parameters": [
                    {
                        "name": "MyParam",
                        "value": 0.4,
                        "min": 0.0,
                        "max": 1.0,
                        "is_enabled": True,
                        "is_quantized": False,
                    }
                ],
            }
        ]
    }
    asyncio.run(
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
    final_val = bridge.state["device_parameters"]["track:0"][0]["parameters"][0]["value"]
    assert abs(final_val - 0.4) < 0.01

    set_calls = [c for c in bridge.tcp_calls if c[0] == "set_parameter_value"]
    mutation_val = float(set_calls[0][1]["value"])
    assert abs(mutation_val - 0.4) > 0.1


def test_websocket_warp_failure_isolation() -> None:
    """Verify that a failure in get_warp_state (WebSocket down) only fails warp tools.

    It must not crash the TCP mutations run.
    """
    bridge = StrictFakeBridge()
    bridge.fail_tool = "get_warp_state"

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
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}

    assert statuses["get_warp_state"] in ("failed", "host_unavailable")
    assert statuses["set_warp_state"] == "failed"
    assert statuses["load_device_to_track"] == "live_passed"
    assert statuses["set_tempo"] == "live_passed"
    assert statuses["create_audio_track"] == "live_passed"
    assert statuses["create_midi_track"] == "live_passed"
    assert statuses["save_set"] == "live_passed"


def test_audio_decoupling_empty_or_non_audio_slot() -> None:
    """Verify that empty/non-audio slot fails warp without stopping TCP mutations."""
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=1,
            audio_clip_index=99,
            fire_clip=True,
        )
    )
    cert = result["certification"]
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    evidences = {row["tool"]: row["evidence"] for row in cert["tools"]}

    assert statuses["set_warp_state"] == "failed"
    assert "warp setup failed" in evidences["set_warp_state"]
    assert statuses["set_tempo"] == "live_passed"
    assert statuses["create_audio_track"] == "live_passed"
    assert statuses["create_midi_track"] == "live_passed"
    assert statuses["load_device_to_track"] == "live_passed"
    assert statuses["set_parameter_value"] == "live_passed"
    assert statuses["save_set"] == "live_passed"
