"""The command groups of the mock Remote Script.

The mock answers the read and the mutation commands with small handlers, one
per command group, so that no single handler carries the whole surface.
``MockRemoteScript`` mixes these handlers in and provides the envelope helpers
(``ok``, ``error``), the snapshot lookups (``_track``, ``_slot``, ``_missing``)
and the dispatcher (``handle``) the groups call.
"""

from __future__ import annotations

import copy
from typing import Any


class MockCommandHandlers:
    """The command groups of the mock Remote Script."""

    def _read_session(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the session read commands."""
        if command == "take_snapshot":
            return self.ok(copy.deepcopy(self.snapshot))
        if command == "get_session_info":
            return self.ok(
                {
                    key: self.snapshot[key]
                    for key in (
                        "tempo",
                        "signature_numerator",
                        "signature_denominator",
                        "is_playing",
                        "current_song_time",
                    )
                }
            )
        if command == "get_song_length":
            return self.ok({"song_length": self.snapshot["song_length"]})
        return None

    def _read_tracks(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the track, the device and the clip read commands."""
        if command == "get_track_state":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track)) if track else self._missing("track")
        if command == "get_device_list":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track["devices"])) if track else self._missing("track")
        if command == "get_clip_summary":
            track = self._track(params.get("track_index"))
            return self.ok(copy.deepcopy(track["clip_slots"])) if track else self._missing("track")
        if command == "get_clip_notes":
            slot = self._slot(params)
            return self.ok(copy.deepcopy(slot.get("notes", []))) if slot else self._missing("clip")
        return None

    def _read_devices(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the device parameter read command."""
        if command == "get_parameter_value":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            device_index = params.get("device_index")
            if not isinstance(device_index, int) or device_index >= len(track["devices"]):
                return self._missing("device")
            name = params.get("parameter_name")
            parameter = next(
                (
                    item
                    for item in track["devices"][device_index]["parameters"]
                    if item["name"] == name
                ),
                None,
            )
            return self.ok(copy.deepcopy(parameter)) if parameter else self._missing("parameter")
        return None

    def _read_diagnostics(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the clip target diagnostic command."""
        if command == "diagnose_clip_targets":
            requested = params.get("track_index")
            targets = (
                [t for t in self.snapshot["tracks"] if t["index"] == requested]
                if isinstance(requested, int)
                else self.snapshot["tracks"]
            )
            tracks = []
            session_total = 0
            for track in targets:
                session = [
                    {
                        "id": slot["clip_id"],
                        "scope": "session",
                        "track_index": track["index"],
                        "clip_index": slot["index"],
                        "name": slot.get("clip_name", ""),
                        "is_midi_clip": True,
                        "color": slot.get("color", 0),
                        "color_index": slot.get("color_index", 0),
                        "colorable": True,
                    }
                    for slot in track["clip_slots"]
                    if slot.get("has_clip")
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
                        "arrangement_supported": False,
                    }
                )
            return self.ok(
                {
                    "tracks": tracks,
                    "session_clip_count": session_total,
                    "arrangement_clip_count": 0,
                    "inaccessible": [
                        {
                            "track_index": track["track_index"],
                            "scope": "arrangement",
                            "reason": "The mock Remote Script exposes no Arrangement lane.",
                        }
                        for track in tracks
                    ],
                }
            )
        return None

    def _read_project(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the Set, the browser and the routing read commands."""
        if command == "get_control_surfaces":
            return self.ok(copy.deepcopy(self.snapshot["control_surfaces"]))
        if command == "get_browser_categories":
            return self.ok(
                [
                    "Sounds",
                    "Drums",
                    "Instruments",
                    "Audio Effects",
                    "MIDI Effects",
                    "Plugins",
                    "Samples",
                ]
            )
        if command == "get_routing":
            return self.ok(
                {
                    "input_routing": "Ext. In",
                    "input_sub_routing": "1/2",
                    "output_routing": "Master",
                    "output_sub_routing": "1/2",
                }
            )
        if command == "get_locators":
            return self.ok(copy.deepcopy(self.snapshot["locators"]))
        if command == "get_scenes":
            return self.ok(copy.deepcopy(self.snapshot["scenes"]))
        if command == "get_project_metadata":
            return self.ok(copy.deepcopy(self.snapshot["project_metadata"]))
        if command == "get_loop_settings":
            return self.ok(copy.deepcopy(self.snapshot["loop_settings"]))
        if command == "get_selected_context":
            return self.ok(copy.deepcopy(self.snapshot["selected_context"]))
        return None

    def _read_queries(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the scene state and the track and device lookup commands."""
        if command == "get_scene_state":
            index = params.get("scene_index")
            scenes = self.snapshot["scenes"]
            return (
                self.ok(copy.deepcopy(scenes[index]))
                if isinstance(index, int) and index < len(scenes)
                else self._missing("scene")
            )
        if command == "live_find_track":
            query = str(params.get("query", "")).casefold()
            tracks = [
                {key: track[key] for key in ("id", "index", "name", "type")}
                for track in self.snapshot["tracks"]
                if query in track["name"].casefold()
            ]
            return self.ok(tracks)
        if command == "list_device_params":
            track = next(
                (
                    track
                    for track in self.snapshot["tracks"]
                    if track["id"] == params.get("track_id")
                ),
                None,
            )
            if not track:
                return self.error("STALE_REFERENCE", "Track path no longer resolves")
            return self.ok(
                [
                    {
                        "device_id": device["id"],
                        "device_name": device["name"],
                        "parameters": copy.deepcopy(device["parameters"]),
                    }
                    for device in track["devices"]
                ]
            )
        return None

    def _mutate_transport(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the tempo, the transport and the loop mutation commands."""
        if command == "set_tempo":
            self.snapshot["tempo"] = float(params["tempo"])
            return self.ok(
                {
                    "tempo": self.snapshot["tempo"],
                    "resolved": {"kind": "tempo", "tempo": self.snapshot["tempo"]},
                }
            )
        if command == "set_current_song_time":
            self.snapshot["current_song_time"] = float(params["time"])
            return self.ok({"current_song_time": self.snapshot["current_song_time"]})
        if command in ("start_playback", "stop_playback"):
            self.snapshot["is_playing"] = command == "start_playback"
            return self.ok({"is_playing": self.snapshot["is_playing"]})
        if command == "set_loop":
            self.snapshot["loop"] = bool(params["enabled"])
            self.snapshot["loop_settings"]["loop"] = self.snapshot["loop"]
            return self.ok({"loop": self.snapshot["loop"]})
        if command in ("set_loop_start", "set_loop_length"):
            key = "loop_start" if command.endswith("start") else "loop_length"
            param = "start_beat" if key == "loop_start" else "length_beats"
            self.snapshot[key] = float(params[param])
            self.snapshot["loop_settings"][key] = self.snapshot[key]
            return self.ok({key: self.snapshot[key]})
        return None

    def _mutate_device(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the device parameter mutation command."""
        if command == "set_parameter_value":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            device_index = params.get("device_index")
            if not isinstance(device_index, int) or device_index >= len(track["devices"]):
                return self._missing("device")
            device = track["devices"][device_index]
            parameter_name = params.get("parameter_name")
            parameter = next(
                (item for item in device["parameters"] if item["name"] == parameter_name),
                None,
            )
            if parameter is None:
                return self._missing("parameter")
            requested = float(params["value"])
            parameter["value"] = requested
            return self.ok(
                {
                    "target": requested,
                    "value": parameter["value"],
                    "is_quantized": parameter["is_quantized"],
                    "resolved": {
                        "kind": "device",
                        "track_index": track["index"],
                        "device_index": device_index,
                        "parameter_name": parameter_name,
                        "track_name": track["name"],
                        "device_name": device["name"],
                    },
                }
            )
        return None

    def _mutate_clip_color(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the clip colour mutation command."""
        if command == "set_clip_color":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            if params.get("scope", "session") != "session":
                return self.error(
                    "CAPABILITY_UNAVAILABLE",
                    "The mock Set has no Arrangement clips.",
                )
            slot = self._slot(params)
            if slot is None:
                return self._missing("clip")
            provided = [name for name in ("color_index", "color") if name in params]
            if len(provided) != 1:
                return self.error(
                    "INVALID_PARAMS",
                    "Provide exactly one of color_index or color.",
                )
            slot[provided[0]] = int(params[provided[0]])
            return self.ok(
                {
                    "clip_id": slot.get("clip_id"),
                    "scope": "session",
                    "track_index": track["index"],
                    "clip_index": params["clip_index"],
                    "property": provided[0],
                    "color": slot.get("color", 0),
                    "color_index": slot.get("color_index", 0),
                    "resolved": {
                        "kind": "clip",
                        "track_index": track["index"],
                        "clip_index": params["clip_index"],
                        "scope": "session",
                        "clip_id": slot.get("clip_id"),
                    },
                }
            )
        return None

    def _mutate_track_color(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the track colour mutation command."""
        if command == "set_track_color":
            track = self._track(params.get("track_index"))
            if not track:
                return self._missing("track")
            provided = [name for name in ("color_index", "color") if name in params]
            if len(provided) != 1:
                return self.error(
                    "INVALID_PARAMS",
                    "Provide exactly one of color_index or color.",
                )
            track[provided[0]] = int(params[provided[0]])
            return self.ok(
                {
                    "track_id": track["id"],
                    "track_index": track["index"],
                    "property": provided[0],
                    "color": track.get("color", 0),
                    "color_index": track.get("color_index", 0),
                    "resolved": {
                        "kind": "track",
                        "track_index": track["index"],
                        "track_name": track["name"],
                    },
                }
            )
        return None

    def _mutate_cue_point(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the cue point creation and deletion commands."""
        if command == "create_cue_point":
            target = float(params["time"])
            cue = next(
                (item for item in self.snapshot["locators"] if abs(item["time"] - target) < 0.01),
                None,
            )
            action = "renamed" if cue else "created"
            if cue is None:
                cue = {"name": str(params["name"]), "time": target}
                self.snapshot["locators"].append(cue)
            else:
                cue["name"] = str(params["name"])
            return self.ok({**cue, "action": action})
        if command == "delete_cue_point":
            target = float(params["time"])
            cue = next(
                (item for item in self.snapshot["locators"] if abs(item["time"] - target) < 0.01),
                None,
            )
            if cue:
                self.snapshot["locators"].remove(cue)
            return self.ok({"deleted": cue is not None, "time": target})
        return None

    def _mutate_cue_points(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the bulk cue point creation command."""
        if command == "bulk_create_cue_points":
            results = []
            for index, item in enumerate(params["items"]):
                response = self._handle_mutation("create_cue_point", item)
                assert response is not None
                results.append({"index": index, "status": "ok", "result": response["result"]})
            return self.ok({"results": results})
        return None

    def _mutate_clips(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the clip firing and the note mutation commands."""
        if command == "fire_clip":
            slot = self._slot(params)
            if not slot:
                return self._missing("clip")
            slot["is_playing"] = True
            return self.ok({"fired": True, "clip_id": slot["clip_id"]})
        if command == "add_notes_to_clip":
            slot = self._slot(params)
            if not slot:
                return self._missing("clip")
            slot.setdefault("notes", []).extend(copy.deepcopy(params["notes"]))
            return self.ok({"added": len(params["notes"]), "clip_id": slot["clip_id"]})
        return None

    def _mutate_clip_creation(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the clip creation command."""
        if command == "create_clip":
            track = self._track(params.get("track_index"))
            clip_index = params.get("clip_index")
            if (
                not track
                or not isinstance(clip_index, int)
                or clip_index >= len(track["clip_slots"])
            ):
                return self._missing("clip slot")
            slot = track["clip_slots"][clip_index]
            if slot["has_clip"]:
                return self.error("BAD_INPUT", "Clip slot is not empty")
            slot.update(
                {
                    "clip_id": f"track:{track['index']}/clipslot:{clip_index}/clip",
                    "has_clip": True,
                    "length_beats": float(params["length_beats"]),
                    "notes": [],
                }
            )
            return self.ok(
                {
                    "created": True,
                    "clip_id": slot["clip_id"],
                    "length_beats": slot["length_beats"],
                    "resolved": {
                        "kind": "clip",
                        "track_index": track["index"],
                        "clip_index": clip_index,
                        "track_name": track["name"],
                        "clip_id": slot["clip_id"],
                    },
                }
            )
        return None

    def _mutate_batch(self, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Answer the batch mutation command."""
        if command == "run_batch":
            results = []
            completed = 0
            aborted_at = None
            for index, subcommand in enumerate(params["commands"]):
                response = self.handle(subcommand["type"], subcommand.get("params", {}))
                if response["status"] == "error":
                    results.append({"index": index, **response})
                    aborted_at = index
                    break
                results.append({"index": index, "status": "ok", "result": response["result"]})
                completed += 1
            return self.ok(
                {
                    "results": results,
                    "completed": completed,
                    "aborted_at": aborted_at,
                    "rolled_back": False,
                }
            )
        return None
