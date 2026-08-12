"""Integration test for ``run_live_acceptance`` against the strict fake.

These tests prove that the runner produces exactly the catalogued number
of certification rows, that no row is fabricated as
``environment_unavailable`` to make the report green, that mutations are
followed by readback before they are recorded as ``live_passed``, and
that ``release_ready`` flips to ``False`` the moment any tool fails or
the baseline profile is not fully exercised.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import (
    BASELINE_PROBE_GROUPS,
    AcceptanceSafetyError,
    run_live_acceptance,
)
from ableton_mcp_server.catalog import TOOL_CATALOG
from contracts import UNSUPPORTED_CAPABILITIES

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import _READ_ONLY_TCP_COMMANDS, StrictFakeBridge


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject ``fast_offline_probes`` for every runner-level integration test.

    The canonical environmental test for the offline pipeline lives in
    ``tests/test_acceptance_audit_p0p1.py`` and exercises the real
    ``real_run_offline_probes``. Every other runner-level test passes the

    deterministic injection via this fixture so the suite does not run
    ``npm install`` + ``tsc`` on every call. Production CLI callers
    (``ableton-mcp acceptance ...``) keep the real implementation
    because they do not pass ``offline_probes``.
    """
    import ableton_mcp_server.acceptance as acceptance_module

    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


def test_fake_runner_returns_77_certification_rows() -> None:
    """Every catalogued tool must produce exactly one verification row."""
    expected = len(TOOL_CATALOG)
    assert expected == 77

    bridge = StrictFakeBridge()
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
    assert cert["tool_count"] == 77
    assert len(cert["tools"]) == 77
    catalog_names = {item.name for item in TOOL_CATALOG}
    assert {row["tool"] for row in cert["tools"]} == catalog_names
    # ``quit_ableton`` is explicitly ``manual_required`` in baseline.
    # The runner never auto-closes the host, and the row only flips to
    # ``manual_passed`` after an out-of-band owner confirmation.
    assert any(
        row["tool"] == "quit_ableton" and row["status"] == "manual_required"
        for row in cert["tools"]
    )
    # No tool is silently dropped from the report.
    reported = {row["tool"] for row in cert["tools"]}
    assert reported == catalog_names


def test_fake_runner_release_ready_true_when_baseline_complete() -> None:
    """Full baseline + fire_clip → release_ready.

    The baseline must finish with ``status == "built"`` for
    ``build_extension`` and zero failed rows. If the local build
    environment is missing the TypeScript toolchain the runner reports
    ``build_extension`` as ``failed`` and ``release_ready`` flips to
    ``False`` — the runner never green-washes a broken build.
    """
    bridge = StrictFakeBridge()
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
    build_row = next(r for r in cert["tools"] if r["tool"] == "build_extension")
    # ``build_extension`` is the gate: if the local TypeScript toolchain
    # is broken we never claim release_ready, even when every other
    # probe passed.
    if build_row["status"] != "offline_passed":
        assert cert["release_ready"] is False, (
            f"release_ready must be False when build_extension did not pass: {build_row}"
        )
        return
    assert cert["release_ready"] is True
    assert all(row["status"] != "failed" for row in cert["tools"])


def test_fake_runner_release_ready_false_without_fire_clip() -> None:
    """Baseline without ``--fire-clip`` is never release-ready.

    P1#9: ``fire_clip`` is a required exercise in the baseline; running
    without it leaves the runner with a documented gap.
    """
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is False, "baseline without --fire-clip must not be release-ready"
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    assert statuses["fire_clip"] == "environment_unavailable"


def test_fake_runner_partial_profile_is_not_release_ready() -> None:
    """Partial profiles (``tcp_reads``) must never claim release_ready.

    P1#9: a partial profile can finish green even when the mutation
    surface was never exercised. The release policy blocks promotion
    unless every baseline group ran.
    """
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            profiles=("tcp_reads",),
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is False
    # Mutations were not exercised; tools outside ``tcp_reads`` must
    # have a recorded status (failed or environment_unavailable), never
    # silently missing.
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    for tool in BASELINE_PROBE_GROUPS["mutations"]:
        assert tool in statuses
    # The runner must NOT have skipped the missing tools entirely.
    assert len(statuses) == 77


def test_fake_runner_release_ready_false_when_one_tool_fails() -> None:
    bridge = StrictFakeBridge()
    bridge.fail_tool = "set_tempo"
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    assert cert["release_ready"] is False
    failed_names = [row["tool"] for row in cert["tools"] if row["status"] == "failed"]
    assert "set_tempo" in failed_names


def test_fake_runner_baseline_records_only_known_unavailable() -> None:
    """Baseline profile must record every selected tool with real evidence.

    The only legitimate ``environment_unavailable`` rows in the baseline
    profile are ``build_extension`` when Node is absent, and ``fire_clip``
    when the flag is missing. ``quit_ableton`` is now
    ``manual_required`` (out-of-band owner confirmation) — never
    green-washed as ``environment_unavailable``.
    """
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    cert = result["certification"]
    statuses = {row["tool"]: row["status"] for row in cert["tools"]}
    unavailable = sorted(
        tool for tool, status in statuses.items() if status == "environment_unavailable"
    )
    # Without ``--fire-clip``, fire_clip is also unavailable. The plugin rows
    # need a third-party VST/VST3/AU that the fake Set does not carry.
    allowed = {"fire_clip", "build_extension", "get_plugin_presets", "set_plugin_preset"}
    assert set(unavailable) <= allowed, f"unexpected unavailable tools: {unavailable}"
    for tool, status in statuses.items():
        if tool in allowed:
            continue
        if status == "manual_required":
            # ``quit_ableton`` is the only tool currently classified as
            # ``manual_required``; other rows must not be silently
            # downgraded without an out-of-band signal.
            assert tool == "quit_ableton", f"unexpected manual_required row: {tool}"
            continue
        if status == "capability_unavailable":
            # Only the hierarchy tools may carry this status, and membership
            # comes from contracts — a probe cannot elect itself into it.
            assert tool in UNSUPPORTED_CAPABILITIES, (
                f"{tool} is not a documented capability gap but claimed one"
            )
            continue
        assert status in {"live_passed", "offline_passed"}, f"{tool} unexpectedly {status!r}"


