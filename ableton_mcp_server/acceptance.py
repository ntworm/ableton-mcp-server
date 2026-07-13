from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import Any, Protocol

from .certification import CertificationReport, Verification


class AcceptanceClient(Protocol):
    def call(
        self,
        command_type: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any: ...

    async def call_ws(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> Any: ...


class AcceptanceSafetyError(RuntimeError):
    """Raised before mutation when the disposable Set cannot be proven safe."""


def _test_tempo(original: float, offset: float) -> float:
    candidate = original + offset
    if candidate <= 999.0:
        return candidate
    return original - offset


def _acceptance_cue_time(locators: list[Mapping[str, Any]]) -> float:
    """Choose a free coarse-grid beat for a disposable cue round trip."""

    candidate = 256.0
    while any(
        abs(float(item.get("time", -1.0)) - candidate) < 0.01 for item in locators
    ):
        candidate += 256.0
    return candidate


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
    cue_time = _acceptance_cue_time(original_locators)
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


# Slice 1 Task 9: baseline probe map. The flattened names must equal the
# 65-name ``PUBLIC_TOOL_NAMES`` set, so each catalogued tool has a home in
# exactly one probe group. ``build_extension`` falls back to
# ``environment_unavailable`` when Node is absent; ``quit_ableton`` is
# ``environment_unavailable`` until the dedicated manual profile is added.
BASELINE_PROBE_GROUPS: dict[str, tuple[str, ...]] = {
    "offline": (
        "get_ableton_logs",
        "diff_snapshots_tool",
        "scaffold_extension",
        "build_extension",
        "analyze_audio",
        "find_frequency_masking",
        "analyze_mix",
        "extract_single_cycle",
    ),
    "composed": ("get_bridge_status", "get_session_overview"),
    "tcp_reads": (
        "get_session_info",
        "get_track_list",
        "get_track_state",
        "get_locators",
        "take_snapshot",
        "get_control_surfaces",
        "get_scenes",
        "get_scene_state",
        "get_project_metadata",
        "get_loop_settings",
        "get_selected_context",
        "get_clip_summary",
        "get_clip_notes",
        "get_clip_info",
        "get_device_list",
        "get_parameter_value",
        "get_routing",
        "get_browser_categories",
        "search_browser",
        "get_song_length",
        "live_find_track",
        "list_device_params",
        "get_composition_structure",
        "diagnose_midi_clip",
        "lifecycle_status",
    ),
    "websocket_reads": ("get_warp_state",),
    "mutations": (
        "create_cue_point",
        "bulk_create_cue_points",
        "delete_cue_point",
        "set_current_song_time",
        "set_tempo",
        "start_playback",
        "stop_playback",
        "set_loop",
        "set_loop_start",
        "set_loop_length",
        "run_batch",
        "add_notes_to_clip",
        "fire_clip",
        "create_clip",
        "delete_clip",
        "clear_clip_notes",
        "fire_scene",
        "set_track_property",
        "set_clip_properties",
        "create_clip_automation",
        "create_midi_track",
        "create_audio_track",
        "rename_track",
        "set_parameter_value",
        "save_set",
        "quit_ableton",
        "live_fade",
        "set_warp_state",
        "load_device_to_track",
    ),
}


def _baseline_tool_names() -> tuple[str, ...]:
    """Import lazily to avoid a circular import at module load."""
    from .server import PUBLIC_TOOL_NAMES

    return tuple(PUBLIC_TOOL_NAMES)


def _baseline_probe_names() -> tuple[str, ...]:
    names: list[str] = []
    for group in BASELINE_PROBE_GROUPS.values():
        names.extend(group)
    return tuple(names)


async def _record_call(
    report: CertificationReport,
    tool: str,
    action: Callable[[], Any | Awaitable[Any]],
    *,
    passed: str = "live_passed",
) -> Any:
    """Invoke ``action``, record a Verification row, and return the value.

    Failures map ``CAPABILITY_UNAVAILABLE`` to ``host_unavailable``; everything
    else is recorded as ``failed``.
    """
    try:
        value = action()
        if inspect.isawaitable(value):
            value = await value
    except Exception as error:  # noqa: BLE001 — recording layer swallows all
        from .errors import BridgeError

        if isinstance(error, BridgeError) and error.code == "CAPABILITY_UNAVAILABLE":
            report.record(
                Verification(tool, "host_unavailable", f"{error.code}: {error}")
            )
        else:
            report.record(
                Verification(tool, "failed", f"{type(error).__name__}: {error}")
            )
        return None
    report.record(Verification(tool, passed, "call and readback completed"))
    return value


def build_baseline_report(
    profiles: tuple[str, ...] | None = None,
) -> CertificationReport:
    """Return a report covering exactly the catalogued tools for the given
    profiles, or the full baseline surface when ``profiles`` is empty.

    Tools that do not appear in any selected group are pre-recorded as
    ``environment_unavailable`` with the rationale so callers can finish()
    the report without juggling partial coverage.
    """
    selected = profiles or tuple(BASELINE_PROBE_GROUPS)
    seen: set[str] = set()
    for profile in selected:
        if profile not in BASELINE_PROBE_GROUPS:
            raise ValueError(f"unknown acceptance profile: {profile}")
        seen.update(BASELINE_PROBE_GROUPS[profile])
    catalog_names = _baseline_tool_names()
    extras = seen.difference(catalog_names)
    if extras:
        raise ValueError(
            f"baseline groups reference uncatalogued tools: {sorted(extras)}"
        )
    report = CertificationReport(tool_names=catalog_names)
    missing = set(catalog_names).difference(seen)
    for tool in missing:
        report.record(
            Verification(
                tool,
                "environment_unavailable",
                f"not covered by selected profiles: {selected}",
            )
        )
    return report


def assert_baseline_probe_coverage() -> None:
    """Invoked from tests and CLI: flattened probe names must equal 65."""
    flat = set(_baseline_probe_names())
    catalog_names = set(_baseline_tool_names())
    assert flat == catalog_names, (
        f"baseline probe mismatch: "
        f"missing={catalog_names - flat}, extra={flat - catalog_names}"
    )
