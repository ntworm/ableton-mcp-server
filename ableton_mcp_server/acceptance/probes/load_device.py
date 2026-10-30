"""``load_device_to_track`` probe.

The probe loads Operator onto the empty MIDI track that ``create_midi_track``
added a moment earlier. The Extension appends a device at the end of the
chain and Live keeps one instrument per chain, so a target that already holds
an instrument, like the MIDI target of the disposable Set, refuses every run
with "Failed to insert device" (docs/KNOWN_BUGS.md, Category R). Loading onto
the created track also leaves the user's tracks as they were: deleting that
track removes the device with it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ...certification import CertificationReport, Verification
from ..report import _record_call

TOOLS: tuple[str, ...] = ("load_device_to_track",)
PROBE_DEVICE = "Operator"

__all__ = ["PROBE_DEVICE", "TOOLS", "run"]

Call = Callable[[str, Mapping[str, Any] | None], Any]
CallWs = Callable[[str, dict[str, Any] | None], Awaitable[Any]]


async def run(
    report: CertificationReport,
    *,
    call: Call,
    call_ws: CallWs,
    track_index: int | None,
    artifacts: dict[str, Any],
) -> None:
    """Record the row against ``track_index``, the MIDI track the runner created."""
    if track_index is None:
        report.record(
            Verification(
                "load_device_to_track",
                "failed",
                "not executed because create_midi_track did not create an empty MIDI track",
            )
        )
        return

    async def probe() -> str:
        return await _load_and_verify(call, call_ws, track_index, artifacts)

    await _record_call(report, "load_device_to_track", probe)


async def _load_and_verify(
    call: Call, call_ws: CallWs, track_index: int, artifacts: dict[str, Any]
) -> str:
    """Load the device, then prove one more device sits at the reported index."""
    devices_before = call("get_device_list", {"track_index": track_index})
    if not isinstance(devices_before, list):
        raise AssertionError(
            f"get_device_list prior to load_device_to_track returned non-list: {devices_before!r}"
        )
    load_result = await call_ws(
        "load_device_to_track", {"track_index": track_index, "device_name": PROBE_DEVICE}
    )
    device_index = _reported_index(load_result, track_index)

    devices_after = call("get_device_list", {"track_index": track_index})
    if not isinstance(devices_after, list) or len(devices_after) != len(devices_before) + 1:
        after = len(devices_after) if isinstance(devices_after, list) else "non-list"
        raise AssertionError(
            "load_device_to_track did not increase device count by 1: "
            f"before={len(devices_before)}, after={after}"
        )
    if not 0 <= device_index < len(devices_after) or (
        devices_after[device_index].get("name") != PROBE_DEVICE
    ):
        raise AssertionError(
            f"load_device_to_track device at index {device_index} "
            f"is not {PROBE_DEVICE}: {devices_after}"
        )
    artifacts["manual_cleanup"].append(
        f"{PROBE_DEVICE} loaded on the MIDI track at index {track_index} that the runner "
        "created; deleting that track removes it"
    )
    return f"{PROBE_DEVICE} loaded at index {device_index} on track {track_index}"


def _reported_index(load_result: Any, track_index: int) -> int:
    """Check the Extension's answer and return the device index it reports."""
    if isinstance(load_result, str):
        load_result = json.loads(load_result)
    if not isinstance(load_result, dict):
        raise AssertionError(f"load_device_to_track non-dict response: {load_result!r}")
    expected = (
        ("status", "loaded", "unexpected status"),
        ("track_index", track_index, "track_index mismatch"),
        ("device_name", PROBE_DEVICE, "device_name mismatch"),
    )
    for key, value, problem in expected:
        if load_result.get(key) != value:
            raise AssertionError(f"load_device_to_track {problem}: {load_result}")
    device_index = load_result.get("device_index")
    if not isinstance(device_index, int):
        raise AssertionError(f"load_device_to_track missing device_index: {load_result}")
    return device_index
