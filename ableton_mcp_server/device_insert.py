"""Where ``load_device_to_track`` puts a device in a track's chain.

Live keeps a device chain in the order MIDI effects, one instrument, audio
effects, and refuses any other insert with one generic "Failed to insert
device" (docs/KNOWN_BUGS.md, Category R). The Extension SDK inserts at an index
but cannot tell what a device is, so the server asks the Remote Script: the
first level of Live's browser gives the role of the new device, and
``Device.type`` gives the role of every device the track already holds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .errors import BadInputError

Call = Callable[[str, Mapping[str, Any] | None], Any]

# Browser categories whose first level lists Live's built-in devices.
_ROLE_CATEGORIES = (
    ("instruments", "instrument"),
    ("midi_effects", "midi_effect"),
    ("audio_effects", "audio_effect"),
)

__all__ = ["insert_params"]


def insert_params(call: Call, track_index: int, device_name: str) -> dict[str, Any]:
    """Return the Extension request that puts ``device_name`` where Live accepts it.

    ``call`` is a Remote Script call. A name the browser does not list gets no
    index, so the Extension appends it and Live decides.
    """
    params: dict[str, Any] = {"track_index": track_index, "device_name": device_name}
    found = _browser_device(call, device_name)
    if found is None:
        return params
    params["device_name"], role = found
    devices = call("get_device_list", {"track_index": track_index})
    params["device_index"] = _insert_index(role, list(devices or []), track_index)
    return params


def _browser_device(call: Call, device_name: str) -> tuple[str, str] | None:
    """Find a built-in device by name; return the browser's spelling and its role."""
    wanted = device_name.casefold()
    for category, role in _ROLE_CATEGORIES:
        items = call(
            "search_browser",
            {"query": device_name, "category_type": category, "limit": 200, "max_depth": 1},
        )
        for item in items or []:
            name = str(item.get("name", ""))
            if name.casefold() == wanted:
                return name, role
    return None


def _insert_index(role: str, devices: list[dict[str, Any]], track_index: int) -> int:
    """Return the first index Live accepts for a device of ``role`` in ``devices``.

    A MIDI effect goes after the MIDI effects already there, an instrument
    before the first audio effect, an audio effect at the end. A device with
    no ``type`` (an older Remote Script) counts as ``undefined``.
    """
    types = [str(device.get("type", "undefined")) for device in devices]
    if role == "audio_effect":
        return len(types)
    if role == "midi_effect":
        return next((i for i, kind in enumerate(types) if kind != "midi_effect"), len(types))
    held = [str(device.get("name", "")) for device in devices if device.get("type") == "instrument"]
    if held:
        raise BadInputError(
            f"Track {track_index} already holds the instrument {held[0]!r}; Live keeps one "
            "instrument per device chain. Load the new one onto a MIDI track without an "
            "instrument, or remove the current one in Live first.",
            "Live refuses a second instrument in a chain; use an Instrument Rack to layer them.",
        )
    return next((i for i, kind in enumerate(types) if kind == "audio_effect"), len(types))
