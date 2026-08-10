"""Strict fake bridge used by the acceptance runner tests.

This fake mirrors the real bridge contracts documented in
``ableton_mcp_server.contracts``:

- Unknown commands / methods raise ``RuntimeError("UNKNOWN_COMMAND")`` so
  the runner cannot greenwash by relying on a permissive fallback.
- Required fields per command are enforced; the real contract quirks
  (``automation_points`` vs ``points``, ``property+value`` vs ``name``,
  ``track_id`` vs ``track_index/device_index``) are validated.
- TCP vs WebSocket routing is recorded per call so the runner cannot
  silently route a WS tool over TCP.

The fake also simulates a small three-track disposable Set:

- Track 0 (midi) "Bass" with slot 3 empty for the MIDI mutation surface.
- Track 1 (audio) "Drums" with slot 0 occupied by an audio clip with
  warp disabled.
- Track 2 (audio) "Samp" with slot 0 occupied by an audio clip with
  warp disabled (this is the ``audio_track_index`` for warp/load tests).
- Each track carries one device with one named parameter so
  ``list_device_params`` and ``set_parameter_value`` can run honestly.

This file is imported by both ``test_acceptance_runner_integration.py``
and ``test_fake_bridge_strict.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ableton_mcp_server.errors import CapabilityUnavailableError
from contracts import CAPABILITY_EVIDENCE, UNSUPPORTED_CAPABILITIES

# ---------------------------------------------------------------------------
# Contract specs
# ---------------------------------------------------------------------------

_TCP_COMMAND_FIELDS: dict[str, dict[str, Any]] = {
    "get_session_info": {},
    "get_track_list": {},
    "get_track_state": {"track_index": int},
    "get_locators": {},
    "take_snapshot": {},
    "get_control_surfaces": {},
    "get_scenes": {},
    "get_scene_state": {"scene_index": int},
    "get_project_metadata": {},
    "get_loop_settings": {},
    "get_selected_context": {},
    "get_clip_summary": {"track_index": int},
    "get_clip_notes": {"track_index": int, "clip_index": int},
    "get_clip_info": {"track_index": int, "clip_index": int},
    "get_device_list": {"track_index": int},
    "get_parameter_value": {
        "track_index": int,
        "device_index": int,
        "parameter_name": str,
    },
    "get_routing": {"track_index": int},
    "get_browser_categories": {},
    "search_browser": {"query": str, "limit": int},
    "get_song_length": {},
    "live_find_track": {"query": str},
    "live_find_device": {"track_index": int, "query": str},
    "live_find_clip": {"track_index": int, "query": str},
    "list_device_params": {"track_id": str},
    "get_composition_structure": {},
    "diagnose_midi_clip": {"track_index": int, "clip_index": int},
    "lifecycle_status": {},
    "create_cue_point": {"name": str, "time": float},
    "bulk_create_cue_points": {"items": list},
    "delete_cue_point": {"time": float},
    "set_current_song_time": {"time": float},
    "set_tempo": {"tempo": float},
    "start_playback": {},
    "stop_playback": {},
    "set_loop": {"enabled": bool},
    "set_loop_start": {"start_beat": float},
    "set_loop_length": {"length_beats": float},
    "run_batch": {"commands": list},
    "add_notes_to_clip": {
        "track_index": int,
        "clip_index": int,
        "notes": list,
    },
    "fire_clip": {"track_index": int, "clip_index": int},
    "create_clip": {
        "track_index": int,
        "clip_index": int,
        "length_beats": float,
    },
    "delete_clip": {"track_index": int, "clip_index": int},
    "clear_clip_notes": {"track_index": int, "clip_index": int},
    "fire_scene": {"scene_index": int},
    "set_track_property": {
        "track_index": int,
        "property": str,
        "value": bool,
    },
    "set_track_color": {"track_index": int},
    "set_clip_color": {"track_index": int, "clip_index": int},
    "diagnose_clip_targets": {},
    # Validated like any other command, then refused: no public Live API can
    # perform these. The fake mirrors the Remote Script's ordering so a probe
    # cannot pass here and fail against the real bridge.
    "move_track": {"track_index": int, "destination_index": int},
    "reorder_tracks": {"order": list},
    "move_track_to_group": {"track_index": int, "group_track_index": int},
    "ungroup_track": {"track_index": int},
    "merge_groups": {"source_group_index": int, "destination_group_index": int},
    "set_clip_properties": {
        "track_index": int,
        "clip_index": int,
    },
    "create_clip_automation": {
        "track_index": int,
        "clip_index": int,
        "parameter_name": str,
        "automation_points": list,
    },
    "create_midi_track": {},
    "create_audio_track": {},
    "rename_track": {"track_index": int, "new_name": str},
    "set_parameter_value": {
        "track_index": int,
        "device_index": int,
        "parameter_name": str,
        "value": float,
    },
    "save_set": {},
    "live_fade": {
        "track_index": int,
        "target_percent": (int, float),
        "duration": (int, float),
        "steps": int,
    },
}


_WS_METHOD_FIELDS: dict[str, dict[str, Any]] = {
    "get_warp_state": {"track_index": int, "clip_index": int},
    "set_warp_state": {"track_index": int, "clip_index": int, "warping": bool},
    "load_device_to_track": {"track_index": int, "device_name": str},
}


# Hierarchy fields every ``get_track_list`` row carries. The disposable Set
# has no Group Track, so all three tracks are ungrouped and visible.
_HIERARCHY_DEFAULTS: dict[str, Any] = {
    "color": 0x000000,
    "color_index": 0,
    "is_group_track": False,
    "is_grouped": False,
    "group_track_index": None,
    "group_track_id": None,
    "is_visible": True,
    "fold_state": 0,
}

# Keys ``get_track_list`` is allowed to expose: identity plus hierarchy.
# Mixer state (mute/solo/arm/volume) is deliberately absent — it lives on
# ``get_track_state`` only.
_TRACK_LIST_KEYS: tuple[str, ...] = (
    "id",
    "index",
    "name",
    "type",
    *_HIERARCHY_DEFAULTS,
)


# ---------------------------------------------------------------------------
# The fake itself
# ---------------------------------------------------------------------------


class StrictFakeBridge:
    """In-process fake that mirrors the real bridge contracts."""

    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 9888
        self.fail_tool: str | None = None
        self.save_set_response: dict[str, Any] | None = None
        self.tcp_calls: list[tuple[str, dict[str, Any]]] = []
        self.ws_calls: list[tuple[str, dict[str, Any]]] = []
        self.timeline_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.state: dict[str, Any] = self._initial_state()

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        # Three-track disposable Set: Bass (midi, no clip), Drums (audio,
        # one clip), Samp (audio, one clip with warp disabled).
        return {
            "tempo": 120.0,
            "current_song_time": 0.0,
            "loop": False,
            "loop_start": 0.0,
            "loop_length": 4.0,
            "is_playing": False,
            "locators": [],
            "tracks": [
                {
                    **_HIERARCHY_DEFAULTS,
                    "index": 0,
                    "type": "midi",
                    "name": "Bass",
                    "id": "track:0",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "color": 0x336699,
                    "color_index": 3,
                    "devices": [{"name": "MIDI Device", "parameters": ["Device On"]}],
                },
                {
                    **_HIERARCHY_DEFAULTS,
                    "index": 1,
                    "type": "audio",
                    "name": "Drums",
                    "id": "track:1",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "color": 0x996633,
                    "color_index": 7,
                    "devices": [{"name": "Audio Device", "parameters": ["Volume"]}],
                },
                {
                    **_HIERARCHY_DEFAULTS,
                    "index": 2,
                    "type": "audio",
                    "name": "Samp",
                    "id": "track:2",
                    "mute": False,
                    "solo": False,
                    "arm": False,
                    "color": 0x669933,
                    "color_index": 11,
                    "devices": [{"name": "Sampler", "parameters": ["Volume"]}],
                },
            ],
            "clips": {
                (1, 0): {
                    "name": "Drums Clip",
                    "is_audio_clip": True,
                    "is_midi_clip": False,
                    "has_clip": True,
                    "length": 4.0,
                    "notes": [],
                },
                (2, 0): {
                    "name": "Samp Clip",
                    "is_audio_clip": True,
                    "is_midi_clip": False,
                    "has_clip": True,
                    "length": 4.0,
                    "notes": [],
                },
            },
            "browser_categories": ["Audio Effects", "MIDI Effects", "Instruments", "Samples"],
            "device_parameters": {
                "track:0": [{"name": "Device On", "value": 1.0}],
                "track:1": [{"name": "Volume", "value": 0.85}],
                "track:2": [{"name": "Volume", "value": 0.85}],
            },
            "warp": {"warping": False, "warp_mode": "beats"},
            "search_browser_queries": [],
            "is_dirty": False,
            "song_length": 64.0,
        }

    # --- AcceptanceClient surface ---

    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        params = dict(params or {})
        self.tcp_calls.append((command_type, params))
        self.timeline_calls.append(("tcp", command_type, params))
        if self.fail_tool and command_type == self.fail_tool:
            raise RuntimeError(f"forced failure on {command_type}")
        return _strict_tcp_dispatch(self, command_type, params)

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> Any:
        params = dict(params or {})
        self.ws_calls.append((method, params))
        self.timeline_calls.append(("ws", method, params))
        if self.fail_tool and method == self.fail_tool:
            raise RuntimeError(f"forced failure on {method}")
        return _strict_ws_dispatch(self, method, params)


# ---------------------------------------------------------------------------
# TCP dispatch
# ---------------------------------------------------------------------------


def _validate_tcp(command: str, params: dict[str, Any]) -> None:
    spec = _TCP_COMMAND_FIELDS.get(command)
    if spec is None:
        raise RuntimeError(f"UNKNOWN_COMMAND: {command}")
    for field, expected in spec.items():
        if field not in params:
            # ``live_fade`` accepts either ``target_percent`` OR
            # ``target_value`` (validated by the Remote Script
            # generator); the strict fake mirrors that flexibility.
            if (
                command == "live_fade"
                and field in ("target_percent", "target_value")
                and ("target_percent" in params or "target_value" in params)
            ):
                continue
            raise RuntimeError(f"MISSING_FIELD: {command}.{field}")
        if isinstance(expected, type):
            if not isinstance(params[field], expected):
                raise RuntimeError(
                    f"BAD_FIELD_TYPE: {command}.{field} expected {expected.__name__}"
                )
        elif isinstance(expected, tuple) and not isinstance(params[field], expected):
            raise RuntimeError(f"BAD_FIELD_TYPE: {command}.{field}")
    # Per-command field quirks. Each command has its own ``if`` because the
    # rejection conditions and error messages differ. Combining them
    # would obscure which contract each guard belongs to.
    if command == "set_track_property" and "name" in params:  # noqa: SIM102
        raise RuntimeError("BAD_FIELD: set_track_property uses property+value, not name")
    if command == "create_clip_automation" and "points" in params:  # noqa: SIM102
        raise RuntimeError("BAD_FIELD: create_clip_automation uses automation_points, not points")
    if command == "list_device_params" and ("track_index" in params or "device_index" in params):  # noqa: SIM102
        raise RuntimeError(
            "BAD_FIELD: list_device_params uses track_id, not track_index/device_index"
        )
    if command == "set_track_color":
        # The real contract requires exactly one colour source; accepting both
        # (or neither) here would let a probe pass against a request the
        # Remote Script rejects with INVALID_PARAMS.
        provided = [name for name in ("color_index", "color") if name in params]
        if len(provided) != 1:
            raise RuntimeError("BAD_FIELD: set_track_color needs exactly one of color_index/color")
        if not isinstance(params[provided[0]], int) or isinstance(params[provided[0]], bool):
            raise RuntimeError(f"BAD_FIELD_TYPE: set_track_color.{provided[0]} expected int")


_READ_ONLY_TCP_COMMANDS = {
    "get_project_metadata",
    "get_track_list",
    "get_track_state",
    "get_clip_summary",
    "get_session_info",
    "get_loop_settings",
    "get_locators",
    "get_scenes",
    "get_scene_state",
    "get_clip_notes",
    "get_clip_info",
    "get_device_list",
    "get_parameter_value",
    "get_routing",
    "get_browser_categories",
    "search_browser",
    "get_song_length",
    "live_find_track",
    "live_find_device",
    "live_find_clip",
    "list_device_params",
    "get_composition_structure",
    "diagnose_midi_clip",
    "lifecycle_status",
    "take_snapshot",
    "get_control_surfaces",
    "get_selected_context",
    "diagnose_clip_targets",
    # Refusals never touch the Set, so they must not mark it dirty either.
    "move_track",
    "reorder_tracks",
    "move_track_to_group",
    "ungroup_track",
    "merge_groups",
}


def _validate_hierarchy(state: dict[str, Any], command: str, params: dict[str, Any]) -> None:
    """Reject malformed hierarchy requests before the capability refusal.

    Mirrors ``_validate_hierarchy_request`` in the Remote Script closely
    enough that a probe cannot pass here and fail against the real bridge.
    """

    tracks = {int(track["index"]): track for track in state["tracks"]}
    regular = sorted(idx for idx, track in tracks.items() if track["type"] in ("midi", "audio"))

    def require_regular(index: int, label: str) -> dict[str, Any]:
        if index not in tracks:
            raise RuntimeError(f"INVALID_PARAMS: {label}={index} does not exist")
        if tracks[index]["type"] in ("return", "master"):
            raise RuntimeError(f"WRONG_TYPE: {label}={index} is a return/main track")
        return tracks[index]

    def require_group(index: int, label: str) -> dict[str, Any]:
        track = require_regular(index, label)
        if not track.get("is_group_track", False):
            raise RuntimeError(f"WRONG_TYPE: {label}={index} is not a Group Track")
        return track

    if command == "move_track":
        require_regular(params["track_index"], "track_index")
        if params["destination_index"] not in regular:
            raise RuntimeError("INVALID_PARAMS: destination_index outside the regular tracks")
    elif command == "reorder_tracks":
        if sorted(params["order"]) != regular:
            raise RuntimeError("BAD_INPUT: order must be a permutation of the regular tracks")
    elif command == "move_track_to_group":
        require_regular(params["track_index"], "track_index")
        require_group(params["group_track_index"], "group_track_index")
        if params["track_index"] == params["group_track_index"]:
            raise RuntimeError("BAD_INPUT: a group cannot contain itself")
    elif command == "ungroup_track":
        track = require_regular(params["track_index"], "track_index")
        if not track.get("is_grouped", False):
            raise RuntimeError("WRONG_TYPE: track is not inside a Group Track")
    elif command == "merge_groups":
        if params.get("delete_empty_source", False):
            raise RuntimeError("BAD_INPUT: delete_empty_source is never supported")
        require_group(params["source_group_index"], "source_group_index")
        require_group(params["destination_group_index"], "destination_group_index")
        if params["source_group_index"] == params["destination_group_index"]:
            raise RuntimeError("BAD_INPUT: source and destination groups must differ")


def _strict_tcp_dispatch(bridge: StrictFakeBridge, command: str, params: dict[str, Any]) -> Any:
    _validate_tcp(command, params)
    s = bridge.state
    if command not in _READ_ONLY_TCP_COMMANDS and command != "save_set":
        s.update({"is_dirty": True})
    if command == "get_project_metadata":
        return {"song_name": "TESTE_CODEX", "is_dirty": bool(s.get("is_dirty", False))}
    if command == "get_track_list":
        # The real ``get_track_list`` contract returns identity plus the
        # hierarchy/colour fields. Mixer state (mute, solo, arm, volume)
        # lives on ``get_track_state``; including those fields here would
        # let the runner invent defaults that bypass the mixer readback.
        return [{k: t[k] for k in _TRACK_LIST_KEYS if k in t} for t in s["tracks"]]
    if command == "get_track_state":
        idx = params["track_index"]
        track = next((t for t in s["tracks"] if t["index"] == idx), None)
        if track is None:
            return {"track_index": idx, "exists": False}
        # Mixer volume lives on ``track.mixer_device.volume`` — a
        # separate channel from device parameters. The fake keeps it
        # on ``state["mixer_volumes"][track_id]`` and falls back to the
        # track's own field, then to Live's default unity (0.85).
        mixer_volume = float(s.get("mixer_volumes", {}).get(f"track:{idx}", 0.85))
        return {
            "track_index": idx,
            "name": track["name"],
            "type": track["type"],
            "mute": track.get("mute", False),
            "solo": track.get("solo", False),
            "arm": track.get("arm", False),
            "device_count": len(track.get("devices", [])),
            "volume": mixer_volume,
            "color": track.get("color", 0),
            "color_index": track.get("color_index", 0),
            "is_group_track": track.get("is_group_track", False),
            "is_grouped": track.get("is_grouped", False),
            "group_track_index": track.get("group_track_index"),
            "group_track_id": track.get("group_track_id"),
            "is_visible": track.get("is_visible", True),
            "fold_state": track.get("fold_state", 0),
        }
    if command == "get_clip_summary":
        track = params["track_index"]
        slots = []
        for i in range(8):
            clip = s["clips"].get((track, i))
            slots.append(
                {
                    "index": i,
                    "has_clip": clip is not None,
                    "is_midi_clip": clip is not None and clip.get("is_midi_clip", False),
                }
            )
        return slots
    if command == "get_session_info":
        return {
            "tempo": s["tempo"],
            "current_song_time": s["current_song_time"],
            "is_playing": s.get("is_playing", False),
        }
    if command == "get_loop_settings":
        return {"loop": s["loop"], "loop_start": s["loop_start"], "loop_length": s["loop_length"]}
    if command == "get_locators":
        return list(s["locators"])
    if command == "get_scenes":
        return [{"index": 0, "name": "Scene 1"}]
    if command == "get_scene_state":
        return {"scene_index": params["scene_index"], "tracks": []}
    if command == "get_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        return list(clip.get("notes", [])) if clip else []
    if command == "get_clip_info":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        if clip is None:
            return {
                "track_index": track,
                "clip_index": slot,
                "has_clip": False,
                "name": "",
                "is_audio_clip": False,
                "is_midi_clip": False,
            }
        return {
            "track_index": track,
            "clip_index": slot,
            "has_clip": True,
            "name": clip.get("name", ""),
            "length": clip.get("length", 4.0),
            "is_audio_clip": clip.get("is_audio_clip", False),
            "is_midi_clip": clip.get("is_midi_clip", False),
            "color": clip.get("color", 0),
            "color_index": clip.get("color_index", 0),
        }
    if command == "get_device_list":
        track = params["track_index"]
        for t in s["tracks"]:
            if t["index"] == track:
                return list(t.get("devices", []))
        return []
    if command == "get_parameter_value":
        track_id = f"track:{params['track_index']}"
        device_index = int(params.get("device_index", 0))
        entries = s["device_parameters"].get(track_id, [])
        if device_index < 0 or device_index >= len(entries):
            raise RuntimeError(
                f"BAD_DEVICE_INDEX: {device_index} (track has {len(entries)} devices)"
            )
        entry = entries[device_index]
        name = params["parameter_name"]
        if "parameters" in entry:
            for nested in entry["parameters"]:
                if nested.get("name") == name:
                    return {"value": nested.get("value", 0.0)}
        elif entry.get("name") == name:
            return {"value": entry.get("value", 0.0)}
        raise RuntimeError(f"PARAMETER_NOT_FOUND: {name} on {track_id}/device:{device_index}")
    if command == "get_routing":
        return {"input_routing": "In 1", "output_routing": "Master"}
    if command == "get_browser_categories":
        return list(s["browser_categories"])
    if command == "search_browser":
        s["search_browser_queries"].append(params["query"])
        # For the runner's query "o" return some results; otherwise empty.
        if params.get("query") == "o":
            return [{"name": "Operator", "uri": "query:Operator#0"}]
        return []
    if command == "get_song_length":
        return {"song_length": float(s.get("song_length", 64.0))}
    if command == "live_find_track":
        q = params["query"].lower()
        return [t for t in s["tracks"] if q in t["name"].lower()]
    if command == "live_find_device":
        q = params["query"].lower()
        t = next((x for x in s["tracks"] if x["index"] == params["track_index"]), None)
        return [d for d in t.get("devices", []) if q in d.get("name", "").lower()] if t else []
    if command == "live_find_clip":
        q = params["query"].lower()
        idx = params["track_index"]
        return [
            {"name": c.get("name", "")}
            for (t_idx, _), c in s.get("clips", {}).items()
            if t_idx == idx and q in c.get("name", "").lower()
        ]
    if command == "list_device_params":
        # Mirrors the real handler: ``[{device_id, device_name,
        # parameters: [{name, value, min, max}]}]``. The runner must
        # descend into the nested ``parameters`` list to discover
        # writable parameters, and remember each entry's position as
        # the device_index to use on subsequent writes. ``device_id``
        # is unique per device (not always ``device:0``).
        track_id = params["track_id"]
        entries = []
        for entry_index, entry in enumerate(s["device_parameters"].get(track_id, [])):
            if "parameters" in entry:
                nested = entry["parameters"]
            elif "name" in entry:
                nested = [
                    {
                        "name": entry["name"],
                        "value": entry.get("value", 0.0),
                        "min": 0.0,
                        "max": 1.0,
                    }
                ]
            else:
                nested = []
            entries.append(
                {
                    "device_id": f"{track_id}/device:{entry_index}",
                    "device_name": entry.get("device_name", f"Device of {track_id}"),
                    "parameters": nested,
                }
            )
        return entries
    if command == "get_composition_structure":
        return {"track_count": len(s["tracks"]), "scene_count": 1, "unnamed_tracks": []}
    if command == "diagnose_midi_clip":
        return {"issues": [], "scale_conformant": True}
    if command == "lifecycle_status":
        return {"song_save_available": True, "app_quit_available": False}
    if command == "set_tempo":
        s["tempo"] = params["tempo"]
        return {"tempo": s["tempo"]}
    if command == "set_current_song_time":
        s["current_song_time"] = params["time"]
        return {"time": s["current_song_time"]}
    if command == "set_loop":
        s["loop"] = params["enabled"]
        return {"loop": s["loop"]}
    if command == "set_loop_start":
        s["loop_start"] = params["start_beat"]
        return {"loop_start": s["loop_start"]}
    if command == "set_loop_length":
        s["loop_length"] = params["length_beats"]
        return {"loop_length": s["loop_length"]}
    if command == "create_cue_point":
        song_length = float(s.get("song_length", 64.0))
        cue_time = float(params["time"])
        if cue_time > song_length + 1e-6:
            raise RuntimeError(
                f"Cannot set the Songtime behind the Songlength: "
                f"time={cue_time} song_length={song_length}"
            )
        cue = {"name": params["name"], "time": cue_time}
        s["locators"].append(cue)
        return {"name": cue["name"], "time": cue["time"]}
    if command == "delete_cue_point":
        song_length = float(s.get("song_length", 64.0))
        cue_time = float(params["time"])
        if cue_time > song_length + 1e-6:
            # Mirror Live: deleting an out-of-range cue returns deleted=false
            # rather than raising, because the locator never existed.
            return {"deleted": False}
        before = len(s["locators"])
        s["locators"] = [c for c in s["locators"] if abs(c["time"] - cue_time) > 0.01]
        return {"deleted": len(s["locators"]) < before}
    if command == "bulk_create_cue_points":
        song_length = float(s.get("song_length", 64.0))
        for item in params["items"]:
            t = float(item["time"])
            if t > song_length + 1e-6:
                raise RuntimeError(
                    f"Cannot set the Songtime behind the Songlength: "
                    f"time={t} song_length={song_length}"
                )
            s["locators"].append({"name": item["name"], "time": t})
        return {"created": len(params["items"])}
    if command == "create_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"][(track, slot)] = {
            "name": "",
            "is_audio_clip": False,
            "is_midi_clip": True,
            "has_clip": True,
            "length": params.get("length_beats", 4.0),
            "notes": [],
        }
        return {"track_index": track, "clip_index": slot}
    if command == "add_notes_to_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault(
            (track, slot),
            {
                "name": "",
                "is_audio_clip": False,
                "is_midi_clip": True,
                "has_clip": True,
                "length": 4.0,
                "notes": [],
            },
        )
        s["clips"][(track, slot)]["notes"] = list(params["notes"])
        return {"added": len(params["notes"])}
    if command == "clear_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        if (track, slot) in s["clips"]:
            s["clips"][(track, slot)]["notes"] = []
        return {"cleared": True}
    if command == "set_clip_properties":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault(
            (track, slot),
            {
                "name": "",
                "is_audio_clip": False,
                "is_midi_clip": True,
                "has_clip": True,
                "length": 4.0,
                "notes": [],
            },
        )
        if "name" in params:
            s["clips"][(track, slot)]["name"] = params["name"]
        return {"name": params.get("name", "")}
    if command == "create_clip_automation":
        return {"points_written": len(params["automation_points"])}
    if command == "start_playback":
        s["is_playing"] = True
        return {"playing": True}
    if command == "stop_playback":
        s["is_playing"] = False
        return {"playing": False}
    if command == "fire_clip":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        if clip is None:
            raise RuntimeError(f"fire_clip: empty slot {track}:{slot}")
        s["is_playing"] = True
        return {"fired": True, "track_index": track, "clip_index": slot}
    if command == "run_batch":
        # Honest partial-batch: create_clip after populated slot fails at
        # index 2 (commands[2]).
        return {"completed": 2, "aborted_at": 2, "rolled_back": False}
    if command == "fire_scene":
        s["is_playing"] = True
        return {"scene_index": params["scene_index"], "fired": True}
    if command == "set_track_property":
        idx = params["track_index"]
        for track in s["tracks"]:
            if track["index"] == idx:
                track[params["property"]] = params["value"]
        return {"property": params["property"], "value": params["value"]}
    if command in UNSUPPORTED_CAPABILITIES:
        # Mirror the Remote Script: validate first so a malformed request is
        # still distinguishable, then refuse with the typed error.
        _validate_hierarchy(s, command, params)
        raise CapabilityUnavailableError(
            UNSUPPORTED_CAPABILITIES[command],
            "The request is well-formed; Live's public API has no operation that "
            "performs it. Nothing was changed in the Set.",
            details={**CAPABILITY_EVIDENCE[command], "request": dict(params), "applied": False},
        )
    if command == "diagnose_clip_targets":
        tracks = []
        session_total = 0
        for track in s["tracks"]:
            session = [
                {
                    "id": f"track:{track['index']}/clipslot:{slot}/clip",
                    "scope": "session",
                    "track_index": track["index"],
                    "clip_index": slot,
                    "name": clip.get("name", ""),
                    "is_midi_clip": clip.get("is_midi_clip", False),
                    "color": clip.get("color", 0),
                    "color_index": clip.get("color_index", 0),
                    "colorable": True,
                }
                for (t_idx, slot), clip in sorted(s["clips"].items())
                if t_idx == track["index"]
            ]
            session_total += len(session)
            tracks.append(
                {
                    "track_index": track["index"],
                    "track_id": track["id"],
                    "name": track["name"],
                    "type": track["type"],
                    "session_clips": session,
                    "arrangement_clips": [],
                    # The disposable Set has no Arrangement clips; the lane is
                    # still reported as supported so the runner exercises the
                    # "supported and empty" branch.
                    "arrangement_supported": True,
                }
            )
        return {
            "tracks": tracks,
            "session_clip_count": session_total,
            "arrangement_clip_count": 0,
            "inaccessible": [],
        }
    if command == "set_clip_color":
        if params.get("scope", "session") != "session":
            raise RuntimeError("BAD_FIELD: fake Set has no Arrangement clips")
        key = (params["track_index"], params["clip_index"])
        clip = s["clips"].get(key)
        if clip is None:
            raise RuntimeError(f"set_clip_color: empty slot {key}")
        provided = [name for name in ("color_index", "color") if name in params]
        if len(provided) != 1:
            raise RuntimeError("BAD_FIELD: set_clip_color needs exactly one colour source")
        clip[provided[0]] = int(params[provided[0]])
        clip_id = f"track:{key[0]}/clipslot:{key[1]}/clip"
        return {
            "clip_id": clip_id,
            "scope": "session",
            "track_index": key[0],
            "clip_index": key[1],
            "property": provided[0],
            "color": clip.get("color", 0),
            "color_index": clip.get("color_index", 0),
            "resolved": {
                "kind": "clip",
                "track_index": key[0],
                "clip_index": key[1],
                "scope": "session",
                "clip_id": clip_id,
            },
        }
    if command == "set_track_color":
        idx = params["track_index"]
        target = next((t for t in s["tracks"] if t["index"] == idx), None)
        if target is None:
            raise RuntimeError(f"BAD_TRACK_INDEX: {idx}")
        if "color_index" in params:
            target["color_index"] = int(params["color_index"])
            attribute = "color_index"
        else:
            target["color"] = int(params["color"])
            attribute = "color"
        return {
            "track_id": f"track:{idx}",
            "track_index": idx,
            "property": attribute,
            "color": target.get("color", 0),
            "color_index": target.get("color_index", 0),
            "resolved": {"kind": "track", "track_index": idx, "track_name": target["name"]},
        }
    if command == "rename_track":
        idx = params["track_index"]
        for track in s["tracks"]:
            if track["index"] == idx:
                track["name"] = params["new_name"]
        return {"new_name": params["new_name"]}
    if command == "delete_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].pop((track, slot), None)
        return {"deleted": True}
    if command in ("create_audio_track", "create_midi_track"):
        kind = "audio" if command == "create_audio_track" else "midi"
        reg_tracks = [t for t in s["tracks"] if t.get("type") in ("midi", "audio")]
        insert_idx = len(reg_tracks)
        for t in s["tracks"]:
            if t["index"] >= insert_idx:
                t["index"] += 1
                t["id"] = f"track:{t['index']}"
        s["tracks"].append(
            {
                **_HIERARCHY_DEFAULTS,
                "index": insert_idx,
                "type": kind,
                "name": "",
                "id": f"track:{insert_idx}",
                "mute": False,
                "solo": False,
                "arm": False,
                "devices": [],
            }
        )
        s["tracks"].sort(key=lambda t: t["index"])
        return {"track_index": insert_idx}
    if command == "set_parameter_value":
        track_id = f"track:{params['track_index']}"
        device_index = int(params.get("device_index", 0))
        entries = s["device_parameters"].get(track_id, [])
        if device_index < 0 or device_index >= len(entries):
            raise RuntimeError(
                f"BAD_DEVICE_INDEX: {device_index} (track has {len(entries)} devices)"
            )
        entry = entries[device_index]
        name = params["parameter_name"]
        if "parameters" in entry:
            for nested in entry["parameters"]:
                if nested.get("name") == name:
                    nested["value"] = float(params["value"])
                    return {"value": float(params["value"])}
        elif entry.get("name") == name:
            entry["value"] = float(params["value"])
            return {"value": float(params["value"])}
        raise RuntimeError(f"PARAMETER_NOT_FOUND: {name} on {track_id}/device:{device_index}")
    if command == "live_fade":
        # Honest live_fade: update the track's mixer volume so the
        # runner's post-fade readback can verify the target landed.
        # The mixer is NOT a device parameter — the real bridge writes
        # to ``track.mixer_device.volume`` directly. We mirror that
        # by keeping a separate ``mixer_volumes`` dict on state.
        track_id = f"track:{params['track_index']}"
        target_percent = params.get("target_percent")
        target_value = params.get("target_value")
        if target_percent is not None:
            # Match the Remote Script's
            # ``AbletonMCPServer_RemoteScript/__init__.py``
            # ``LIVE_FADE_UNITY_VALUE`` factor: ``target_percent=100``
            # maps to ``0.85``, not ``1.0``. Without this, the runner's
            # post-fade readback in
            # ``tests/test_acceptance_live_fade_percent.py`` cannot
            # observe the actual Live behaviour, and any acceptance
            # probe that asserts on ``volume`` drifts.
            target_value = float(target_percent) / 100.0 * 0.8500000238418579
        if target_value is not None:
            target_value = float(target_value)
            s.setdefault("mixer_volumes", {})[track_id] = max(
                0.0,
                min(1.0, target_value),
            )
        return {"final_value": target_value}
    if command == "save_set":
        if bridge.save_set_response is not None:
            return dict(bridge.save_set_response)
        s.update({"is_dirty": False})
        return {"saved": True, "api_available": True, "result": None}
    if command == "take_snapshot":
        return {
            "schema_version": 1,
            "captured_at_unix_ms": 0,
            "live_version": "12.0",
            "tempo": float(s["tempo"]),
            "signature_numerator": 4,
            "signature_denominator": 4,
            "is_playing": bool(s.get("is_playing", False)),
            "current_song_time": float(s["current_song_time"]),
            "tracks": [
                {"index": t["index"], "name": t["name"], "type": t["type"]} for t in s["tracks"]
            ],
            "control_surfaces": list(s.get("control_surfaces", [])),
            "browser_categories_count": len(s["browser_categories"]),
        }
    if command == "get_control_surfaces":
        return list(s.get("control_surfaces", []))
    if command == "get_selected_context":
        return {"track": None, "scene": None, "device": None}
    raise RuntimeError(f"UNKNOWN_TCP_COMMAND: {command}")


# ---------------------------------------------------------------------------
# WebSocket dispatch
# ---------------------------------------------------------------------------


def _strict_ws_dispatch(bridge: StrictFakeBridge, method: str, params: dict[str, Any]) -> Any:
    spec = _WS_METHOD_FIELDS.get(method)
    if spec is None:
        raise RuntimeError(f"UNKNOWN_WS_METHOD: {method}")
    for field, expected in spec.items():
        if field not in params:
            raise RuntimeError(f"MISSING_FIELD: {method}.{field}")
        if isinstance(expected, type) and not isinstance(params[field], expected):
            raise RuntimeError(f"BAD_FIELD_TYPE: {method}.{field} expected {expected.__name__}")
    s = bridge.state
    if method in ("set_warp_state", "load_device_to_track"):
        s.update({"is_dirty": True})
    if method == "get_warp_state":
        return dict(s["warp"])
    if method == "set_warp_state":
        s["warp"]["warping"] = params["warping"]
        return dict(s["warp"])
    if method == "load_device_to_track":
        target = params["track_index"]
        device_name = params["device_name"]
        device_index = None
        for track in s["tracks"]:
            if track["index"] == target:
                devs = track.setdefault("devices", [])
                device_index = len(devs)
                devs.append({"name": device_name})
                break
        return {
            "status": "loaded",
            "track_index": target,
            "device_name": device_name,
            "device_index": device_index,
        }
    raise RuntimeError(f"UNKNOWN_WS_METHOD: {method}")
