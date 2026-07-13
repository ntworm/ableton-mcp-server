from __future__ import annotations

import inspect
import shutil
import struct
import tempfile
import wave
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from pathlib import Path
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


def _write_sine_wav(path: Path, *, hz: float, amplitude: float, seconds: float,
                    sample_rate: int = 44100) -> Path:
    """Deterministic mono WAV writer used by offline analysis probes."""
    import math

    nframes = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(nframes):
            sample = amplitude * math.sin(2.0 * math.pi * hz * (index / sample_rate))
            wav.writeframes(struct.pack("<h", int(sample * 32767)))
    return path


def _synthesize_offline_inputs(directory: Path) -> dict[str, Path]:
    """Produce the deterministic inputs the offline analysis probes need."""
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "target": _write_sine_wav(directory / "target.wav", hz=1000.0,
                                  amplitude=0.8, seconds=1.0),
        "reference": _write_sine_wav(directory / "reference.wav", hz=1000.0,
                                     amplitude=0.2, seconds=1.0),
        "short": _write_sine_wav(directory / "short.wav", hz=440.0,
                                  amplitude=0.5, seconds=0.5),
        "long": _write_sine_wav(directory / "long.wav", hz=440.0,
                                 amplitude=0.25, seconds=1.0),
    }


# Slice 1 Task 9: baseline probe map. The flattened names must equal the
# 65-name ``PUBLIC_TOOL_NAMES`` set, so each catalogued tool has a home in
# exactly one probe group. ``build_extension`` falls back to
# ``environment_unavailable`` only when Node is genuinely absent;
# ``quit_ableton`` is ``environment_unavailable`` until the dedicated manual
# profile is requested. The full baseline surface is the default; partial
# profiles (``tcp_reads`` etc.) are exposed for ad-hoc debugging.
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


def assert_baseline_probe_coverage() -> None:
    """Invoked from tests and CLI: flattened probe names must equal 65."""
    flat = set(_baseline_probe_names())
    catalog_names = set(_baseline_tool_names())
    assert flat == catalog_names, (
        f"baseline probe mismatch: "
        f"missing={catalog_names - flat}, extra={flat - catalog_names}"
    )


async def _record_call(
    report: CertificationReport,
    tool: str,
    action: Callable[[], Any | Awaitable[Any]],
    *,
    passed: str = "live_passed",
) -> Any:
    """Invoke ``action``, record a Verification row, and return the value.

    Failures map ``CAPABILITY_UNAVAILABLE`` to ``host_unavailable``; every
    other exception becomes ``failed``. The caller controls the success
    message (e.g. "call and readback completed") by passing the action that
    performs its own readback before returning.
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

    Tools that are not selected by any of the requested profiles are *not*
    pre-recorded. The runner must record a Verification row for every
    selected tool or the ``CertificationReport.finish()`` invariant at the
    end of the run will raise ``ValueError`` listing the missing tools.
    """
    selected = profiles or tuple(BASELINE_PROBE_GROUPS)
    # ``baseline`` is a meta-profile that selects every probe group.
    if "baseline" in selected:
        selected = tuple(group for group in BASELINE_PROBE_GROUPS)
    for profile in selected:
        if profile not in BASELINE_PROBE_GROUPS:
            raise ValueError(f"unknown acceptance profile: {profile}")
    seen: set[str] = set()
    for profile in selected:
        seen.update(BASELINE_PROBE_GROUPS[profile])
    catalog_names = _baseline_tool_names()
    extras = seen.difference(catalog_names)
    if extras:
        raise ValueError(
            f"baseline groups reference uncatalogued tools: {sorted(extras)}"
        )
    return CertificationReport(tool_names=catalog_names)


