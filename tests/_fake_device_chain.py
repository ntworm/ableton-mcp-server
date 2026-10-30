"""Device-chain rules the strict fake shares with Live.

Live keeps a chain in the order MIDI effects, one instrument, audio effects,
and refuses any other insert, or a name that is not one of its built-in
devices, with the generic "Failed to insert device" (docs/KNOWN_BUGS.md,
Category R). Before the fake knew this, it accepted Operator on a track that
already held an Instrument Rack, and the acceptance tests passed while the
disposable Set failed every run. The fake Browser lists the same devices at
the first level of their category, as Live's Browser does.
"""

from __future__ import annotations

from typing import Any

from ableton_mcp_server.errors import BridgeError, InvalidParamsError

# Built-in devices the fake Browser lists, with their ``Device.type``.
_BROWSER_DEVICES = {
    "Operator": "instrument",
    "Wavetable": "instrument",
    "Instrument Rack": "instrument",
    "Arpeggiator": "midi_effect",
    "Reverb": "audio_effect",
    "Utility": "audio_effect",
}
_CATEGORIES = {"instrument": "instruments", "midi_effect": "midi_effects"}
_CHAIN_ORDER = {"midi_effect": 0, "instrument": 1, "audio_effect": 2}


def _device_type(device: dict[str, Any]) -> str:
    if device.get("class_name") == "InstrumentGroupDevice":
        return "instrument"
    return _BROWSER_DEVICES.get(str(device.get("name")), "undefined")


def typed_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a track's devices with ``type`` filled in, as ``get_device_list`` does."""
    return [{**device, "type": device.get("type", _device_type(device))} for device in devices]


def browser_search(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Answer ``search_browser``: the runner's ``"o"`` probe and first-level lookups."""
    if params.get("query") == "o":
        return [{"name": "Operator", "uri": "query:Operator#0"}]
    if params.get("max_depth") != 1:
        return []
    wanted = str(params["query"]).casefold()
    return [
        {"name": name, "category": params.get("category_type"), "is_loadable": True}
        for name, kind in _BROWSER_DEVICES.items()
        if _CATEGORIES.get(kind, "audio_effects") == params.get("category_type")
        and wanted in name.casefold()
    ]


def _chain_accepts(types: list[str]) -> bool:
    ordered = [_CHAIN_ORDER[kind] for kind in types if kind in _CHAIN_ORDER]
    return "unknown" not in types and ordered == sorted(ordered) and types.count("instrument") < 2


def append_device(
    tracks: list[dict[str, Any]],
    track_index: int,
    device_name: str,
    device_index: int | None = None,
) -> dict[str, Any]:
    """Insert ``device_name`` at ``device_index`` (default: the end), refusing what Live refuses."""
    for track in tracks:
        if track["index"] != track_index:
            continue
        devices = track.setdefault("devices", [])
        index = len(devices) if device_index is None else device_index
        if not 0 <= index <= len(devices):
            raise InvalidParamsError(f"device_index must be an integer from 0 to {len(devices)}")
        types = [_device_type(device) for device in devices]
        types.insert(index, _BROWSER_DEVICES.get(device_name, "unknown"))
        if not _chain_accepts(types):
            raise BridgeError("Failed to insert device", code="EXTENSION_RPC_-32603")
        devices.insert(index, {"name": device_name, "type": types[index]})
        return {
            "status": "loaded",
            "track_index": track_index,
            "device_name": device_name,
            "device_index": index,
        }
    return {
        "status": "loaded",
        "track_index": track_index,
        "device_name": device_name,
        "device_index": None,
    }
