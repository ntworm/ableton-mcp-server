"""``load_device_to_track`` acceptance probe against Live's device-chain rule.

Live refuses a second instrument in a chain with "Failed to insert device"
(docs/KNOWN_BUGS.md, Category R). The probe used to append Operator to the
MIDI target track, which in the disposable Set already holds one, so it
failed on every run. It now loads onto the empty MIDI track the runner
creates, and the strict fake refuses what Live refuses.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ableton_mcp_server.acceptance import run_live_acceptance
from ableton_mcp_server.errors import BridgeError

from ._fake_device_chain import append_device
from ._offline_probe_fixture import fast_offline_probes
from ._strict_fake import StrictFakeBridge
from .test_acceptance_audit_p0p1 import _RestoreOnlyDivergentBridge


@pytest.fixture(autouse=True)
def _inject_fast_offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    import ableton_mcp_server.acceptance as acceptance_module

    monkeypatch.setattr(acceptance_module, "run_offline_probes", fast_offline_probes)


def _run(bridge: StrictFakeBridge) -> dict[str, Any]:
    return asyncio.run(
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


def _row(result: dict[str, Any], tool: str) -> dict[str, Any]:
    return next(row for row in result["certification"]["tools"] if row["tool"] == tool)


def test_fake_refuses_a_second_instrument_like_live() -> None:
    tracks: list[dict[str, Any]] = [{"index": 0, "devices": [{"name": "Operator"}]}]

    with pytest.raises(BridgeError, match="Failed to insert device") as refused:
        append_device(tracks, 0, "Wavetable")

    assert refused.value.code == "EXTENSION_RPC_-32603"
    assert append_device(tracks, 0, "Reverb")["device_index"] == 1
    assert [device["name"] for device in tracks[0]["devices"]] == ["Operator", "Reverb"]


def test_probe_loads_onto_the_created_midi_track() -> None:
    bridge = StrictFakeBridge()
    target_devices = list(bridge.state["tracks"][0]["devices"])

    result = _run(bridge)

    assert _row(result, "load_device_to_track")["status"] == "live_passed"
    created = [entry for entry in result["artifacts"]["tracks_created"] if "midi:" in entry]
    loads = [params for method, params in bridge.ws_calls if method == "load_device_to_track"]
    assert loads == [{"track_index": int(created[0].split(":")[1]), "device_name": "Operator"}]
    assert bridge.state["tracks"][0]["devices"] == target_devices
    commands = [command for _route, command, _params in bridge.timeline_calls]
    assert commands.index("create_midi_track") < commands.index("load_device_to_track")


def test_probe_is_not_run_without_the_created_midi_track() -> None:
    bridge = StrictFakeBridge()
    bridge.fail_tool = "create_midi_track"

    result = _run(bridge)

    row = _row(result, "load_device_to_track")
    assert row["status"] == "failed"
    assert "not executed because create_midi_track" in row["evidence"]
    assert "load_device_to_track" not in [method for method, _params in bridge.ws_calls]


def test_probe_is_skipped_with_track_creation_after_a_failed_cleanup() -> None:
    result = _run(_RestoreOnlyDivergentBridge(allowed_writes=1))

    row = _row(result, "load_device_to_track")
    assert row["status"] == "failed"
    assert "reversible cleanup failed" in row["evidence"]