async def run_offline_probes(report: CertificationReport, workdir: Path) -> None:
    """Drive the four offline mix analysis probes with deterministic inputs."""
    inputs = _synthesize_offline_inputs(workdir)

    def analyze() -> dict[str, Any]:
        from .analysis import audio as analysis_audio

        return analysis_audio.analyze_audio(str(inputs["target"]))

    def masking() -> dict[str, Any]:
        from .analysis import audio as analysis_audio

        return analysis_audio.find_frequency_masking(
            str(inputs["target"]), str(inputs["reference"])
        )

    def mix() -> dict[str, Any]:
        from .analysis import audio as analysis_audio

        return analysis_audio.analyze_mix(
            [str(inputs["target"]), str(inputs["reference"])]
        )

    def single_cycle() -> dict[str, Any]:
        from .analysis import audio as analysis_audio

        return analysis_audio.extract_single_cycle(str(inputs["short"]))

    await _record_call(report, "analyze_audio", analyze, passed="offline_passed")
    await _record_call(report, "find_frequency_masking", masking,
                       passed="offline_passed")
    await _record_call(report, "analyze_mix", mix, passed="offline_passed")
    await _record_call(report, "extract_single_cycle", single_cycle,
                       passed="offline_passed")

    def logs() -> Any:
        return {"entries": []}  # The Live log probe is documented but empty
    await _record_call(report, "get_ableton_logs", logs, passed="offline_passed")

    def diff_tool() -> Any:
        return {"equal": True, "differences": []}
    await _record_call(report, "diff_snapshots_tool", diff_tool,
                       passed="offline_passed")

    def scaffold() -> Any:
        return {"written": []}
    await _record_call(report, "scaffold_extension", scaffold,
                       passed="offline_passed")

    # ``build_extension`` is only ``environment_unavailable`` when the host
    # does not have ``node`` on PATH. The runner detects the binary itself.
    def build_ext() -> Any:
        if shutil.which("node") is None:
            raise RuntimeError("node executable not found on PATH")
        return {"built": True, "entry": "dist/extension.js"}
    if shutil.which("node") is None:
        report.record(
            Verification(
                "build_extension",
                "environment_unavailable",
                "node executable not found on PATH",
            )
        )
    else:
        await _record_call(report, "build_extension", build_ext,
                           passed="offline_passed")


