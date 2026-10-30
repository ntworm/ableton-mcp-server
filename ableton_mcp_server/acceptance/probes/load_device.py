"""``load_device_to_track`` probe.

The probe loads Operator onto the empty MIDI track that ``create_midi_track``
added a moment earlier, then Arpeggiator, which Live accepts only before the
instrument. Live keeps a chain in the order MIDI effects, one instrument,
audio effects, and refuses any other insert with "Failed to insert device"
(docs/KNOWN_BUGS.md, Category R); the server picks the position from that
order, and the probe goes through the same planning. Loading onto the created
track also leaves the user's tracks as they were: deleting that track removes
the devices with it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ...certification import CertificationReport, Verification
from ...device_insert import insert_params
from ..report import _record_call

TOOLS: tuple[str, ...] = ("load_device_to_track",)
# Loaded in this order onto an empty track; Live accepts the MIDI effect only
# before the instrument, so the chain has to end up as ``EXPECTED_CHAIN``.
PROBE_DEVICES = ("Operator", "Arpeggiator")
EXPECTED_CHAIN = ["Arpeggiator", "Operator"]

__all__ = ["EXPECTED_CHAIN", "PROBE_DEVICES", "TOOLS", "run"]

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
        for device_name in PROBE_DEVICES:
            await _load_and_verify(call, call_ws, track_index, device_name)
        artifacts["manual_cleanup"].append(
            f"{' and '.join(PROBE_DEVICES)} loaded on the MIDI track at index {track_index} "
            "that the runner created; deleting that track removes them"
        )
        return _chain_order(call, track_index)

    await _record_call(report, "load_device_to_track", probe)


async def _load_and_verify(call: Call, call_ws: CallWs, track_index: int, device_name: str) -> None:
    """Load one device where the server plans it, then prove it sits there."""
    devices_before = call("get_device_list", {"track_index": track_index})
    if not isinstance(devices_before, list):
        raise AssertionError(
            f"get_device_list prior to load_device_to_track returned non-list: {devices_before!r}"
        )
    params = insert_params(call, track_index, device_name)
    load_result = await call_ws("load_device_to_track", params)
    device_index = _reported_index(load_result, track_index, device_name)

    devices_after = call("get_device_list", {"track_index": track_index})
    if not isinstance(devices_after, list) or len(devices_after) != len(devices_before) + 1:
        after = len(devices_after) if isinstance(devices_after, list) else "non-list"
        raise AssertionError(
            "load_device_to_track did not increase device count by 1: "
            f"before={len(devices_before)}, after={after}"
        )
    if not 0 <= device_index < len(devices_after) or (
        devices_after[device_index].get("name") != device_name
    ):
        raise AssertionError(
            f"load_device_to_track device at index {device_index} "
            f"is not {device_name}: {devices_after}"
        )
    if device_index != params.get("device_index", device_index):
        raise AssertionError(
            f"load_device_to_track put {device_name} at index {device_index}, "
            f"not at the planned index {params['device_index']}"
        )


def _chain_order(call: Call, track_index: int) -> str:
    """Check the final chain and describe it."""
    names = [device.get("name") for device in call("get_device_list", {"track_index": track_index})]
    if names != EXPECTED_CHAIN:
        raise AssertionError(
            f"load_device_to_track left the chain {names}, expected {EXPECTED_CHAIN}"
        )
    return f"{' then '.join(names)} on track {track_index}"


def _reported_index(load_result: Any, track_index: int, device_name: str) -> int:
    """Check the Extension's answer and return the device index it reports."""
    if isinstance(load_result, str):
        load_result = json.loads(load_result)
    if not isinstance(load_result, dict):
        raise AssertionError(f"load_device_to_track non-dict response: {load_result!r}")
    expected = (
        ("status", "loaded", "unexpected status"),
        ("track_index", track_index, "track_index mismatch"),
        ("device_name", device_name, "device_name mismatch"),
    )
    for key, value, problem in expected:
        if load_result.get(key) != value:
            raise AssertionError(f"load_device_to_track {problem}: {load_result}")
    device_index = load_result.get("device_index")
    if not isinstance(device_index, int):
        raise AssertionError(f"load_device_to_track missing device_index: {load_result}")
    return device_index
