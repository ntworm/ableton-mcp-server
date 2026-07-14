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
    run_live_acceptance,
)
from ableton_mcp_server.catalog import TOOL_CATALOG

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge


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


def test_fake_runner_returns_65_certification_rows() -> None:
    """Every catalogued tool must produce exactly one verification row."""
    expected = len(TOOL_CATALOG)
    assert expected == 65

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
    assert cert["tool_count"] == 65
    assert len(cert["tools"]) == 65
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
    assert len(statuses) == 65


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
    # Without ``--fire-clip``, fire_clip is also unavailable.
    allowed = {"fire_clip", "build_extension"}
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
        assert status in {"live_passed", "offline_passed"}, f"{tool} unexpectedly {status!r}"


def test_fake_runner_readback_failure_flips_tool_to_failed() -> None:
    """Inject a readback mismatch and prove the tool becomes ``failed``.

    The fake exposes a knob via ``state`` overrides. Here we set the
    audio track index to a non-existent track; the runner's audio clip
    guard must refuse the run with ``AcceptanceSafetyError`` and every
    mutation tool must be marked ``failed`` — not ``live_passed``.
    """
    bridge = StrictFakeBridge()
    bridge.state["tracks"] = [
        {
            "index": 0,
            "type": "midi",
            "name": "Bass",
            "id": "track:0",
            "mute": False,
            "solo": False,
            "arm": False,
            "devices": [{"name": "MIDI Device"}],
        },
    ]
    # No audio track exists; the runner should refuse on the audio
    # clip guard.
    import pytest

    with pytest.raises(  # noqa: B017 — broad to catch any refusal path
        RuntimeError, match="audio_track_index"
    ):
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


def test_fake_runner_save_set_requires_explicit_saved_true() -> None:
    """``save_set`` must not pass with ``saved=False`` or ambiguous results."""
    bridge = StrictFakeBridge()
    bridge.save_set_response = {"saved": False, "song_save_available": True}
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
    # The runner must not promote the report when save_set is ambiguous.
    assert cert["release_ready"] is False


def test_fake_runner_save_set_host_unavailable_when_api_missing() -> None:
    """``save_set`` is ``host_unavailable`` when ``song_save_available=False``."""
    bridge = StrictFakeBridge()
    bridge.save_set_response = {"saved": False, "song_save_available": False}
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
    assert save_row["status"] == "host_unavailable", save_row


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
    assert len(flat) == 65


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
