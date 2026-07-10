from __future__ import annotations

import math
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Protocol


class AcceptanceClient(Protocol):
    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any: ...


class AcceptanceSafetyError(RuntimeError):
    """Raised before mutation when the disposable Set cannot be proven safe."""


def _test_tempo(original: float, offset: float) -> float:
    candidate = original + offset
    if candidate <= 999.0:
        return candidate
    return original - offset


def run_live_acceptance(
    client: AcceptanceClient,
    *,
    confirm_project_name: str,
    track_index: int,
    clip_index: int,
    fire_clip: bool = False,
) -> dict[str, Any]:
    """Exercise the real bridge after exact disposable-project confirmation."""

    def call(command: str, params: Mapping[str, Any] | None = None) -> Any:
        return client.call(command, params or {}, timeout=None)

    metadata = call("get_project_metadata")
    actual_name = str(metadata.get("song_name", ""))
    if actual_name != confirm_project_name:
        raise AcceptanceSafetyError(
            f"Loaded project {actual_name!r} does not match confirmation "
            f"{confirm_project_name!r}; no mutations were sent."
        )

    tracks = call("get_track_list")
    track = next((item for item in tracks if item.get("index") == track_index), None)
    if track is None or track.get("type") != "midi":
        raise AcceptanceSafetyError(
            f"Track {track_index} is missing or is not MIDI; no mutations were sent."
        )
    slots = call("get_clip_summary", {"track_index": track_index})
    slot = next((item for item in slots if item.get("index") == clip_index), None)
    if slot is None or bool(slot.get("has_clip")):
        raise AcceptanceSafetyError(
            f"Clip slot {track_index}:{clip_index} is missing or occupied; no mutations were sent."
        )

    original_session = call("get_session_info")
    original_loop = call("get_loop_settings")
    original_locators = call("get_locators")
    original_tempo = float(original_session["tempo"])
    original_time = float(original_session["current_song_time"])
    cue_time = max(
        32.0,
        math.ceil(max((float(item["time"]) for item in original_locators), default=0.0) + 8.0),
    )
    tempo_one = _test_tempo(original_tempo, 1.0)
    tempo_two = _test_tempo(original_tempo, 2.0)
    cue_name = "ABLETON_MCP_ACCEPTANCE"
    cue_created = False
    result: dict[str, Any] = {
        "status": "running",
        "project": actual_name,
        "track_index": track_index,
        "clip_index": clip_index,
    }
    try:
        call("set_tempo", {"tempo": tempo_one})
        call("set_current_song_time", {"time": 8.0})
        call("set_loop_start", {"start_beat": 4.0})
        call("set_loop_length", {"length_beats": 8.0})
        call("set_loop", {"enabled": True})

        call("create_cue_point", {"name": cue_name, "time": cue_time})
        cue_created = True
        locators = call("get_locators")
        if not any(
            item.get("name") == cue_name
            and abs(float(item.get("time", -1.0)) - cue_time) < 0.01
            for item in locators
        ):
            raise AssertionError("Cue creation acknowledged but not observed at the target time")
        call("delete_cue_point", {"time": cue_time})
        cue_created = False
        if any(
            abs(float(item.get("time", -1.0)) - cue_time) < 0.01
            for item in call("get_locators")
        ):
            raise AssertionError("Cue deletion was acknowledged but the cue still exists")

        call(
            "create_clip",
            {"track_index": track_index, "clip_index": clip_index, "length_beats": 4.0},
        )
        notes = [
            {
                "pitch": pitch,
                "start_time": float(index),
                "duration": 0.75,
                "velocity": 72 + index * 4,
                "mute": False,
            }
            for index, pitch in enumerate((60, 64, 67, 72))
        ]
        added = call(
            "add_notes_to_clip",
            {"track_index": track_index, "clip_index": clip_index, "notes": notes},
        )
        observed_notes = call(
            "get_clip_notes", {"track_index": track_index, "clip_index": clip_index}
        )
        if int(added["added"]) != 4 or len(observed_notes) != 4:
            raise AssertionError("MIDI notes were not observed after add_notes_to_clip")

        if fire_clip:
            call("fire_clip", {"track_index": track_index, "clip_index": clip_index})
            call("stop_playback")

        batch = call(
            "run_batch",
            {
                "commands": [
                    {"type": "set_tempo", "params": {"tempo": tempo_two}},
                    {"type": "set_loop", "params": {"enabled": True}},
                    {
                        "type": "create_clip",
                        "params": {
                            "track_index": track_index,
                            "clip_index": clip_index,
                            "length_beats": 4.0,
                        },
                    },
                    {"type": "set_tempo", "params": {"tempo": tempo_one}},
                ]
            },
        )
        if (
            int(batch["completed"]) != 2
            or int(batch["aborted_at"]) != 2
            or bool(batch["rolled_back"])
        ):
            raise AssertionError(f"Unexpected partial-batch result: {batch}")

        result.update(
            {
                "status": "ok",
                "notes_added": len(observed_notes),
                "cue_round_trip": True,
                "batch": batch,
            }
        )
        return result
    finally:
        if cue_created:
            with suppress(Exception):
                call("delete_cue_point", {"time": cue_time})
        with suppress(Exception):
            call("stop_playback")
        call("set_loop", {"enabled": bool(original_loop["loop"])})
        call("set_loop_start", {"start_beat": float(original_loop["loop_start"])})
        call("set_loop_length", {"length_beats": float(original_loop["loop_length"])})
        call("set_tempo", {"tempo": original_tempo})
        call("set_current_song_time", {"time": original_time})
