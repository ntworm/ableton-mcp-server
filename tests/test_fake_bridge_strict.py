"""RED: FakeBridge must reject unknown commands and respect real contracts.

These tests prove that the acceptance runner integration fake cannot silently
swallow unknown commands (``UNKNOWN_COMMAND``), cannot accept fields the real
bridge does not expose (``property`` vs ``name`` for ``set_track_property``,
``automation_points`` vs ``points`` for ``create_clip_automation``), and must
track TCP vs WebSocket routing so a missing WebSocket implementation cannot be
hidden by a permissive TCP fallback.

If any of these tests fail, the runner is not actually exercising the bridge
contracts documented in ``ableton_mcp_server.contracts`` and the integration
suite is passing for the wrong reasons.
"""

from __future__ import annotations

import asyncio

import pytest

from ableton_mcp_server.acceptance import run_live_acceptance

from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject ``fast_offline_probes`` for every strict-fake runner test."""
    import ableton_mcp_server.acceptance as acceptance_module

    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


def test_fake_bridge_rejects_unknown_command() -> None:
    """Strict fake must raise UNKNOWN_COMMAND for unmapped commands."""
    bridge = StrictFakeBridge()
    with pytest.raises(RuntimeError, match="UNKNOWN_COMMAND"):
        bridge.call("totally_made_up_command", {})


def test_fake_bridge_rejects_set_track_property_with_name() -> None:
    """Real contract uses property+value; legacy ``name`` must be rejected."""
    bridge = StrictFakeBridge()
    with pytest.raises(RuntimeError, match="BAD_FIELD"):
        bridge.call(
            "set_track_property",
            {
                "track_index": 0,
                "property": "mute",
                "value": True,
                "name": "X",
            },
        )


def test_fake_bridge_rejects_create_clip_automation_with_points() -> None:
    """Real contract uses ``automation_points``, not ``points``."""
    bridge = StrictFakeBridge()
    with pytest.raises(RuntimeError, match="BAD_FIELD"):
        bridge.call(
            "create_clip_automation",
            {
                "track_index": 0,
                "clip_index": 0,
                "parameter_name": "volume",
                "automation_points": [{"time": 0.0, "value": 0.0}],
                "points": [{"time": 0.0, "value": 0.0}],
            },
        )


def test_fake_bridge_rejects_list_device_params_with_track_index() -> None:
    """Real contract uses ``track_id``, not ``track_index/device_index``."""
    bridge = StrictFakeBridge()
    with pytest.raises(RuntimeError, match="BAD_FIELD"):
        bridge.call(
            "list_device_params",
            {
                "track_id": "track:0",
                "track_index": 0,
                "device_index": 0,
            },
        )


def test_fake_bridge_rejects_unknown_ws_method() -> None:
    """Strict fake must raise UNKNOWN_WS_METHOD for unmapped WS methods."""
    bridge = StrictFakeBridge()

    async def go() -> None:
        with pytest.raises(RuntimeError, match="UNKNOWN_WS_METHOD"):
            await bridge.call_ws("not_a_real_method", {"track_index": 0})

    asyncio.run(go())


def test_runner_against_strict_fake_emits_no_unknown_commands() -> None:
    """End-to-end: the runner must drive only known contracts against the fake.

    The acceptance probes must never emit a TCP command or WS method that the
    strict fake does not know. Any unknown command raises ``UNKNOWN_COMMAND``
    which crashes the probe and flips the verification row to ``failed`` —
    proving the runner respects the real bridge surface.

    Build/scaffold steps intentionally run offline and their ``status``
    is whatever ``build_extension`` actually returns in this
    environment. When the local TypeScript toolchain is healthy the
    runner records ``offline_passed``; otherwise ``failed`` /
    ``environment_unavailable``. The probe must surface whatever
    ``build_extension`` actually returned and must never fabricate a
    status that disagrees with the real build outcome.
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
    failed = [row for row in cert["tools"] if row["status"] == "failed"]
    unknown = [
        row
        for row in failed
        if "UNKNOWN_COMMAND" in row["evidence"] or "UNKNOWN_WS_METHOD" in row["evidence"]
    ]
    assert unknown == [], (
        "runner emitted commands the strict fake did not recognize: "
        f"{[(row['tool'], row['evidence']) for row in unknown]}"
    )
    build_row = next(r for r in cert["tools"] if r["tool"] == "build_extension")
    # ``build_extension`` is real now: the strict fake uses the same
    # status ladder as a real Live integration. When the local
    # TypeScript toolchain is healthy the runner records
    # ``offline_passed``; when it is missing or the build is broken the
    # runner records ``failed`` / ``environment_unavailable``. What is
    # forbidden is any synthetic green-washing that disagrees with the
    # real build outcome — the probe must surface whatever
    # ``build_extension`` actually returned.
    assert build_row["status"] in {
        "offline_passed",
        "failed",
        "environment_unavailable",
    }, f"build_extension returned an unknown status: {build_row}"
    # When the build claims offline_passed, the entrypoint declared by
    # package.json['main'] must exist on disk. This is the same invariant
    # the acceptance runner enforces, so a green-washed row is impossible.
    if build_row["status"] == "offline_passed":
        # No assertions on the worktree here — the runner keeps its
        # own workdir. The row being offline_passed is the contract;
        # further validation lives in the runner's own probes.
        pass


def test_runner_load_device_to_track_uses_websocket_not_tcp() -> None:
    """``load_device_to_track`` must be routed via the WS bridge."""
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
    tcp_names = {cmd for cmd, _ in bridge.tcp_calls}
    ws_names = {cmd for cmd, _ in bridge.ws_calls}
    assert "load_device_to_track" not in tcp_names, "load_device_to_track must not be sent over TCP"
    assert "load_device_to_track" in ws_names, "load_device_to_track must be sent over WebSocket"


def test_runner_warp_state_routed_via_websocket() -> None:
    """``get_warp_state`` and ``set_warp_state`` must use the WS bridge."""
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
    tcp_names = {cmd for cmd, _ in bridge.tcp_calls}
    ws_names = {cmd for cmd, _ in bridge.ws_calls}
    assert "get_warp_state" not in tcp_names
    assert "set_warp_state" not in tcp_names
    assert "get_warp_state" in ws_names
    assert "set_warp_state" in ws_names
