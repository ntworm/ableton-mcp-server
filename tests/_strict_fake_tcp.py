"""TCP command dispatch for the strict fake bridge: one handler per group."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from contracts import UNSUPPORTED_CAPABILITIES

from ._fake_device_chain import typed_devices

if TYPE_CHECKING:
    from ._strict_fake import StrictFakeBridge


def _handle_session(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the session, transport and locator read commands."""
    if command == "get_session_info":
        return {
            "tempo": s["tempo"], "current_song_time": s["current_song_time"],
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
    if command == "get_song_length":
        return {"song_length": float(s.get("song_length", 64.0))}
    if command == "get_routing":
        return {"input_routing": "In 1", "output_routing": "Master"}
    if command == "get_control_surfaces":
        return list(s.get("control_surfaces", []))

def _handle_project(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the project, browser category and snapshot read commands."""
    if command == "get_project_metadata":
        return {"song_name": "TESTE_CODEX", "is_dirty": s["is_dirty"], "can_undo": s["can_undo"]}
    if command == "get_composition_structure":
        return {"track_count": len(s["tracks"]), "scene_count": 1, "unnamed_tracks": []}
    if command == "diagnose_midi_clip":
        return {"issues": [], "scale_conformant": True}
    if command == "lifecycle_status":
        return {"song_save_available": True, "app_quit_available": False}
    if command == "get_browser_categories":
        return list(s["browser_categories"])
    if command == "get_selected_context":
        return {"track": None, "scene": None, "device": None}
    if command == "take_snapshot":
        return {
            "schema_version": 1, "captured_at_unix_ms": 0, "live_version": "12.0",
            "tempo": float(s["tempo"]), "signature_numerator": 4, "signature_denominator": 4,
            "is_playing": bool(s.get("is_playing", False)),
            "current_song_time": float(s["current_song_time"]),
            "tracks": [
                {"index": t["index"], "name": t["name"], "type": t["type"]} for t in s["tracks"]
            ],
            "control_surfaces": list(s.get("control_surfaces", [])),
            "browser_categories_count": len(s["browser_categories"]),
        }

def _handle_clips(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the clip summary, notes, info and automation read commands."""
    if command == "get_clip_summary":
        track = params["track_index"]
        slots = []
        for i in range(8):
            clip = s["clips"].get((track, i))
            slots.append({
                "index": i, "has_clip": clip is not None,
                "is_midi_clip": clip is not None and clip.get("is_midi_clip", False),
            })
        return slots
    if command == "get_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        return list(clip.get("notes", [])) if clip else []
    if command == "get_clip_info":
        track, slot = params["track_index"], params["clip_index"]
        clip = s["clips"].get((track, slot))
        if clip is None:
            return {
                "track_index": track, "clip_index": slot, "has_clip": False,
                "name": "", "is_audio_clip": False, "is_midi_clip": False,
            }
        return {
            "track_index": track, "clip_index": slot, "has_clip": True,
            "name": clip.get("name", ""), "length": clip.get("length", 4.0),
            "is_audio_clip": clip.get("is_audio_clip", False),
            "is_midi_clip": clip.get("is_midi_clip", False),
            "color": clip.get("color", 0), "color_index": clip.get("color_index", 0),
        }
    if command == "get_clip_automation":
        if (params["track_index"], params["clip_index"]) not in s["clips"]:
            raise RuntimeError("EMPTY_CLIP_SLOT")
        return {
            "track_index": params["track_index"], "clip_index": params["clip_index"],
            "parameter_name": params["parameter_name"], "has_envelope": False, "samples": [],
        }

def _handle_transport(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the tempo, song time, loop and track property writes."""
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
    if command == "set_track_property":
        idx = params["track_index"]
        for track in s["tracks"]:
            if track["index"] == idx:
                track[params["property"]] = params["value"]
        return {"property": params["property"], "value": params["value"]}

def _handle_playback(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the playback, batch and scene fire commands."""
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
        scene_index = params["scene_index"]
        s["is_playing"] = any(slot == scene_index for _, slot in s["clips"])
        return {"scene_index": params["scene_index"], "fired": True}

def _handle_cues(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the cue point read and write commands."""
    if command == "create_cue_point":
        song_length = float(s.get("song_length", 64.0))
        cue_time = float(params["time"])
        if cue_time > song_length + 1e-6:
            raise RuntimeError(
                f"Cannot set the Songtime behind the Songlength: "
                f"time={cue_time} song_length={song_length}")
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
                    f"time={t} song_length={song_length}")
            s["locators"].append({"name": item["name"], "time": t})
        return {"created": len(params["items"])}

def _handle_clip_writes(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the session clip create, note and delete commands."""
    if command == "create_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"][(track, slot)] = {
            "name": "", "is_audio_clip": False, "is_midi_clip": True, "has_clip": True,
            "length": params.get("length_beats", 4.0), "notes": [],
        }
        return {"track_index": track, "clip_index": slot}
    if command == "add_notes_to_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault((track, slot), {
            "name": "", "is_audio_clip": False, "is_midi_clip": True,
            "has_clip": True, "length": 4.0, "notes": []})
        s["clips"][(track, slot)]["notes"] = list(params["notes"])
        return {"added": len(params["notes"])}
    if command == "clear_clip_notes":
        track, slot = params["track_index"], params["clip_index"]
        if (track, slot) in s["clips"]:
            s["clips"][(track, slot)]["notes"] = []
        return {"cleared": True}
    if command == "set_clip_properties":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].setdefault((track, slot), {
            "name": "", "is_audio_clip": False, "is_midi_clip": True,
            "has_clip": True, "length": 4.0, "notes": []})
        if "name" in params:
            s["clips"][(track, slot)]["name"] = params["name"]
        return {"name": params.get("name", "")}
    if command == "delete_clip":
        track, slot = params["track_index"], params["clip_index"]
        s["clips"].pop((track, slot), None)
        return {"deleted": True}