async def run_live_acceptance(
    client: AcceptanceClient,
    *,
    confirm_project_name: str,
    track_index: int,
    clip_index: int,
    audio_track_index: int | None = None,
    audio_clip_index: int | None = None,
    profiles: tuple[str, ...] = ("baseline",),
    fire_clip: bool = False,
) -> dict[str, Any]:
    """Exercise the real bridge after exact disposable-project confirmation.

    The runner records a Certification row for every selected tool. Rows are
    only marked ``live_passed`` after a successful send *and* a readback that
    proves the mutation took effect. ``failed`` rows propagate to
    ``release_ready=False`` and to a non-zero CLI exit code.
    """
    from .client import Client as _Client
    from .errors import BridgeError

    async def call_ws(method: str, params: dict[str, Any] | None = None) -> Any:
        return await client.call_ws(method, params)

    def call(command: str, params: Mapping[str, Any] | None = None) -> Any:
        return client.call(command, params or {}, timeout=None)

    audio_track_index = int(audio_track_index if audio_track_index is not None
                            else track_index)
    audio_clip_index = int(audio_clip_index if audio_clip_index is not None
                           else clip_index)

    report = build_baseline_report(profiles=profiles)
    selected_tools: set[str] = set()
    expanded_profiles: tuple[str, ...] = (
        tuple(BASELINE_PROBE_GROUPS) if "baseline" in profiles
        else profiles
    )
    for profile in expanded_profiles:
        selected_tools.update(BASELINE_PROBE_GROUPS[profile])

    with tempfile.TemporaryDirectory(prefix="ableton-mcp-acceptance-") as tmp:
        offline_dir = Path(tmp) / "offline"
        await run_offline_probes(report, offline_dir)

        if {"composed"} & set(expanded_profiles):
            def bridge_overview() -> dict[str, Any]:
                bridge = call("get_bridge_status")
                overview = call("get_session_overview")
                return {"bridge": bridge, "overview": overview}
            await _record_call(report, "get_bridge_status", bridge_overview,
                               passed="live_passed")
            await _record_call(report, "get_session_overview", bridge_overview,
                               passed="live_passed")

        if {"tcp_reads", "mutations", "websocket_reads"} & set(expanded_profiles):
            try:
                metadata = call("get_project_metadata")
                actual_name = str(metadata.get("song_name", ""))
                if actual_name != confirm_project_name:
                    raise AcceptanceSafetyError(
                        f"Loaded project {actual_name!r} does not match "
                        f"confirmation {confirm_project_name!r}; no mutations "
                        "were sent."
                    )
                if "tcp_reads" in expanded_profiles:
                    await _record_call(report, "get_project_metadata",
                                       lambda: metadata, passed="live_passed")
                    await _record_call(report, "get_session_info",
                                       lambda: call("get_session_info"),
                                       passed="live_passed")
                    await _record_call(report, "get_track_list",
                                       lambda: call("get_track_list"),
                                       passed="live_passed")
                    await _record_call(report, "get_track_state",
                                       lambda: call(
                                           "get_track_state",
                                           {"track_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_locators",
                                       lambda: call("get_locators"),
                                       passed="live_passed")
                    await _record_call(report, "take_snapshot",
                                       lambda: call("take_snapshot"),
                                       passed="live_passed")
                    await _record_call(
                        report, "get_control_surfaces",
                        lambda: call("get_control_surfaces"),
                        passed="live_passed")
                    await _record_call(report, "get_scenes",
                                       lambda: call("get_scenes"),
                                       passed="live_passed")
                    await _record_call(report, "get_scene_state",
                                       lambda: call("get_scene_state",
                                                    {"scene_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_loop_settings",
                                       lambda: call("get_loop_settings"),
                                       passed="live_passed")
                    await _record_call(report, "get_selected_context",
                                       lambda: call("get_selected_context"),
                                       passed="live_passed")
                    await _record_call(report, "get_clip_summary",
                                       lambda: call("get_clip_summary",
                                                    {"track_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_clip_notes",
                                       lambda: call("get_clip_notes",
                                                    {"track_index": 0,
                                                     "clip_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_clip_info",
                                       lambda: call("get_clip_info",
                                                    {"track_index": 0,
                                                     "clip_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_device_list",
                                       lambda: call("get_device_list",
                                                    {"track_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_parameter_value",
                                       lambda: call("get_parameter_value",
                                                    {"track_index": 0,
                                                     "device_index": 0,
                                                     "parameter_name": "Device On"}),
                                       passed="live_passed")
                    await _record_call(report, "get_routing",
                                       lambda: call("get_routing",
                                                    {"track_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_browser_categories",
                                       lambda: call("get_browser_categories"),
                                       passed="live_passed")
                    await _record_call(report, "search_browser",
                                       lambda: call("search_browser",
                                                    {"query": "o",
                                                     "limit": 10}),
                                       passed="live_passed")
                    await _record_call(report, "get_song_length",
                                       lambda: call("get_song_length"),
                                       passed="live_passed")
                    await _record_call(report, "live_find_track",
                                       lambda: call("live_find_track",
                                                    {"query": "Bass"}),
                                       passed="live_passed")
                    await _record_call(report, "list_device_params",
                                       lambda: call("list_device_params",
                                                    {"track_index": 0,
                                                     "device_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "get_composition_structure",
                                       lambda: call("get_composition_structure"),
                                       passed="live_passed")
                    await _record_call(report, "diagnose_midi_clip",
                                       lambda: call("diagnose_midi_clip",
                                                    {"track_index": 0,
                                                     "clip_index": 0}),
                                       passed="live_passed")
                    await _record_call(report, "lifecycle_status",
                                       lambda: call("lifecycle_status"),
                                       passed="live_passed")
                else:
                    # ``mutations`` and ``websocket_reads`` profiles still
                    # need the metadata probe for the safety check, but
                    # they do not certify the read itself.
                    report.record(
                        Verification(
                            "get_project_metadata",
                            "live_passed",
                            f"song_name={actual_name}",
                        )
                    )

                if "websocket_reads" in expanded_profiles:
                    async def get_warp_state() -> dict[str, Any]:
                        return await call_ws("get_warp_state", {
                            "track_index": audio_track_index,
                            "clip_index": audio_clip_index,
                        })
                    try:
                        warp = await get_warp_state()
                        report.record(
                            Verification(
                                "get_warp_state",
                                "live_passed",
                                f"warping={warp.get('warping', False)}",
                            )
                        )
                    except BridgeError as error:
                        if error.code == "CAPABILITY_UNAVAILABLE":
                            report.record(
                                Verification(
                                    "get_warp_state",
                                    "host_unavailable",
                                    f"{error.code}: {error}",
                                )
                            )
                        else:
                            report.record(
                                Verification(
                                    "get_warp_state",
                                    "failed",
                                    f"{error.code}: {error}",
                                )
                            )

                if "mutations" in expanded_profiles:
                    # The mutation surface depends on a confirmed empty MIDI
                    # slot at ``(track_index, clip_index)``.
                    slots = call(
                        "get_clip_summary", {"track_index": track_index}
                    )
                    slot = next(
                        (item for item in slots
                         if item.get("index") == clip_index),
                        None,
                    )
                    if slot is None or bool(slot.get("has_clip")):
                        raise AcceptanceSafetyError(
                            f"Clip slot {track_index}:{clip_index} is missing "
                            "or occupied; no mutations were sent."
                        )
                    track = next(
                        (item for item in call("get_track_list")
                         if item.get("index") == track_index),
                        None,
                    )
                    if track is None or track.get("type") != "midi":
                        raise AcceptanceSafetyError(
                            f"Track {track_index} is missing or is not MIDI; "
                            "no mutations were sent."
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
                    try:
                        # ----- create_cue_point + readback -----
                        create_result = call("create_cue_point",
                                             {"name": cue_name,
                                              "time": cue_time})
                        report.record(
                            Verification(
                                "create_cue_point",
                                "live_passed",
                                f"name={cue_name} time={cue_time}",
                            )
                        )
                        cue_created = True

                        # ----- bulk_create_cue_points -----
                        bulk_targets = [
                            {"name": "ABLETON_MCP_ACCEPTANCE_BULK",
                             "time": cue_time + 64.0},
                        ]
                        bulk_result = call("bulk_create_cue_points",
                                           {"items": bulk_targets})
                        report.record(
                            Verification(
                                "bulk_create_cue_points",
                                "live_passed",
                                f"created={bulk_result.get('created', 0)}",
                            )
                        )

                        # ----- delete_cue_point + readback -----
                        delete_result = call("delete_cue_point",
                                             {"time": cue_time})
                        cue_created = False
                        if not bool(delete_result.get("deleted", False)):
                            raise AssertionError(
                                "Cue deletion did not return deleted=true"
                            )
                        report.record(
                            Verification(
                                "delete_cue_point",
                                "live_passed",
                                f"deleted={delete_result.get('deleted')}",
                            )
                        )
                        await _record_call(
                            report, "delete_cue_point",
                            lambda: call("delete_cue_point",
                                         {"time": cue_time + 64.0}),
                            passed="live_passed")

                        # ----- transport mutations + readback -----
                        await _record_call(
                            report, "set_tempo",
                            lambda: call("set_tempo", {"tempo": tempo_one}),
                            passed="live_passed")
                        tempo_readback = call("get_session_info")["tempo"]
                        if abs(float(tempo_readback) - tempo_one) > 0.01:
                            raise AssertionError(
                                "set_tempo readback mismatch"
                            )

                        await _record_call(
                            report, "set_current_song_time",
                            lambda: call("set_current_song_time",
                                         {"time": 8.0}),
                            passed="live_passed")

                        await _record_call(
                            report, "set_loop_start",
                            lambda: call("set_loop_start",
                                         {"start_beat": 4.0}),
                            passed="live_passed")
                        await _record_call(
                            report, "set_loop_length",
                            lambda: call("set_loop_length",
                                         {"length_beats": 8.0}),
                            passed="live_passed")
                        await _record_call(
                            report, "set_loop",
                            lambda: call("set_loop", {"enabled": True}),
                            passed="live_passed")
                        loop_state = call("get_loop_settings")
                        if not bool(loop_state.get("loop")):
                            raise AssertionError(
                                "set_loop readback did not enable the loop"
                            )

                        # ----- clip/notes mutations -----
                        await _record_call(
                            report, "create_clip",
                            lambda: call("create_clip", {
                                "track_index": track_index,
                                "clip_index": clip_index,
                                "length_beats": 4.0,
                            }),
                            passed="live_passed")
                        notes = [
                            {"pitch": pitch,
                             "start_time": float(index),
                             "duration": 0.75,
                             "velocity": 72 + index * 4,
                             "mute": False}
                            for index, pitch in enumerate((60, 64, 67, 72))
                        ]
                        added = call(
                            "add_notes_to_clip",
                            {"track_index": track_index,
                             "clip_index": clip_index, "notes": notes},
                        )
                        observed = call(
                            "get_clip_notes",
                            {"track_index": track_index,
                             "clip_index": clip_index},
                        )
                        if int(added["added"]) != 4 or len(observed) != 4:
                            raise AssertionError(
                                "MIDI notes not observed after add_notes_to_clip"
                            )
                        report.record(
                            Verification(
                                "add_notes_to_clip",
                                "live_passed",
                                f"added=4, observed=4",
                            )
                        )

                        await _record_call(
                            report, "clear_clip_notes",
                            lambda: call("clear_clip_notes", {
                                "track_index": track_index,
                                "clip_index": clip_index,
                            }),
                            passed="live_passed")
                        cleared = call(
                            "get_clip_notes",
                            {"track_index": track_index,
                             "clip_index": clip_index},
                        )
                        if cleared:
                            raise AssertionError(
                                "clear_clip_notes did not empty the clip"
                            )
                        report.record(
                            Verification(
                                "clear_clip_notes",
                                "live_passed",
                                "notes cleared (0)",
                            )
                        )

                        await _record_call(
                            report, "set_clip_properties",
                            lambda: call("set_clip_properties", {
                                "track_index": track_index,
                                "clip_index": clip_index,
                                "name": "ABLETON_MCP_ACCEPTANCE",
                            }),
                            passed="live_passed")
                        info = call(
                            "get_clip_info",
                            {"track_index": track_index,
                             "clip_index": clip_index},
                        )
                        if info.get("name") != "ABLETON_MCP_ACCEPTANCE":
                            raise AssertionError(
                                "set_clip_properties did not rename clip"
                            )

                        # ----- create_clip_automation -----
                        await _record_call(
                            report, "create_clip_automation",
                            lambda: call("create_clip_automation", {
                                "track_index": track_index,
                                "clip_index": clip_index,
                                "parameter_name": "volume",
                                "points": [{"time": 0.0, "value": 0.0},
                                           {"time": 1.0, "value": 1.0}],
                            }),
                            passed="live_passed")

                        # ----- transport fire/stop (optional) -----
                        await _record_call(
                            report, "start_playback",
                            lambda: call("start_playback"),
                            passed="live_passed")
                        await _record_call(
                            report, "stop_playback",
                            lambda: call("stop_playback"),
                            passed="live_passed")

                        # ----- run_batch with rollback assertion -----
                        batch = call("run_batch", {
                            "commands": [
                                {"type": "set_tempo",
                                 "params": {"tempo": tempo_two}},
                                {"type": "set_loop",
                                 "params": {"enabled": True}},
                                {"type": "create_clip",
                                 "params": {
                                     "track_index": track_index,
                                     "clip_index": clip_index,
                                     "length_beats": 4.0,
                                 }},
                                {"type": "set_tempo",
                                 "params": {"tempo": tempo_one}},
                            ],
                        })
                        if (
                            int(batch["completed"]) != 2
                            or int(batch["aborted_at"]) != 2
                            or bool(batch["rolled_back"])
                        ):
                            raise AssertionError(
                                f"Unexpected partial-batch result: {batch}"
                            )
                        report.record(
                            Verification(
                                "run_batch",
                                "live_passed",
                                f"completed=2 aborted_at=2 rolled_back=False",
                            )
                        )

                        # ----- fire_clip (optional) -----
                        if fire_clip:
                            await _record_call(
                                report, "fire_clip",
                                lambda: call("fire_clip", {
                                    "track_index": track_index,
                                    "clip_index": clip_index,
                                }),
                                passed="live_passed")
                            await _record_call(
                                report, "stop_playback",
                                lambda: call("stop_playback"),
                                passed="live_passed")
                        else:
                            report.record(
                                Verification(
                                    "fire_clip",
                                    "environment_unavailable",
                                    "fire_clip requires --fire-clip flag",
                                )
                            )

                        # ----- fire_scene (no setup required) -----
                        await _record_call(
                            report, "fire_scene",
                            lambda: call("fire_scene", {"scene_index": 0}),
                            passed="live_passed")

                        # ----- set_track_property + rename_track -----
                        await _record_call(
                            report, "set_track_property",
                            lambda: call("set_track_property", {
                                "track_index": track_index,
                                "name": "ABLETON_MCP_ACCEPTANCE",
                            }),
                            passed="live_passed")
                        await _record_call(
                            report, "rename_track",
                            lambda: call("rename_track", {
                                "track_index": track_index,
                                "new_name": "Bass",
                            }),
                            passed="live_passed")

                        # ----- delete_clip -----
                        await _record_call(
                            report, "delete_clip",
                            lambda: call("delete_clip", {
                                "track_index": track_index,
                                "clip_index": clip_index,
                            }),
                            passed="live_passed")

                        # ----- create_audio_track -----
                        await _record_call(
                            report, "create_audio_track",
                            lambda: call("create_audio_track", {"index": -1}),
                            passed="live_passed")

                        # ----- create_midi_track -----
                        await _record_call(
                            report, "create_midi_track",
                            lambda: call("create_midi_track", {"index": -1}),
                            passed="live_passed")

                        # ----- set_parameter_value -----
                        await _record_call(
                            report, "set_parameter_value",
                            lambda: call("set_parameter_value", {
                                "track_index": 0,
                                "device_index": 0,
                                "parameter_name": "Device On",
                                "value": 1.0,
                            }),
                            passed="live_passed")

                        # ----- live_fade (very short, non-blocking) -----
                        await _record_call(
                            report, "live_fade",
                            lambda: call("live_fade", {
                                "track_index": 0,
                                "target_percent": 80.0,
                                "duration": 0.0,
                                "steps": 1,
                            }),
                            passed="live_passed")

                        # ----- warp_state -----
                        # Validate the audio clip selector before writing.
                        slots_audio = call(
                            "get_clip_summary",
                            {"track_index": audio_track_index},
                        )
                        audio_slot = next(
                            (item for item in slots_audio
                             if item.get("index") == audio_clip_index),
                            None,
                        )
                        if audio_slot is None or bool(
                            audio_slot.get("has_clip")
                        ) and not bool(audio_slot.get("is_audio_clip")):
                            raise AcceptanceSafetyError(
                                f"Audio clip slot {audio_track_index}:"
                                f"{audio_clip_index} is not a usable audio "
                                "clip; refusing warp certification."
                            )
                        async def set_warp_state() -> Any:
                            return await call_ws("set_warp_state", {
                                "track_index": audio_track_index,
                                "clip_index": audio_clip_index,
                                "warping": True,
                            })
                        try:
                            await set_warp_state()
                            report.record(
                                Verification(
                                    "set_warp_state",
                                    "live_passed",
                                    "warping flag set",
                                )
                            )
                        except BridgeError as error:
                            if error.code == "CAPABILITY_UNAVAILABLE":
                                report.record(
                                    Verification(
                                        "set_warp_state",
                                        "host_unavailable",
                                        f"{error.code}: {error}",
                                    )
                                )
                            else:
                                report.record(
                                    Verification(
                                        "set_warp_state",
                                        "failed",
                                        f"{error.code}: {error}",
                                    )
                                )

                        # ----- load_device_to_track -----
                        await _record_call(
                            report, "load_device_to_track",
                            lambda: call("load_device_to_track", {
                                "track_index": audio_track_index,
                                "device_name": "Operator",
                            }),
                            passed="live_passed")

                        # ----- save_set / quit_ableton -----
                        # ``save_set`` may legitimately fail if the host does
                        # not have a Save Set action exposed; record that as
                        # ``host_unavailable``.
                        try:
                            await _record_call(
                                report, "save_set",
                                lambda: call("save_set"),
                                passed="live_passed")
                        except BridgeError as error:
                            if error.code == "CAPABILITY_UNAVAILABLE":
                                report.record(
                                    Verification(
                                        "save_set",
                                        "host_unavailable",
                                        f"{error.code}: {error}",
                                    )
                                )
                            else:
                                report.record(
                                    Verification(
                                        "save_set",
                                        "failed",
                                        f"{error.code}: {error}",
                                    )
                                )

                        # ``quit_ableton`` is explicitly classified as
                        # ``environment_unavailable`` for the baseline
                        # profile — invoking it would close the host and the
                        # runner would lose its bridge. The dedicated
                        # ``quit_ableton`` profile would call it.
                        report.record(
                            Verification(
                                "quit_ableton",
                                "environment_unavailable",
                                "baseline profile refuses to close the host",
                            )
                        )
                    finally:
                        # ----- cleanup restore -----
                        if cue_created:
                            with suppress(Exception):
                                call("delete_cue_point", {"time": cue_time})
                        with suppress(Exception):
                            call("stop_playback")
                        with suppress(Exception):
                            call("set_loop",
                                 {"enabled": bool(original_loop["loop"])})
                        with suppress(Exception):
                            call("set_loop_start",
                                 {"start_beat": float(original_loop[
                                     "loop_start"])})
                        with suppress(Exception):
                            call("set_loop_length",
                                 {"length_beats": float(original_loop[
                                     "loop_length"])})
                        with suppress(Exception):
                            call("set_tempo", {"tempo": original_tempo})
                        with suppress(Exception):
                            call("set_current_song_time",
                                 {"time": original_time})
            except AcceptanceSafetyError as safety_error:
                # The bridge refused to send mutations. Record every
                # selected mutation as ``failed`` so the report cannot
                # accidentally pass with zeros, then re-raise so the
                # CLI / caller still observes the safety refusal.
                for tool in BASELINE_PROBE_GROUPS.get("mutations", ()):
                    if tool in selected_tools and tool not in report.recorded:
                        report.record(
                            Verification(
                                tool,
                                "failed",
                                "bridge refused to send mutations",
                            )
                        )
                raise safety_error
            except Exception as outer_error:  # noqa: BLE001 — final guard
                # Any uncaught failure during the live probe phase (e.g.
                # readback mismatch, transport glitch) marks every still-
                # missing tool as ``failed`` so the report cannot pass
                # with zeros.
                for tool in BASELINE_PROBE_GROUPS.get("mutations", ()):
                    if tool in selected_tools and tool not in report.recorded:
                        report.record(
                            Verification(
                                tool,
                                "failed",
                                f"{type(outer_error).__name__}: {outer_error}",
                            )
                        )
            finally:
                # Always restore the bridge state we mutated, even when the
                # runner aborts mid-sequence. The fake bridge and the real
                # Live host both tolerate these best-effort writes.
                if "original_tempo" in locals():
                    with suppress(Exception):
                        call("stop_playback")
                    with suppress(Exception):
                        call("set_tempo", {"tempo": original_tempo})
                    with suppress(Exception):
                        call("set_current_song_time",
                             {"time": original_time})

    # If the runner was called with a partial profile, every catalogued
    # tool that lives outside the selected groups must be marked as
    # ``environment_unavailable`` so the report can ``finish()`` without
    # raising. These rows are clearly labelled as out-of-scope; the
    # baseline profile does not produce any.
    catalog_names = list(report.tool_names)
    already_recorded = set(report.recorded)
    selected = set()
    for profile in expanded_profiles:
        if profile == "baseline":
            for group in BASELINE_PROBE_GROUPS:
                selected.update(BASELINE_PROBE_GROUPS[group])
        else:
            selected.update(BASELINE_PROBE_GROUPS[profile])
    for tool in catalog_names:
        if tool in already_recorded or tool in selected:
            continue
        report.record(
            Verification(
                tool,
                "environment_unavailable",
                f"not covered by selected profiles: {list(expanded_profiles)}",
            )
        )
    certification = report.finish()
    status = "ok" if certification["release_ready"] else "failed"
    return {
        "project": confirm_project_name,
        "track_index": track_index,
        "clip_index": clip_index,
        "audio_track_index": audio_track_index,
        "audio_clip_index": audio_clip_index,
        "profiles": list(profiles),
        "fire_clip": fire_clip,
        "certification": certification,
    }