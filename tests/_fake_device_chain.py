"""Device-chain rule the strict fake shares with Live.

The Extension's ``load_device_to_track`` appends a device at the end of the
chain, and Live keeps one instrument per chain, so it refuses a second one
with the generic "Failed to insert device" (docs/KNOWN_BUGS.md, Category R).
Before the fake knew this, it accepted Operator on a track that already held
an Instrument Rack, and the acceptance tests passed while the disposable Set
failed every run.
"""

from __future__ import annotations

from typing import Any

from ableton_mcp_server.errors import BridgeError

# Instruments the fake Sets use, by device name or Live class name.
_INSTRUMENTS = frozenset({"Operator", "Wavetable", "Instrument Rack", "InstrumentGroupDevice"})


def _is_instrument(device: dict[str, Any]) -> bool:
    return device.get("name") in _INSTRUMENTS or device.get("class_name") in _INSTRUMENTS


def append_device(
    tracks: list[dict[str, Any]], track_index: int, device_name: str
) -> dict[str, Any]:
    """Append ``device_name`` to the chain of ``track_index``, refusing what Live refuses."""
    device_index = None
    for track in tracks:
        if track["index"] != track_index:
            continue
        devices = track.setdefault("devices", [])
        if device_name in _INSTRUMENTS and any(_is_instrument(d) for d in devices):
            raise BridgeError("Failed to insert device", code="EXTENSION_RPC_-32603")
        device_index = len(devices)
        devices.append({"name": device_name})
        break
    return {
        "status": "loaded",
        "track_index": track_index,
        "device_name": device_name,
        "device_index": device_index,
    }