def _handle_automation(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the clip automation writes and the clip target diagnosis."""
    if command == "create_clip_automation":
        return {"points_written": len(params["automation_points"])}
    if command == "create_clip_automation_curve":
        return {
            "parameter_name": params["parameter_name"], "shape": params.get("shape", "linear"),
            "points_written": len(params["control_points"]),
            "control_points": len(params["control_points"]),
        }
    if command == "add_notes_pattern":
        added = len(params["cell"]) * int(params["repeats"])
        return {"added": added, "note_ids": list(range(added)), "repeats": int(params["repeats"])}
    if command == "diagnose_clip_targets":
        tracks = []
        session_total = 0
        for track in s["tracks"]:
            session = [
                {
                    "id": f"track:{track['index']}/clipslot:{slot}/clip", "scope": "session",
                    "track_index": track["index"], "clip_index": slot,
                    "name": clip.get("name", ""), "is_midi_clip": clip.get("is_midi_clip", False),
                    "color": clip.get("color", 0), "color_index": clip.get("color_index", 0),
                    "colorable": True,
                }
                for (t_idx, slot), clip in sorted(s["clips"].items())
                if t_idx == track["index"]
            ]
            session_total += len(session)
            tracks.append({
                "track_index": track["index"], "track_id": track["id"],
                "name": track["name"], "type": track["type"],
                "session_clips": session, "arrangement_clips": [],
                # The disposable Set has no Arrangement clips; the lane is
                # still reported as supported so the runner exercises the
                # "supported and empty" branch.
                "arrangement_supported": True,
            })
        return {
            "tracks": tracks, "session_clip_count": session_total,
            "arrangement_clip_count": 0, "inaccessible": [],
        }

def _handle_arrangement(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the arrangement clip move, copy and delete commands."""
    if command == "set_arrangement_clip_properties":
        idx, position = params["track_index"], params["clip_index"]
        lane = sorted(
            s.setdefault("arrangement", {}).get(idx, []), key=lambda entry: entry["start_time"]
        )
        if position >= len(lane):
            raise RuntimeError("INVALID_PARAMS: arrangement clip %s does not exist" % position)
        if "name" in params:
            lane[position]["name"] = params["name"]
        s["arrangement"][idx] = lane
        return {"updated": True, "clip": {"clip_index": position}}
    if command == "duplicate_session_clip_to_arrangement":
        idx, slot = params["track_index"], params["clip_index"]
        source = s["clips"].get((idx, slot))
        if source is None:
            raise RuntimeError(f"BAD_INPUT: session slot {slot} is empty")
        lane = s.setdefault("arrangement", {}).setdefault(idx, [])
        lane.append({
            "name": source.get("name", ""), "start_time": float(params["time"]),
            "length": float(source.get("length_beats", 4.0)),
        })
        return {"placed": True, "clip_count": len(lane)}
    if command == "move_arrangement_clip":
        idx, position = params["track_index"], params["clip_index"]
        lane = sorted(
            s.setdefault("arrangement", {}).get(idx, []), key=lambda entry: entry["start_time"]
        )
        if position >= len(lane):
            raise RuntimeError(f"INVALID_PARAMS: arrangement clip {position} does not exist")
        lane[position]["start_time"] = float(params["time"])
        s["arrangement"][idx] = lane
        return {"moved": True, "clip_count": len(lane)}
    if command == "delete_arrangement_clip":
        idx, position = params["track_index"], params["clip_index"]
        lane = sorted(
            s.setdefault("arrangement", {}).get(idx, []), key=lambda entry: entry["start_time"]
        )
        if position >= len(lane):
            raise RuntimeError(f"INVALID_PARAMS: arrangement clip {position} does not exist")
        lane.pop(position)
        s["arrangement"][idx] = lane
        return {"deleted": True, "clip_count": len(lane)}

def _handle_arrangement_reads(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the arrangement clip list and the parameter value read."""
    if command == "get_arrangement_clips":
        idx = params["track_index"]
        lane = sorted(
            s.setdefault("arrangement", {}).get(idx, []), key=lambda entry: entry["start_time"]
        )
        clips = [
            {
                "id": f"track:{idx}/arrangementclip:{position}", "scope": "arrangement",
                "track_index": idx, "clip_index": position, "name": entry["name"],
                "start_time": entry["start_time"],
                "end_time": entry["start_time"] + entry["length"],
                "length_beats": entry["length"], "is_midi_clip": True, "muted": False,
                "looping": False, "loop_start": 0.0, "loop_end": entry["length"],
                "color_index": None,
            }
            for position, entry in enumerate(lane)
        ]
        return {"track_index": idx, "clip_count": len(clips), "clips": clips}
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

def _handle_colors(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the track and clip colour write commands."""
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
            "clip_id": clip_id, "scope": "session",
            "track_index": key[0], "clip_index": key[1], "property": provided[0],
            "color": clip.get("color", 0), "color_index": clip.get("color_index", 0),
            "resolved": {
                "kind": "clip", "track_index": key[0], "clip_index": key[1],
                "scope": "session", "clip_id": clip_id},
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
            "track_id": f"track:{idx}", "track_index": idx, "property": attribute,
            "color": target.get("color", 0), "color_index": target.get("color_index", 0),
            "resolved": {"kind": "track", "track_index": idx, "track_name": target["name"]},
        }

def _handle_device_chains(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the device chain read command."""
    if command == "get_device_chains":
        track = next((item for item in s["tracks"] if item["index"] == params["track_index"]), None)
        devices = track.get("devices", []) if track is not None else []
        device_index = params["device_index"]
        if device_index < 0 or device_index >= len(devices):
            raise RuntimeError("BAD_DEVICE_INDEX")
        if devices[device_index].get("class_name") != "InstrumentGroupDevice":
            raise RuntimeError("WRONG_TYPE: device does not expose chains")
        return {
            "track_index": params["track_index"], "device_index": params["device_index"],
            "device_name": "Instrument Rack", "chain_count": 1,
            "chains": [
                {
                    "id": "track:%s/device:%s/chain:0"
                    % (params["track_index"], params["device_index"]),
                    "chain_index": 0, "name": "Chain", "devices": [],
                    "volume": 0.85, "volume_min": 0.0, "volume_max": 1.0,
                    "panning": 0.0, "muted": False, "soloed": False,
                }
            ],
        }

def _handle_devices(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the device list, chain report and instrument read commands."""
    if command == "get_device_list":
        track = params["track_index"]
        for t in s["tracks"]:
            if t["index"] == track:
                return typed_devices(t.get("devices", []))
        return []
    if command == "get_midi_chain_report":
        return {"track_index": params["track_index"], "rewrites_input": False, "devices": []}
    if command == "describe_instrument":
        return {
            "track_index": params["track_index"], "has_instrument": True, "device_index": 0,
            "name": "Instrument Rack", "class_name": "InstrumentGroupDevice",
            "is_plugin": False, "configured_parameter_count": 2, "parameter_count": 2,
            "parameters": [], "setup_requests": [],
        }

def _handle_live_find(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer the device and clip find commands."""
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

def _handle_device_params(command: str, s: dict[str, Any], params: dict[str, Any]) -> Any:
    """Answer ``list_device_params`` with the nested parameter list."""
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
                    {"name": entry["name"], "value": entry.get("value", 0.0),
                     "min": 0.0, "max": 1.0}
                ]
            else:
                nested = []
            entries.append({
                "device_id": f"{track_id}/device:{entry_index}",
                "device_name": entry.get("device_name", f"Device of {track_id}"),
                "parameters": nested,
            })
        return entries

def _strict_tcp_dispatch(bridge: StrictFakeBridge, command: str, params: dict[str, Any]) -> Any:
    """Answer one TCP command against the fake bridge.

    The handlers of the sibling module are reached through the module
    object, imported here at call time, so that the two modules stay free
    of an import cycle.
    """
    from . import _strict_fake

    _strict_fake._validate_tcp(command, params)
    s = bridge.state
    if command not in _strict_fake._READ_ONLY_TCP_COMMANDS and command != "save_set":
        s.update({"is_dirty": True, "can_undo": True})
    if command == "save_set":
        if bridge.save_set_response is not None:
            return dict(bridge.save_set_response)
        s.update({"is_dirty": False})
        return {"saved": True, "api_available": True, "result": None}
    for handler in (
        _handle_session, _handle_project, _handle_clips, _handle_transport,
        _handle_playback, _handle_cues, _handle_clip_writes, _handle_automation,
        _handle_arrangement, _handle_arrangement_reads, _handle_colors,
        _handle_device_chains, _handle_devices, _handle_live_find,
        _handle_device_params, _strict_fake._handle_tracks,
        _strict_fake._handle_search, _strict_fake._handle_track_writes,
        _strict_fake._handle_live_fade, _strict_fake._handle_parameter_value,
    ):
        result = handler(command, s, params)
        if result is not None:
            return result
    if command in UNSUPPORTED_CAPABILITIES:
        return _strict_fake._handle_unsupported_capability(command, s, params)
    raise RuntimeError(f"UNKNOWN_TCP_COMMAND: {command}")