def test_fake_runner_readback_failure_flips_tool_to_failed() -> None:
    """Inject a readback mismatch and prove the tool becomes ``failed``."""
    bridge = StrictFakeBridge()
    bridge.fail_tool = "set_tempo"
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
    assert cert["release_ready"] is False
    assert statuses["set_tempo"] == "failed"


@pytest.mark.parametrize(
    "response",
    [
        {"saved": True, "api_available": False, "song_save_available": True},
        {"saved": False, "api_available": False, "gui_workflow": {}},
        {"saved": False, "api_available": False, "gui_workflow": {"save": []}},
        {
            "saved": False,
            "api_available": False,
            "gui_workflow": {"save": ["File -> Save", ""]},
        },
        {"saved": False, "song_save_available": False},
    ],
)
def test_fake_runner_save_set_rejects_non_contract_responses(
    response: dict[str, Any],
) -> None:
    """Contradictory, legacy, or malformed save responses must fail closed."""
    bridge = StrictFakeBridge()
    bridge.save_set_response = response
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
    save_row = next(r for r in cert["tools"] if r["tool"] == "save_set")
    assert save_row["status"] == "failed", save_row
    assert cert["release_ready"] is False


def test_fake_runner_reports_reserved_artifacts() -> None:
    """The runner must surface a list of artifacts reserved for cleanup."""
    bridge = StrictFakeBridge()
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
    artifacts = result["artifacts"]
    assert isinstance(artifacts, dict)
    assert "tags" in artifacts
    assert "files" in artifacts
    assert "tracks_created" in artifacts
    assert "manual_cleanup" in artifacts
    # The runner tagged at least one cue point.
    assert any("ABLETON_MCP_ACCEPTANCE" in tag for tag in artifacts["tags"])
    # The runner created the audio + midi tracks.
    assert any("audio:" in t for t in artifacts["tracks_created"])
    assert any("midi:" in t for t in artifacts["tracks_created"])


def test_fake_runner_quit_profile_marks_quit_ableton_manual_required() -> None:
    """``quit_ableton`` runs only under the ``quit`` profile, and only
    as ``manual_required`` — never as ``live_passed`` without an
    out-of-band owner confirmation that the host was actually closed.
    """
    bridge = StrictFakeBridge()
    result = asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
            profiles=("quit",),
        )
    )
    cert = result["certification"]
    quit_row = next(r for r in cert["tools"] if r["tool"] == "quit_ableton")
    # The runner does not have a real quit path. Certifying
    # ``manual_required`` keeps release_ready=False until the owner
    # confirms a real shutdown.
    assert quit_row["status"] == "manual_required"
    assert cert["release_ready"] is False


def test_baseline_probe_coverage_matches_catalog() -> None:
    """Defensive guard: the probe map must cover every catalogued tool."""
    flat = {name for group in BASELINE_PROBE_GROUPS.values() for name in group}
    catalog_names = {item.name for item in TOOL_CATALOG}
    assert flat == catalog_names
    assert len(flat) == 77


def test_spy_proves_fast_offline_probes_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that runner execution actually invokes fast_offline_probes."""
    import ableton_mcp_server.acceptance as acceptance_module

    spy_called = False

    async def spy_offline_probes(*args: Any, **kwargs: Any) -> None:
        nonlocal spy_called
        spy_called = True
        await fast_offline_probes(*args, **kwargs)

    monkeypatch.setattr(acceptance_module, "run_offline_probes", spy_offline_probes)

    bridge = StrictFakeBridge()
    asyncio.run(
        run_live_acceptance(
            bridge,
            confirm_project_name="TESTE_CODEX",
            track_index=0,
            clip_index=3,
            audio_track_index=2,
            audio_clip_index=0,
        )
    )
    assert spy_called, "fast_offline_probes spy was not invoked during run_live_acceptance"


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


def test_save_set_order_and_is_dirty_checking() -> None:
    """Verify that save_set executes before other mutations.

    Also verify that preflight blocks if project is dirty.
    """
    bridge = StrictFakeBridge()
    # 1. Verify preflight safety check blocks when is_dirty is True
    bridge.state["is_dirty"] = True
    with pytest.raises(AcceptanceSafetyError, match="Loaded project dirty state is non-clean"):
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


def test_preflight_is_dirty_missing_or_ambiguous() -> None:
    """Verify that metadata missing is_dirty or non-False value raises error."""

    class MissingDirtyBridge(StrictFakeBridge):
        def call(self, command_type: str, params: Any = None, *, timeout: Any = None) -> Any:
            if command_type == "get_project_metadata":
                return {"song_name": "TESTE_CODEX"}
            return super().call(command_type, params, timeout=timeout)

    bridge = MissingDirtyBridge()
    with pytest.raises(AcceptanceSafetyError, match="non-clean"):
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
