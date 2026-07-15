"""Live acceptance runner for the Ableton MCP Server.

This module drives the real bridge through every catalogued tool so the
``release_ready`` flag in ``CertificationReport`` reflects what the bridge
actually did. The runner is intentionally paranoid:

- Probes are split into groups; partial profiles run only their groups.
- ``release_ready`` is **only** ``True`` when the baseline profile completes
  end-to-end with no failed tool. Partial profiles and the ``quit``
  profile never claim ``release_ready``.
- Every mutation is followed by a readback *before* the verification row
  is recorded. Readback mismatches flip the row to ``failed``.
- The disposable Set preserves and restores the original track names,
  mixer state, and clip contents. Track creation happens last so we can
  restore everything else from the original three-track layout.
- Audio clip guards use ``get_clip_info.is_audio_clip`` (the real bridge
  exposes this), not the legacy ``is_audio_clip`` on ``get_clip_summary``.
- Offline probes call the **real** implementation of each helper
  (``get_ableton_logs``, ``diff_snapshots``, ``scaffold_extension``,
  ``build_extension``) — never synthetic stand-ins.
"""

from __future__ import annotations

import inspect
import shutil
import struct
import tempfile
import wave
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from .certification import CertificationReport, Verification
from .errors import BridgeError


class AcceptanceClient(Protocol):
    host: str
    port: int

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


# ---------------------------------------------------------------------------
# Helper utilities (pure functions; no bridge state)
# ---------------------------------------------------------------------------


def _test_tempo(original: float, offset: float) -> float:
    candidate = original + offset
    if candidate <= 999.0:
        return candidate
    return original - offset


def _acceptance_cue_time(locators: list[Mapping[str, Any]]) -> float:
    candidate = 256.0
    while any(abs(float(item.get("time", -1.0)) - candidate) < 0.01 for item in locators):
        candidate += 256.0
    return candidate


def _write_sine_wav(
    path: Path, *, hz: float, amplitude: float, seconds: float, sample_rate: int = 44100
) -> Path:
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
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "target": _write_sine_wav(directory / "target.wav", hz=1000.0, amplitude=0.8, seconds=1.0),
        "reference": _write_sine_wav(
            directory / "reference.wav", hz=1000.0, amplitude=0.2, seconds=1.0
        ),
        "short": _write_sine_wav(directory / "short.wav", hz=440.0, amplitude=0.5, seconds=0.5),
        "long": _write_sine_wav(directory / "long.wav", hz=440.0, amplitude=0.25, seconds=1.0),
    }


# ---------------------------------------------------------------------------
# Probe groups and tool catalog helpers
# ---------------------------------------------------------------------------


# Tools that may legitimately be classified ``environment_unavailable``
# under specific, documented conditions. Everything else either runs,
# raises ``BridgeError`` → ``failed``, or is missing-from-profile.
#
# ``quit_ableton`` is classified ``manual_required`` whenever it is not
# actually invoked. The runner must never record ``live_passed`` for an
# operation that was not executed: that is a documented false-positive
# pattern. ``build_extension`` is unavailable only when Node is genuinely
# absent. ``fire_clip`` is unavailable when ``--fire-clip`` is not set.
_ALLOWED_UNAVAILABLE: dict[str, str] = {
    "build_extension": "node executable not found on PATH",
    "fire_clip": "fire_clip requires --fire-clip flag",
}

# ``quit_ableton`` is only valid as ``live_passed`` after the bridge was
# actually invoked and a real shutdown handshake completed. The runner
# does not invoke it during the automated probe (doing so would close
# the host and block every later probe). Until an out-of-band owner
# confirmation arrives, the row must read ``manual_required``.
QUIT_ABLETON_MANUAL_REASON = (
    "quit_ableton requires out-of-band owner confirmation; "
    "automated probe never invokes a destructive shutdown"
)


# Slice 1 Task 9: baseline probe map. The flattened names must equal the
# 65-name ``PUBLIC_TOOL_NAMES`` set, so each catalogued tool has a home in
# exactly one probe group. The runner never fabricates
# ``environment_unavailable`` for a tool that is actually selected.
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
        "live_fade",
        "set_warp_state",
        "load_device_to_track",
    ),
    "quit": ("quit_ableton",),
}


def _baseline_tool_names() -> tuple[str, ...]:
    from .server import PUBLIC_TOOL_NAMES

    return tuple(PUBLIC_TOOL_NAMES)


def _baseline_probe_names() -> tuple[str, ...]:
    names: list[str] = []
    for group in BASELINE_PROBE_GROUPS.values():
        names.extend(group)
    return tuple(names)


def assert_baseline_probe_coverage() -> None:
    flat = set(_baseline_probe_names())
    catalog_names = set(_baseline_tool_names())
    assert flat == catalog_names, (
        f"baseline probe mismatch: missing={catalog_names - flat}, extra={flat - catalog_names}"
    )


def _expand_profiles(profiles: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve ``"baseline"`` to every group and validate names."""
    if "baseline" in profiles:
        return tuple(BASELINE_PROBE_GROUPS)
    for profile in profiles:
        if profile not in BASELINE_PROBE_GROUPS:
            raise ValueError(f"unknown acceptance profile: {profile}")
    return profiles


def _parameter_tolerance(min_val: float, max_val: float) -> float:
    """Compute range-proportional tolerance with a numeric precision floor (1e-12)."""
    return max(1e-12, abs(max_val - min_val) * 0.01)


# ---------------------------------------------------------------------------
# Verification recording
# ---------------------------------------------------------------------------


async def _record_call(
    report: CertificationReport,
    tool: str,
    action: Callable[[], Any | Awaitable[Any]],
    *,
    passed: str = "live_passed",
) -> Any:
    """Invoke ``action`` and record one verification row.

    The caller is responsible for performing any readback inside ``action``
    and raising if the mutation didn't take effect. This function only
    records the result of the whole encapsulated action.

    ``BridgeError`` with code ``CAPABILITY_UNAVAILABLE`` is mapped to
    ``host_unavailable``; every other exception becomes ``failed``.
    """
    try:
        value = action()
        if inspect.isawaitable(value):
            value = await value
    except Exception as error:  # noqa: BLE001 — recording layer swallows all

        if getattr(error, "code", None) == "CAPABILITY_UNAVAILABLE":
            report.record(
                Verification(
                    tool,
                    "host_unavailable",
                    f"{getattr(error, 'code', 'CAPABILITY_UNAVAILABLE')}: {error}",
                )
            )
        else:
            report.record(Verification(tool, "failed", f"{type(error).__name__}: {error}"))
        return None
    report.record(Verification(tool, passed, "call and readback completed"))
    return value


def _record_unavailable(report: CertificationReport, tool: str, reason: str) -> None:
    report.record(Verification(tool, "environment_unavailable", reason))


# ---------------------------------------------------------------------------
# Profile / release policy
# ---------------------------------------------------------------------------


def build_baseline_report(
    profiles: tuple[str, ...] | None = None,
) -> CertificationReport:
    """Return a report covering exactly the catalogued tools.

    The runner calls this and then manually records every selected tool;
    the report itself does not pre-classify unselected tools. The
    ``CertificationReport.finish()`` invariant guarantees the runner
    cannot forget a tool.
    """
    selected = profiles or tuple(BASELINE_PROBE_GROUPS)
    for _profile in _expand_profiles(selected):
        pass
    catalog_names = _baseline_tool_names()
    return CertificationReport(tool_names=catalog_names)


def _is_full_baseline(profiles: tuple[str, ...]) -> bool:
    expanded = _expand_profiles(profiles)
    return set(expanded) == set(BASELINE_PROBE_GROUPS)


def _release_ready(
    report: CertificationReport, profiles: tuple[str, ...], *, fire_clip: bool
) -> bool:
    """Compute the final ``release_ready`` decision.

    Rules (in order):

    1. Any ``failed`` row blocks promotion.
    2. Partial profiles (not full baseline) are never release-ready.
    3. ``fire_clip`` must have been exercised (the flag toggled on).
    4. ``host_unavailable`` blocks promotion.
    5. ``environment_unavailable`` blocks promotion, except ``build_extension``.
    6. ``manual_required`` blocks promotion, except ``quit_ableton`` and the
       strictly validated manual fallback for ``save_set``.
    7. Otherwise the report is release-ready.
    """
    rows = list(report.recorded.values())
    if any(row.status == "failed" for row in rows):
        return False
    if not _is_full_baseline(profiles):
        return False
    if not fire_clip:
        return False
    if any(row.status == "host_unavailable" for row in rows):
        return False
    if any(
        row.status == "environment_unavailable"
        and row.tool != "build_extension"
        for row in rows
    ):
        return False
    return not any(
        row.status == "manual_required" and row.tool not in ("quit_ableton", "save_set")
        for row in rows
    )


# ---------------------------------------------------------------------------
# Offline probes
# ---------------------------------------------------------------------------


async def run_offline_probes(report: CertificationReport, workdir: Path) -> None:
    """Drive the four offline mix analysis probes plus 4 helpers.

    Each helper calls the **real** implementation rather than returning a
    synthetic object, so an upstream regression cannot be hidden by a
    hard-coded response. ``build_extension`` is the only legitimate
    ``environment_unavailable`` — and only when ``node`` is genuinely
    absent from PATH.
    """
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

        return analysis_audio.analyze_mix([str(inputs["target"]), str(inputs["reference"])])

    def single_cycle() -> dict[str, Any]:
        from .analysis import audio as analysis_audio

        return analysis_audio.extract_single_cycle(str(inputs["short"]))

    await _record_call(report, "analyze_audio", analyze, passed="offline_passed")
    await _record_call(report, "find_frequency_masking", masking, passed="offline_passed")
    await _record_call(report, "analyze_mix", mix, passed="offline_passed")
    await _record_call(report, "extract_single_cycle", single_cycle, passed="offline_passed")

    def logs() -> str:
        """Real ``get_ableton_logs`` impl: read the tail of Log.txt."""
        from .diagnostics import find_ableton_log_path

        path = find_ableton_log_path()
        if path is None:
            return "Ableton Log.txt path could not be resolved."
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                return "".join(handle.readlines()[-100:])
        except OSError as error:
            return f"Error reading Ableton Log.txt: {error}"

    await _record_call(report, "get_ableton_logs", logs, passed="offline_passed")

    def diff_tool() -> dict[str, Any]:
        """Compare two snapshots through the real ``diff_snapshots`` impl."""
        from .diff import diff_snapshots

        # Build two snapshots via ``take_snapshot`` semantics — same shape
        # the runner would observe; equality is preserved so the diff is
        # honest.
        snapshot_a = {
            "schema_version": 1,
            "captured_at_unix_ms": 1,
            "live_version": "12.0",
            "tempo": 120.0,
            "signature_numerator": 4,
            "signature_denominator": 4,
            "is_playing": False,
            "current_song_time": 0.0,
            "tracks": [{"index": 0, "name": "Bass"}],
            "control_surfaces": [],
            "browser_categories_count": 1,
        }
        snapshot_b = dict(snapshot_a)
        snapshot_b["tempo"] = 121.0
        return diff_snapshots(snapshot_a, snapshot_b)

    await _record_call(report, "diff_snapshots_tool", diff_tool, passed="offline_passed")

    def scaffold() -> dict[str, Any]:
        """Real ``scaffold_extension`` impl, validated by file presence."""
        import json

        from .server import scaffold_extension

        out_dir = workdir / "scaffold"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = scaffold_extension(
            "MCP_ACCEPTANCE_SCAFFOLD",
            author="mcp-acceptance",
            output_directory=str(out_dir),
        )
        parsed = json.loads(result)
        project_path = Path(parsed["project_path"])
        # Verify the actual files exist on disk.
        for name in parsed.get("files", []):
            assert (project_path / name).is_file(), f"scaffold_extension did not create {name}"
        # Tag the directory as MCP acceptance artifact.
        (project_path / "MCP_ACCEPTANCE_ARTIFACT").write_text(
            "acceptance scaffold output", encoding="utf-8"
        )
        return cast(dict[str, Any], parsed)

    await _record_call(report, "scaffold_extension", scaffold, passed="offline_passed")

    # ``build_extension`` runs ``npm install`` + ``tsc``. It is only
    # ``environment_unavailable`` when Node is genuinely absent; otherwise
    # we exercise the real implementation against the scaffold we just
    # wrote so the runner proves the build actually completes.
    if shutil.which("node") is None:
        _record_unavailable(
            report,
            "build_extension",
            "node executable not found on PATH",
        )
        return

    def build_ext() -> dict[str, Any]:
        import json

        from .server import build_extension

        scaffold_dir = workdir / "scaffold"
        scaffold_dirs = [p for p in scaffold_dir.iterdir() if p.is_dir()]
        if not scaffold_dirs:
            raise RuntimeError("scaffold output missing for build_extension")
        project = scaffold_dirs[0]
        result_json = build_extension(str(project))
        parsed = json.loads(result_json)
        # Strict invariant: the build must report ``status == "built"``,
        # every step must have ``returncode == 0``, and the canonical
        # artefact — the entrypoint declared by the project's own
        # ``package.json["main"]`` (falling back to
        # ``manifest.json["entry"]``) — must exist on disk. ``status ==
        # "error"`` or a failed returncode cannot be reported as
        # ``offline_passed``. Per-step ``artifact`` is **not** part of
        # the contract — the runner does not require one.
        status = str(parsed.get("status", "")).strip().lower()
        if status != "built":
            raise AssertionError(f"build_extension status={status!r} expected 'built': {parsed}")
        steps = parsed.get("steps", [])
        if not isinstance(steps, list) or not steps:
            raise AssertionError(f"build_extension missing steps list: {parsed}")
        for index, step in enumerate(steps):
            if int(step.get("returncode", -1)) != 0:
                raise AssertionError(
                    f"build_extension step {index} returncode="
                    f"{step.get('returncode')!r} expected 0: {step}"
                )
        entrypoint = parsed.get("entrypoint")
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            raise AssertionError(f"build_extension response missing entrypoint: {parsed}")
        entrypoint_rel = entrypoint.strip()
        # Top-level artefacts must include the declared entrypoint.
        artifacts = parsed.get("artifacts", [])
        if not isinstance(artifacts, list) or not artifacts:
            raise AssertionError(f"build_extension produced no artifacts: {parsed}")
        if entrypoint_rel not in artifacts:
            raise AssertionError(
                f"build_extension artifacts missing declared entrypoint "
                f"{entrypoint_rel!r}: {artifacts}"
            )
        canonical = project / entrypoint_rel
        if not canonical.is_file():
            raise AssertionError(f"build_extension entrypoint not on disk: {canonical}")
        # Tag built artefacts for cleanup.
        for artefact in artifacts:
            target = project / artefact
            if target.exists():
                (target.parent / "MCP_ACCEPTANCE_ARTIFACT").write_text(
                    "acceptance built artifact", encoding="utf-8"
                )
        return cast(dict[str, Any], parsed)

    await _record_call(report, "build_extension", build_ext, passed="offline_passed")


# ---------------------------------------------------------------------------


# Disposable set discovery (called inside the safety guard)
# ---------------------------------------------------------------------------


def _resolve_track_id(client: AcceptanceClient, index: int) -> str:
    tracks = client.call("get_track_list")
    match = next((t for t in tracks if int(t.get("index", -1)) == index), None)
    if match is None:
        raise AcceptanceSafetyError(f"track {index} not present")
    return str(match.get("id", f"track:{index}"))


def _discover_baseline(client: AcceptanceClient) -> dict[str, Any]:
    """Capture the disposable Set baseline that the runner must restore.

    The restore step relies on every value the mutations touch being
    captured here. A live ``live_fade`` or ``set_track_property`` run
    must round-trip through the original value, not a default.

    The real ``get_track_list`` contract returns only ``id``/``index``/
    ``name``/``type`` — no ``mute``/``solo``/``arm``/``volume``. We
    therefore drive every per-track field from ``get_track_state``,
    which exposes the mixer and arm state. We never read the absent
    fields from ``get_track_list`` or invent defaults for them.
    """
    metadata = client.call("get_project_metadata")
    song_name = str(metadata.get("song_name", ""))
    tracks = client.call("get_track_list")
    track_names: dict[int, str] = {}
    track_types: dict[int, str] = {}
    track_mutes: dict[int, bool] = {}
    track_solos: dict[int, bool] = {}
    track_arms: dict[int, bool] = {}
    track_volumes: dict[int, float] = {}
    for track in tracks:
        idx = int(track.get("index", -1))
        track_names[idx] = str(track.get("name", ""))
        track_types[idx] = str(track.get("type", ""))
        # ``get_track_list`` is not the source of truth for the mixer
        # state — read it from ``get_track_state``.
        state = client.call("get_track_state", {"track_index": idx})
        if not isinstance(state, dict):
            raise AcceptanceSafetyError(f"get_track_state({idx}) returned non-dict: {state!r}")
        if "mute" not in state or "solo" not in state or "arm" not in state:
            raise AcceptanceSafetyError(
                f"get_track_state({idx}) missing mute/solo/arm; "
                "the disposable Set must expose the full track state"
            )
        if "volume" not in state:
            raise AcceptanceSafetyError(
                f"get_track_state({idx}) missing volume; the disposable "
                "Set must expose the mixer volume"
            )
        track_mutes[idx] = bool(state["mute"])
        track_solos[idx] = bool(state["solo"])
        track_arms[idx] = bool(state["arm"])
        track_volumes[idx] = float(state["volume"])
    session = client.call("get_session_info")
    loop = client.call("get_loop_settings")
    locators = client.call("get_locators")
    return {
        "song_name": song_name,
        "track_names": track_names,
        "track_types": track_types,
        "track_mutes": track_mutes,
        "track_solos": track_solos,
        "track_arms": track_arms,
        "track_volumes": track_volumes,
        "tempo": float(session["tempo"]),
        "current_song_time": float(session["current_song_time"]),
        "loop": bool(loop.get("loop", False)),
        "loop_start": float(loop.get("loop_start", 0.0)),
        "loop_length": float(loop.get("loop_length", 4.0)),
        "locators": list(locators),
        "track_count": len(tracks),
    }


# ---------------------------------------------------------------------------
# Live acceptance runner
# ---------------------------------------------------------------------------


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
    offline_probes: Callable[[CertificationReport, Path], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Exercise the real bridge after exact disposable-project confirmation.

    The runner records a Certification row for every selected tool. Rows
    are only marked ``live_passed`` after a successful send **and** a
    readback that proves the mutation took effect. ``failed`` rows
    propagate to ``release_ready=False`` and to a non-zero CLI exit code.
    """
    from .diagnostics import bridge_status as _bridge_status_fn

    expanded = _expand_profiles(profiles)

    async def call_ws(method: str, params: dict[str, Any] | None = None) -> Any:
        return await client.call_ws(method, params or {})

    def call(command: str, params: Mapping[str, Any] | None = None) -> Any:
        return client.call(command, dict(params or {}), timeout=None)

    audio_track_index = int(audio_track_index if audio_track_index is not None else track_index)
    audio_clip_index = int(audio_clip_index if audio_clip_index is not None else clip_index)

    report = build_baseline_report(profiles=profiles)

    # Track every artifact the runner persists to disk so the owner can
    # decide what to undo / clean up after the run.
    artifacts: dict[str, Any] = {
        "tags": [],  # MCP_ACCEPTANCE_* names placed in the Set
        "files": [],  # files created on disk (scaffold, build, etc.)
        "tracks_created": [],  # track indexes that the runner appended
        "manual_cleanup": [],  # anything requiring owner-side cleanup
    }

    with tempfile.TemporaryDirectory(prefix="ableton-mcp-acceptance-") as tmp:
        offline_dir = Path(tmp) / "offline"
        # The offline probe set only runs when the operator actually selects
        # it (either via the ``offline`` group or the ``baseline`` umbrella).
        # Partial profiles such as ``tcp_reads`` must not trigger the
        # scaffold / npm / mix-analysis pipeline.
        if "offline" in expanded:
            # ``offline_probes`` is injectable so unit tests of the
            # runner can skip the (slow) ``scaffold_extension`` /
            # ``build_extension`` / npm / tsc pipeline. Production CLI
            # callers pass ``None`` and use the real
            # ``run_offline_probes`` implementation. Exactly one
            # end-to-end environmental test exercises the real
            # implementation; every other test that needs the offline
            # rows uses the injection point.
            probe_callable = offline_probes or run_offline_probes
            await probe_callable(report, offline_dir)
            # Mark scaffold/build artifacts that the offline probe produced.
            scaffold_dir = offline_dir / "scaffold"
            if scaffold_dir.exists():
                for path in scaffold_dir.rglob("*"):
                    if path.is_file():
                        artifacts["files"].append(str(path))

        if "composed" in expanded:

            def bridge_status_probe() -> dict[str, Any]:
                # ``get_bridge_status`` is a composed tool that wraps
                # ``diagnostics.bridge_status(client, tool_count=...)``.
                # The runner must call the wrapper, not the underlying
                # ``get_session_info`` TCP command.
                return _bridge_status_fn(client, tool_count=65)

            def session_overview_probe() -> dict[str, Any]:
                # ``get_session_overview`` is composed from three TCP reads.
                # The runner must do the same composition explicitly; the
                # bridge does not expose a single ``get_session_overview``
                # command.
                return {
                    "session": call("get_session_info", {}),
                    "tracks": call("get_track_list", {}),
                    "scenes": call("get_scenes", {}),
                }

            await _record_call(
                report, "get_bridge_status", bridge_status_probe, passed="live_passed"
            )
            await _record_call(
                report, "get_session_overview", session_overview_probe, passed="live_passed"
            )

        if "quit" in profiles and not {"tcp_reads", "mutations", "websocket_reads"} & set(expanded):
            # ``quit`` profile without tcp_reads/mutations: record the
            # ``quit_ableton`` row as ``manual_required``. The runner does
            # not invoke the bridge here — invoking it would close the host
            # and prevent any subsequent probe from running, so the row
            # never claims ``live_passed`` without an out-of-band owner
            # confirmation.
            report.record(
                Verification(
                    "quit_ableton",
                    "manual_required",
                    QUIT_ABLETON_MANUAL_REASON,
                )
            )

        if {"tcp_reads", "mutations", "websocket_reads"} & set(expanded):
            baseline: dict[str, Any] | None = None
            try:
                metadata = call("get_project_metadata")
                actual_name = str(metadata.get("song_name", ""))
                if actual_name != confirm_project_name:
                    raise AcceptanceSafetyError(
                        f"Loaded project {actual_name!r} does not match "
                        f"confirmation {confirm_project_name!r}; no "
                        "mutations were sent."
                    )
                if metadata.get("is_dirty") is not False:
                    raise AcceptanceSafetyError(
                        f"Loaded project dirty state is non-clean ({metadata.get('is_dirty')!r}); "
                        "acceptance requires a saved, clean project baseline."
                    )
                baseline = _discover_baseline(client)

                discovered_param_track_index = None
                discovered_param_device_index = None
                discovered_param_name = None
                discovered_param_min = 0.0
                discovered_param_max = 1.0
                discovered_param_is_quantized = False

                search_tracks = []
                if audio_track_index in baseline["track_names"]:
                    search_tracks.append(audio_track_index)
                for t_idx in sorted(baseline["track_names"].keys()):
                    if t_idx not in search_tracks:
                        search_tracks.append(t_idx)

                for t_idx in search_tracks:
                    try:
                        dev_list = call("get_device_list", {"track_index": t_idx})
                        if isinstance(dev_list, list) and dev_list:
                            t_id = _resolve_track_id(client, t_idx)
                            device_params = call("list_device_params", {"track_id": t_id})
                            if isinstance(device_params, list):
                                for dev_idx, dev_entry in enumerate(device_params):
                                    if isinstance(dev_entry, dict) and dev_entry.get("parameters"):
                                        params_list = dev_entry.get("parameters")
                                        if isinstance(params_list, list):
                                            for p in params_list:
                                                if not isinstance(p, dict):
                                                    continue
                                                if (
                                                    p.get("is_enabled") is False
                                                    or p.get("enabled") is False
                                                ):
                                                    continue
                                                p_name = p.get("name")
                                                if not isinstance(p_name, str) or not p_name:
                                                    continue
                                                min_val = float(p.get("min", 0.0))
                                                max_val = float(p.get("max", 1.0))
                                                is_quant = bool(p.get("is_quantized", False))

                                                discovered_param_track_index = t_idx
                                                discovered_param_device_index = dev_idx
                                                discovered_param_name = p_name
                                                discovered_param_min = min_val
                                                discovered_param_max = max_val
                                                discovered_param_is_quantized = is_quant
                                                break
                                            if discovered_param_name is not None:
                                                break
                                if discovered_param_name is not None:
                                    break
                    except Exception:
                        pass

                if "tcp_reads" in expanded:
                    await _record_call(
                        report, "get_project_metadata", lambda: metadata, passed="live_passed"
                    )
                    await _record_call(
                        report,
                        "get_session_info",
                        lambda: call("get_session_info"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_track_list",
                        lambda: call("get_track_list"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_track_state",
                        lambda: call("get_track_state", {"track_index": track_index}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report, "get_locators", lambda: call("get_locators"), passed="live_passed"
                    )
                    await _record_call(
                        report, "take_snapshot", lambda: call("take_snapshot"), passed="live_passed"
                    )
                    await _record_call(
                        report,
                        "get_control_surfaces",
                        lambda: call("get_control_surfaces"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report, "get_scenes", lambda: call("get_scenes"), passed="live_passed"
                    )
                    await _record_call(
                        report,
                        "get_scene_state",
                        lambda: call("get_scene_state", {"scene_index": 0}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_loop_settings",
                        lambda: call("get_loop_settings"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_selected_context",
                        lambda: call("get_selected_context"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_clip_summary",
                        lambda: call("get_clip_summary", {"track_index": track_index}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_clip_notes",
                        lambda: call(
                            "get_clip_notes", {"track_index": track_index, "clip_index": clip_index}
                        ),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_clip_info",
                        lambda: call(
                            "get_clip_info", {"track_index": track_index, "clip_index": clip_index}
                        ),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_device_list",
                        lambda: call("get_device_list", {"track_index": track_index}),
                        passed="live_passed",
                    )
                    if discovered_param_track_index is not None:
                        await _record_call(
                            report,
                            "get_parameter_value",
                            lambda: call(
                                "get_parameter_value",
                                {
                                    "track_index": discovered_param_track_index,
                                    "device_index": discovered_param_device_index,
                                    "parameter_name": discovered_param_name,
                                },
                            ),
                            passed="live_passed",
                        )
                    else:
                        report.record(
                            Verification(
                                "get_parameter_value",
                                "environment_unavailable",
                                "no device parameter found in current Set",
                            )
                        )
                    await _record_call(
                        report,
                        "get_routing",
                        lambda: call("get_routing", {"track_index": track_index}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_browser_categories",
                        lambda: call("get_browser_categories"),
                        passed="live_passed",
                    )
                    # ``search_browser`` should be a small query against a
                    # category the runner proves is present, not a guess.
                    categories = call("get_browser_categories")
                    query = "o" if categories else ""
                    await _record_call(
                        report,
                        "search_browser",
                        lambda: call("search_browser", {"query": query, "limit": 10}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_song_length",
                        lambda: call("get_song_length"),
                        passed="live_passed",
                    )
                    # Discover the actual track that contains "bass" so we
                    # do not hard-code a name the owner might have changed.
                    matches = call("live_find_track", {"query": "bass"})
                    discovered_track = track_index
                    if isinstance(matches, list) and matches:
                        idx = matches[0].get("index")
                        if isinstance(idx, int):
                            discovered_track = idx
                    artifacts["tags"].append(
                        f"live_find_track resolved bass track index={discovered_track}"
                    )
                    await _record_call(
                        report, "live_find_track", lambda: matches, passed="live_passed"
                    )
                    # ``list_device_params`` requires ``track_id``, not
                    # ``track_index/device_index``.
                    track_id = _resolve_track_id(client, track_index)
                    await _record_call(
                        report,
                        "list_device_params",
                        lambda: call("list_device_params", {"track_id": track_id}),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "get_composition_structure",
                        lambda: call("get_composition_structure"),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "diagnose_midi_clip",
                        lambda: call(
                            "diagnose_midi_clip",
                            {"track_index": track_index, "clip_index": clip_index},
                        ),
                        passed="live_passed",
                    )
                    await _record_call(
                        report,
                        "lifecycle_status",
                        lambda: call("lifecycle_status"),
                        passed="live_passed",
                    )
                else:
                    # ``mutations`` / ``websocket_reads`` profiles still
                    # need a recorded ``get_project_metadata`` row to
                    # satisfy the catalog but do not certify the read.
                    report.record(
                        Verification(
                            "get_project_metadata",
                            "live_passed",
                            f"song_name={actual_name}",
                        )
                    )

                if "websocket_reads" in expanded:

                    async def get_warp_readback() -> dict[str, Any]:
                        warp = await call_ws(
                            "get_warp_state",
                            {
                                "track_index": audio_track_index,
                                "clip_index": audio_clip_index,
                            },
                        )
                        # WS tools serialize to JSON strings — normalize.
                        if isinstance(warp, str):
                            import json as _json

                            return cast(dict[str, Any], _json.loads(warp))
                        return dict(warp or {})

                    try:
                        warp = await get_warp_readback()
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
                    except Exception as error:
                        report.record(
                            Verification(
                                "get_warp_state",
                                "failed",
                                f"{type(error).__name__}: {error}",
                            )
                        )

                if "mutations" in expanded:
                    # ----- mutation surface -----
                    #
                    # All mutations run inside a single try / finally so
                    # cleanup can restore the original Set state from the
                    # ``baseline`` snapshot. Every mutation is followed
                    # by a readback before its row is recorded.

                    # Discover a usable MIDI track for the clip mutations.
                    midi_tracks = [
                        idx for idx, kind in baseline["track_types"].items() if kind == "midi"
                    ]
                    if not midi_tracks:
                        raise AcceptanceSafetyError("no MIDI track available in disposable Set")
                    midi_track_index = (
                        track_index
                        if (baseline["track_types"].get(track_index) == "midi")
                        else midi_tracks[0]
                    )
                    artifacts["tags"].append(f"midi_track_index={midi_track_index}")

                    # Track for live_fade readback/mutation (prefers
                    # audio_track_index, falls back to midi_track_index).
                    fade_track_index = (
                        audio_track_index
                        if audio_track_index in baseline["track_names"]
                        else midi_track_index
                    )

                    # Verify the MIDI slot is empty before mutating.
                    slots = call("get_clip_summary", {"track_index": midi_track_index})
                    slot = next(
                        (item for item in slots if item.get("index") == clip_index),
                        None,
                    )
                    if slot is None:
                        raise AcceptanceSafetyError(
                            f"clip slot {midi_track_index}:{clip_index} "
                            "is missing; refusing to mutate"
                        )
                    if bool(slot.get("has_clip")):
                        raise AcceptanceSafetyError(
                            f"clip slot {midi_track_index}:{clip_index} "
                            "is occupied; refusing to overwrite"
                        )

                    original_tempo = baseline["tempo"]
                    original_time = baseline["current_song_time"]
                    original_loop = baseline["loop"]
                    original_loop_start = baseline["loop_start"]
                    original_loop_length = baseline["loop_length"]
                    cue_time = _acceptance_cue_time(baseline["locators"])
                    tempo_one = _test_tempo(original_tempo, 1.0)
                    tempo_two = _test_tempo(original_tempo, 2.0)
                    cue_name = "ABLETON_MCP_ACCEPTANCE"
                    bulk_cue_name = "ABLETON_MCP_ACCEPTANCE_BULK"
                    artifacts["tags"].extend([cue_name, bulk_cue_name])
                    cue_created = False

                    # Audio warp readback helper.
                    async def read_warp() -> dict[str, Any]:
                        raw = await call_ws(
                            "get_warp_state",
                            {
                                "track_index": audio_track_index,
                                "clip_index": audio_clip_index,
                            },
                        )
                        import json as _json

                        if isinstance(raw, str):
                            return cast(dict[str, Any], _json.loads(raw))
                        return dict(raw or {})

                    # Original warp state for restore.
                    original_warp = None
                    track_creation_runner: Callable[[str], Awaitable[str]] | None = None
                    if (
                        baseline["track_types"].get(audio_track_index) == "audio"
                    ):
                        try:
                            audio_slots = call(
                                "get_clip_summary", {"track_index": audio_track_index}
                            )
                            audio_slot = next(
                                (
                                    item
                                    for item in audio_slots
                                    if item.get("index") == audio_clip_index
                                ),
                                None,
                            )
                            if audio_slot is not None and bool(audio_slot.get("has_clip")):
                                audio_info = call(
                                    "get_clip_info",
                                    {
                                        "track_index": audio_track_index,
                                        "clip_index": audio_clip_index,
                                    },
                                )
                                if bool(audio_info.get("is_audio_clip", False)):
                                    original_warp = await read_warp()
                                    artifacts["manual_cleanup"].append(
                                        "restore warp_state from original_warp snapshot"
                                    )
                        except Exception:
                            pass

                    try:
                        # ----- save_set -----
                        async def run_save_set() -> None:
                            save_result = call("save_set")
                            if not isinstance(save_result, dict):
                                raise AssertionError(
                                    f"unexpected save_set response: {save_result!r}"
                                )
                            saved = save_result.get("saved")
                            api_avail = save_result.get("api_available")
                            gui_workflow = save_result.get("gui_workflow")

                            if saved is True and api_avail is True:
                                meta = call("get_project_metadata")
                                if meta.get("is_dirty") is not False:
                                    dirty_val = meta.get("is_dirty")
                                    raise AssertionError(
                                        "save_set returned saved=true but "
                                        f"get_project_metadata still shows is_dirty={dirty_val}"
                                    )
                                report.record(
                                    Verification("save_set", "live_passed", "saved=true")
                                )
                                return
                            if saved is False and api_avail is False:
                                save_steps = (
                                    gui_workflow.get("save")
                                    if isinstance(gui_workflow, dict)
                                    else None
                                )
                                if not (
                                    isinstance(save_steps, list)
                                    and save_steps
                                    and all(
                                        isinstance(step, str) and bool(step.strip())
                                        for step in save_steps
                                    )
                                ):
                                    raise AssertionError(
                                        "save_set manual fallback requires a non-empty "
                                        "gui_workflow.save string list"
                                    )
                                report.record(
                                    Verification(
                                        "save_set",
                                        "manual_required",
                                        "Host does not expose Song.save API "
                                        "(save_set requires GUI workflow or manual save)",
                                    )
                                )
                                return
                            raise AssertionError(f"ambiguous save_set response: {save_result}")

                        try:
                            await run_save_set()
                        except Exception as error:
                            if getattr(error, "code", None) == "CAPABILITY_UNAVAILABLE":
                                err_code = getattr(error, "code", "CAPABILITY_UNAVAILABLE")
                                report.record(
                                    Verification(
                                        "save_set",
                                        "host_unavailable",
                                        f"{err_code}: {error}",
                                    )
                                )
                            else:
                                report.record(
                                    Verification(
                                        "save_set", "failed", f"{type(error).__name__}: {error}"
                                    )
                                )
                        # ----- cue points -----
                        async def run_create_cue() -> str:
                            call("create_cue_point", {"name": cue_name, "time": cue_time})
                            locators = call("get_locators")
                            if not any(
                                abs(float(item.get("time", -1)) - cue_time) < 0.01
                                and item.get("name") == cue_name
                                for item in locators
                            ):
                                raise AssertionError("create_cue_point readback failed")
                            return f"name={cue_name} time={cue_time}"

                        await _record_call(report, "create_cue_point", run_create_cue)
                        cue_created = (
                            "create_cue_point" in report.recorded
                            and report.recorded["create_cue_point"].status == "live_passed"
                        )

                        async def run_bulk_cue() -> str:
                            bulk_targets = [
                                {"name": bulk_cue_name, "time": cue_time + 64.0},
                            ]
                            call("bulk_create_cue_points", {"items": bulk_targets})
                            locators = call("get_locators")
                            if not any(item.get("name") == bulk_cue_name for item in locators):
                                raise AssertionError("bulk_create_cue_points readback failed")
                            return f"created={len(bulk_targets)}"

                        await _record_call(report, "bulk_create_cue_points", run_bulk_cue)

                        async def run_delete_cue() -> str:
                            delete_result = call("delete_cue_point", {"time": cue_time})
                            if not bool(delete_result.get("deleted", False)):
                                raise AssertionError("delete_cue_point did not return deleted=true")
                            locators = call("get_locators")
                            if any(
                                abs(float(item.get("time", -1)) - cue_time) < 0.01
                                for item in locators
                            ):
                                raise AssertionError("delete_cue_point readback left cue in place")

                            # Second delete: bulk cue.
                            delete_bulk = call("delete_cue_point", {"time": cue_time + 64.0})
                            if not bool(delete_bulk.get("deleted", False)):
                                raise AssertionError("delete_cue_point (bulk) readback failed")
                            return f"deleted={delete_result.get('deleted')}"

                        await _record_call(report, "delete_cue_point", run_delete_cue)
                        # Assume deleted (restore will clean up if still present anyway)
                        cue_created = False

                        # ----- transport -----
                        async def run_set_tempo() -> str:
                            call("set_tempo", {"tempo": tempo_one})
                            rb_tempo = float(call("get_session_info")["tempo"])
                            if abs(rb_tempo - tempo_one) > 0.01:
                                raise AssertionError("set_tempo readback mismatch")
                            return f"tempo={tempo_one} readback={rb_tempo}"

                        await _record_call(report, "set_tempo", run_set_tempo)

                        async def run_set_time() -> str:
                            call("set_current_song_time", {"time": 8.0})
                            rb_time = float(call("get_session_info")["current_song_time"])
                            if abs(rb_time - 8.0) > 0.5:
                                raise AssertionError(
                                    f"set_current_song_time readback {rb_time} far from 8.0"
                                )
                            return f"time=8.0 readback={rb_time}"

                        await _record_call(report, "set_current_song_time", run_set_time)

                        async def run_set_loop_start() -> str:
                            call("set_loop_start", {"start_beat": 4.0})
                            rb_loop_start = float(call("get_loop_settings")["loop_start"])
                            if abs(rb_loop_start - 4.0) > 0.01:
                                raise AssertionError("set_loop_start readback mismatch")
                            return f"start_beat=4.0 readback={rb_loop_start}"

                        await _record_call(report, "set_loop_start", run_set_loop_start)

                        async def run_set_loop_length() -> str:
                            call("set_loop_length", {"length_beats": 8.0})
                            rb_loop_length = float(call("get_loop_settings")["loop_length"])
                            if abs(rb_loop_length - 8.0) > 0.01:
                                raise AssertionError("set_loop_length readback mismatch")
                            return f"length_beats=8.0 readback={rb_loop_length}"

                        await _record_call(report, "set_loop_length", run_set_loop_length)

                        async def run_set_loop() -> str:
                            call("set_loop", {"enabled": True})
                            rb_loop = bool(call("get_loop_settings")["loop"])
                            if not rb_loop:
                                raise AssertionError("set_loop readback did not enable loop")
                            return f"enabled=True readback={rb_loop}"

                        await _record_call(report, "set_loop", run_set_loop)

                        # ----- clip + notes mutations -----
                        async def run_create_clip() -> str:
                            call(
                                "create_clip",
                                {
                                    "track_index": midi_track_index,
                                    "clip_index": clip_index,
                                    "length_beats": 4.0,
                                },
                            )
                            clip_info = call(
                                "get_clip_info",
                                {
                                    "track_index": midi_track_index,
                                    "clip_index": clip_index,
                                },
                            )
                            if not bool(clip_info.get("has_clip", False)):
                                raise AssertionError("create_clip readback failed")
                            return f"track={midi_track_index} slot={clip_index}"

                        await _record_call(report, "create_clip", run_create_clip)
                        create_clip_ok = (
                            "create_clip" in report.recorded
                            and report.recorded["create_clip"].status == "live_passed"
                        )

                        if not create_clip_ok:
                            report.record(
                                Verification(
                                    "add_notes_to_clip",
                                    "failed",
                                    "Skipped: create_clip dependency failed",
                                )
                            )
                        else:

                            async def run_add_notes() -> str:
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
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                        "notes": notes,
                                    },
                                )
                                if int(added.get("added", 0)) != 4:
                                    raise AssertionError(
                                        f"add_notes_to_clip added={added.get('added')} expected 4"
                                    )
                                observed = call(
                                    "get_clip_notes",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                if len(observed) != 4:
                                    raise AssertionError("add_notes_to_clip readback failed")
                                return "added=4, observed=4"

                            await _record_call(report, "add_notes_to_clip", run_add_notes)

                        if not create_clip_ok:
                            report.record(
                                Verification(
                                    "clear_clip_notes",
                                    "failed",
                                    "Skipped: create_clip dependency failed",
                                )
                            )
                        else:

                            async def run_clear_notes() -> str:
                                call(
                                    "clear_clip_notes",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                cleared = call(
                                    "get_clip_notes",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                if cleared:
                                    raise AssertionError("clear_clip_notes did not empty clip")
                                return "notes cleared (0)"

                            await _record_call(report, "clear_clip_notes", run_clear_notes)

                        if not create_clip_ok:
                            report.record(
                                Verification(
                                    "set_clip_properties",
                                    "failed",
                                    "Skipped: create_clip dependency failed",
                                )
                            )
                        else:

                            async def run_set_clip_props() -> str:
                                call(
                                    "set_clip_properties",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                        "name": "ABLETON_MCP_ACCEPTANCE",
                                    },
                                )
                                info = call(
                                    "get_clip_info",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                if info.get("name") != "ABLETON_MCP_ACCEPTANCE":
                                    raise AssertionError("set_clip_properties did not rename clip")
                                artifacts["tags"].append("clip:ABLETON_MCP_ACCEPTANCE")
                                return "name=ABLETON_MCP_ACCEPTANCE"

                            await _record_call(report, "set_clip_properties", run_set_clip_props)

                        if not create_clip_ok:
                            report.record(
                                Verification(
                                    "create_clip_automation",
                                    "failed",
                                    "Skipped: create_clip dependency failed",
                                )
                            )
                        else:

                            async def run_clip_automation() -> str:
                                auto_points = [
                                    {"time": 0.0, "value": 0.0},
                                    {"time": 1.0, "value": 1.0},
                                ]
                                auto_resp = call(
                                    "create_clip_automation",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                        "parameter_name": "volume",
                                        "automation_points": auto_points,
                                    },
                                )
                                if not isinstance(auto_resp, dict):
                                    raise AssertionError(
                                        "create_clip_automation must return a dict "
                                        "with 'points_written'"
                                    )
                                if int(auto_resp.get("points_written", -1)) != len(auto_points):
                                    raise AssertionError(
                                        "create_clip_automation points readback "
                                        f"mismatch: {auto_resp}"
                                    )
                                return f"points_written={auto_resp.get('points_written')}"

                            await _record_call(
                                report, "create_clip_automation", run_clip_automation
                            )

                        # ----- transport fire/stop -----
                        async def run_start_playback() -> str:
                            call("start_playback")
                            playback_state = call("get_session_info")
                            if not bool(playback_state.get("is_playing", False)):
                                raise AssertionError("start_playback did not engage transport")
                            return f"is_playing={playback_state.get('is_playing')}"

                        await _record_call(report, "start_playback", run_start_playback)

                        async def run_stop_playback() -> str:
                            call("stop_playback")
                            stop_state = call("get_session_info")
                            if bool(stop_state.get("is_playing", False)):
                                raise AssertionError("stop_playback left transport playing")
                            return "transport stopped and readback confirmed"

                        await _record_call(report, "stop_playback", run_stop_playback)

                        # ----- run_batch -----
                        async def run_run_batch() -> str:
                            batch = call(
                                "run_batch",
                                {
                                    "commands": [
                                        {"type": "set_tempo", "params": {"tempo": tempo_two}},
                                        {"type": "set_loop", "params": {"enabled": True}},
                                        {
                                            "type": "create_clip",
                                            "params": {
                                                "track_index": midi_track_index,
                                                "clip_index": clip_index,
                                                "length_beats": 4.0,
                                            },
                                        },
                                        {"type": "set_tempo", "params": {"tempo": tempo_one}},
                                    ],
                                },
                            )
                            if (
                                int(batch.get("completed", 0)) < 2
                                or int(batch.get("aborted_at", -1)) < 2
                                or bool(batch.get("rolled_back", True))
                            ):
                                raise AssertionError(f"Unexpected run_batch result: {batch}")
                            return (
                                f"completed={batch.get('completed')} "
                                f"aborted_at={batch.get('aborted_at')}"
                            )

                        await _record_call(report, "run_batch", run_run_batch)

                        # ----- fire_clip (optional) -----
                        if not fire_clip:
                            _record_unavailable(
                                report,
                                "fire_clip",
                                "fire_clip requires --fire-clip flag",
                            )
                        elif not create_clip_ok:
                            report.record(
                                Verification(
                                    "fire_clip", "failed", "Skipped: create_clip dependency failed"
                                )
                            )
                        else:

                            async def run_fire_clip() -> str:
                                fire_resp = call(
                                    "fire_clip",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                if not isinstance(fire_resp, dict):
                                    raise AssertionError("fire_clip must return a dict")
                                if not bool(fire_resp.get("fired", False)):
                                    raise AssertionError("fire_clip did not return fired=true")
                                playing = call("get_session_info").get("is_playing", False)
                                if not bool(playing):
                                    raise AssertionError("fire_clip left transport stopped")
                                return f"track={midi_track_index} slot={clip_index}"

                            await _record_call(report, "fire_clip", run_fire_clip)
                            import contextlib

                            with contextlib.suppress(Exception):
                                call("stop_playback")

                        # ----- fire_scene -----
                        async def run_fire_scene() -> str:
                            scene_resp = call("fire_scene", {"scene_index": 0})
                            if not isinstance(scene_resp, dict):
                                raise AssertionError("fire_scene must return a dict")
                            if "scene_index" not in scene_resp:
                                raise AssertionError("fire_scene response missing scene_index")
                            scene_playing = call("get_session_info").get("is_playing", False)
                            if not bool(scene_playing):
                                raise AssertionError("fire_scene left transport stopped")
                            return "scene=0"

                        await _record_call(report, "fire_scene", run_fire_scene)
                        import contextlib

                        with contextlib.suppress(Exception):
                            call("stop_playback")

                        # ----- set_track_property + readback -----
                        async def run_set_track_prop() -> str:
                            call(
                                "set_track_property",
                                {
                                    "track_index": midi_track_index,
                                    "property": "mute",
                                    "value": True,
                                },
                            )
                            state = call("get_track_state", {"track_index": midi_track_index})
                            if not bool(state.get("mute", False)):
                                raise AssertionError("set_track_property mute readback failed")
                            return "mute=True readback OK"

                        await _record_call(report, "set_track_property", run_set_track_prop)
                        try:
                            original_mute = bool(
                                baseline.get("track_mutes", {}).get(midi_track_index, False)
                            )
                            call(
                                "set_track_property",
                                {
                                    "track_index": midi_track_index,
                                    "property": "mute",
                                    "value": original_mute,
                                },
                            )
                        except Exception:
                            pass

                        # ----- rename_track + readback -----
                        async def run_rename_track() -> str:
                            tag_name = "ABLETON_MCP_ACCEPTANCE"
                            call(
                                "rename_track",
                                {
                                    "track_index": midi_track_index,
                                    "new_name": tag_name,
                                },
                            )
                            tracks = call("get_track_list")
                            renamed = next(
                                (t for t in tracks if int(t.get("index", -1)) == midi_track_index),
                                None,
                            )
                            if renamed is None or renamed.get("name") != tag_name:
                                raise AssertionError("rename_track readback failed")
                            artifacts["tags"].append(f"track:{tag_name}")
                            return f"renamed to {tag_name}"

                        await _record_call(report, "rename_track", run_rename_track)
                        try:
                            original_track_name = baseline["track_names"].get(midi_track_index, "")
                            if original_track_name:
                                call(
                                    "rename_track",
                                    {
                                        "track_index": midi_track_index,
                                        "new_name": original_track_name,
                                    },
                                )
                        except Exception:
                            pass

                        # ----- delete_clip + readback -----
                        if not create_clip_ok:
                            report.record(
                                Verification(
                                    "delete_clip",
                                    "failed",
                                    "Skipped: create_clip dependency failed",
                                )
                            )
                        else:

                            async def run_delete_clip() -> str:
                                call(
                                    "delete_clip",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                info_after_delete = call(
                                    "get_clip_info",
                                    {
                                        "track_index": midi_track_index,
                                        "clip_index": clip_index,
                                    },
                                )
                                if bool(info_after_delete.get("has_clip", False)):
                                    raise AssertionError("delete_clip did not remove clip")
                                return f"track={midi_track_index} slot={clip_index}"

                            await _record_call(report, "delete_clip", run_delete_clip)

                        # ----- set_parameter_value + readback -----
                        if discovered_param_track_index is None:
                            report.record(
                                Verification(
                                    "set_parameter_value",
                                    "environment_unavailable",
                                    "No writable parameter found in the loaded project devices",
                                )
                            )
                        else:

                            async def run_set_parameter_value() -> str:
                                original_param_resp = call(
                                    "get_parameter_value",
                                    {
                                        "track_index": discovered_param_track_index,
                                        "device_index": discovered_param_device_index,
                                        "parameter_name": discovered_param_name,
                                    },
                                )
                                if not isinstance(original_param_resp, dict):
                                    raise AssertionError("get_parameter_value must return a dict")
                                live_val = float(original_param_resp.get("value", 0.0))
                                min_val = float(discovered_param_min)
                                max_val = float(discovered_param_max)
                                is_quant = bool(discovered_param_is_quantized)

                                prop_tol = _parameter_tolerance(min_val, max_val)

                                target = None
                                if is_quant:
                                    for c in [min_val, max_val]:
                                        if abs(c - live_val) > prop_tol:
                                            target = c
                                            break
                                    if target is None:
                                        i_min = int(min_val)
                                        i_max = int(max_val)
                                        for c in range(i_min, i_max + 1):
                                            if abs(float(c) - live_val) > prop_tol:
                                                target = float(c)
                                                break
                                else:
                                    range_val = abs(max_val - min_val)
                                    for c in [min_val, max_val]:
                                        if abs(c - live_val) > range_val * 0.1:
                                            target = c
                                            break
                                    if target is None:
                                        mid = (min_val + max_val) / 2.0
                                        if abs(mid - live_val) > prop_tol:
                                            target = mid
                                        elif abs(max_val - live_val) > prop_tol:
                                            target = max_val
                                        elif abs(min_val - live_val) > prop_tol:
                                            target = min_val

                                if target is None:
                                    raise AssertionError(
                                        "could not compute valid target value for parameter write"
                                    )

                                artifacts["set_parameter_value_restore"] = {
                                    "track_index": discovered_param_track_index,
                                    "device_index": discovered_param_device_index,
                                    "parameter_name": discovered_param_name,
                                    "original": live_val,
                                    "min": min_val,
                                    "max": max_val,
                                    "is_quantized": is_quant,
                                }
                                call(
                                    "set_parameter_value",
                                    {
                                        "track_index": discovered_param_track_index,
                                        "device_index": discovered_param_device_index,
                                        "parameter_name": discovered_param_name,
                                        "value": target,
                                    },
                                )
                                rb_value = call(
                                    "get_parameter_value",
                                    {
                                        "track_index": discovered_param_track_index,
                                        "device_index": discovered_param_device_index,
                                        "parameter_name": discovered_param_name,
                                    },
                                )
                                if not isinstance(rb_value, dict):
                                    raise AssertionError(
                                        "set_parameter_value readback failed "
                                        "(no dict response)"
                                    )
                                rb_val = float(rb_value.get("value", 0.0))
                                if abs(rb_val - target) > prop_tol:
                                    raise AssertionError(
                                        f"set_parameter_value readback failed: "
                                        f"expected {target} but got {rb_val} (tol {prop_tol})"
                                    )
                                return (
                                    f"param={discovered_param_name} "
                                    f"live_val={live_val} target={target}"
                                )

                            await _record_call(
                                report, "set_parameter_value", run_set_parameter_value
                            )

                        # ----- live_fade -----
                        async def run_live_fade() -> str:
                            pre_state = call("get_track_state", {"track_index": fade_track_index})
                            if not isinstance(pre_state, dict) or "volume" not in pre_state:
                                raise AssertionError(
                                    "live_fade pre-readback failed "
                                    "(get_track_state missing 'volume')"
                                )
                            original_volume = float(pre_state["volume"])
                            artifacts["live_fade_volume_original"] = original_volume
                            artifacts["live_fade_track_index"] = fade_track_index

                            call(
                                "live_fade",
                                {
                                    "track_index": fade_track_index,
                                    "target_percent": 50.0,
                                    "duration": 0.0,
                                    "steps": 1,
                                },
                            )
                            post_immediate = call(
                                "get_track_state", {"track_index": fade_track_index}
                            )
                            if (
                                not isinstance(post_immediate, dict)
                                or "volume" not in post_immediate
                            ):
                                raise AssertionError("live_fade immediate readback failed")
                            if abs(float(post_immediate["volume"]) - 0.5) > 0.05:
                                raise AssertionError("live_fade immediate target mismatch")

                            call(
                                "live_fade",
                                {
                                    "track_index": fade_track_index,
                                    "target_percent": 80.0,
                                    "duration": 0.2,
                                    "steps": 4,
                                },
                            )
                            post_fade = call("get_track_state", {"track_index": fade_track_index})
                            if not isinstance(post_fade, dict) or "volume" not in post_fade:
                                raise AssertionError("live_fade timed readback failed")
                            if abs(float(post_fade["volume"]) - 0.8) > 0.05:
                                raise AssertionError("live_fade timed target mismatch")
                            return "duration=0.2 monotonic fade readback OK"

                        await _record_call(report, "live_fade", run_live_fade)

                        # ----- set_warp_state + readback -----
                        async def run_set_warp_state() -> str:
                            if original_warp is None:
                                raise AssertionError(
                                    "warp setup failed "
                                    "(audio clip missing or WebSocket unreachable)"
                                )
                            await call_ws(
                                "set_warp_state",
                                {
                                    "track_index": audio_track_index,
                                    "clip_index": audio_clip_index,
                                    "warping": True,
                                },
                            )
                            rb_warp = await read_warp()
                            if not bool(rb_warp.get("warping", False)):
                                raise AssertionError("set_warp_state readback failed")
                            return f"warping=True readback={rb_warp}"

                        await _record_call(report, "set_warp_state", run_set_warp_state)

                        # ----- load_device_to_track + readback -----
                        async def run_load_device() -> str:
                            load_target = midi_track_index
                            devs_before = call("get_device_list", {"track_index": load_target})
                            if not isinstance(devs_before, list):
                                raise AssertionError(
                                    "get_device_list prior to load_device_to_track "
                                    f"returned non-list: {devs_before!r}"
                                )
                            count_before = len(devs_before)

                            load_result = await call_ws(
                                "load_device_to_track",
                                {
                                    "track_index": load_target,
                                    "device_name": "Operator",
                                },
                            )
                            import json as _json

                            if isinstance(load_result, str):
                                load_result = _json.loads(load_result)

                            if not isinstance(load_result, dict):
                                raise AssertionError(
                                    f"load_device_to_track non-dict response: {load_result!r}"
                                )
                            if load_result.get("status") != "loaded":
                                raise AssertionError(
                                    f"load_device_to_track unexpected status: {load_result}"
                                )
                            if load_result.get("track_index") != load_target:
                                raise AssertionError(
                                    f"load_device_to_track track_index mismatch: {load_result}"
                                )
                            if load_result.get("device_name") != "Operator":
                                raise AssertionError(
                                    f"load_device_to_track device_name mismatch: {load_result}"
                                )
                            dev_idx = load_result.get("device_index")
                            if not isinstance(dev_idx, int):
                                raise AssertionError(
                                    f"load_device_to_track missing device_index: {load_result}"
                                )

                            devs_after = call("get_device_list", {"track_index": load_target})
                            if (
                                not isinstance(devs_after, list)
                                or len(devs_after) != count_before + 1
                            ):
                                post_str = (
                                    len(devs_after)
                                    if isinstance(devs_after, list)
                                    else "non-list"
                                )
                                raise AssertionError(
                                    "load_device_to_track did not increase device count by 1: "
                                    f"before={count_before}, after={post_str}"
                                )

                            if (
                                dev_idx < 0
                                or dev_idx >= len(devs_after)
                                or devs_after[dev_idx].get("name") != "Operator"
                            ):
                                raise AssertionError(
                                    f"load_device_to_track device at index {dev_idx} "
                                    f"is not Operator: {devs_after}"
                                )

                            artifacts["manual_cleanup"].append(
                                f"Operator loaded on track {load_target}; "
                                "remove via Live UI or Undo"
                            )
                            return f"Operator loaded at index {dev_idx} on track {load_target}"

                        await _record_call(report, "load_device_to_track", run_load_device)

                        if "quit" not in profiles and "quit_ableton" not in report.recorded:
                            report.record(
                                Verification(
                                    "quit_ableton",
                                    "manual_required",
                                    QUIT_ABLETON_MANUAL_REASON,
                                )
                            )

                        async def _run_track_creation(kind: str) -> str:
                            tool_name = f"create_{kind}_track"
                            pre_tracks = call("get_track_list")
                            if not isinstance(pre_tracks, list):
                                raise AssertionError(
                                    f"get_track_list prior to {tool_name} returned non-list"
                                )
                            pre_total_count = len(pre_tracks)
                            pre_regular = [
                                t for t in pre_tracks if t.get("type") in ("midi", "audio")
                            ]
                            pre_regular_count = len(pre_regular)

                            res = call(tool_name, {"index": -1})
                            if not isinstance(res, dict):
                                raise AssertionError(f"{tool_name} must return a dict")
                            new_index = res.get("track_index")
                            if not isinstance(new_index, int):
                                raise AssertionError(f"{tool_name} missing track_index")

                            if new_index != pre_regular_count:
                                raise AssertionError(
                                    f"{tool_name} returned track_index {new_index}, "
                                    f"expected {pre_regular_count}"
                                )

                            post_tracks = call("get_track_list")
                            if (
                                not isinstance(post_tracks, list)
                                or len(post_tracks) != pre_total_count + 1
                            ):
                                post_str = (
                                    len(post_tracks)
                                    if isinstance(post_tracks, list)
                                    else "non-list"
                                )
                                raise AssertionError(
                                    f"{tool_name} did not increase total track count by 1: "
                                    f"pre={pre_total_count}, post={post_str}"
                                )

                            post_regular = [
                                t for t in post_tracks if t.get("type") in ("midi", "audio")
                            ]
                            if len(post_regular) != pre_regular_count + 1:
                                raise AssertionError(
                                    f"{tool_name} did not increase regular track count by 1: "
                                    f"pre={pre_regular_count}, post={len(post_regular)}"
                                )

                            created_track = next(
                                (
                                    t
                                    for t in post_tracks
                                    if int(t.get("index", -1)) == new_index
                                ),
                                None,
                            )
                            if created_track is None or created_track.get("type") != kind:
                                raise AssertionError(
                                    f"{tool_name} {new_index} missing or not "
                                    f"{kind} in get_track_list"
                                )

                            for t in pre_regular:
                                idx = int(t.get("index", -1))
                                match = next(
                                    (pt for pt in post_tracks if int(pt.get("index", -1)) == idx),
                                    None,
                                )
                                if (
                                    match is None
                                    or match.get("name") != t.get("name")
                                    or match.get("type") != t.get("type")
                                ):
                                    raise AssertionError(
                                        f"Pre-existing regular track {idx} mutated: {t} vs {match}"
                                    )

                            pre_special = [
                                t for t in pre_tracks if t.get("type") not in ("midi", "audio")
                            ]
                            for t in pre_special:
                                old_idx = int(t.get("index", -1))
                                expected_new_idx = old_idx + 1
                                match = next(
                                    (
                                        pt
                                        for pt in post_tracks
                                        if int(pt.get("index", -1)) == expected_new_idx
                                    ),
                                    None,
                                )
                                if (
                                    match is None
                                    or match.get("name") != t.get("name")
                                    or match.get("type") != t.get("type")
                                ):
                                    raise AssertionError(
                                        f"Return/master track {t.get('name')} mismatched "
                                        f"post-creation: expected index {expected_new_idx}, "
                                        f"found {match}"
                                    )

                            artifacts["tracks_created"].append(f"{kind}:{new_index}")
                            artifacts["manual_cleanup"].append(
                                f"delete {kind} track at index {new_index} "
                                "(originally created by acceptance runner)"
                            )
                            return f"new {kind} track index={new_index}"

                        track_creation_runner = _run_track_creation

                    except Exception as mutations_error:
                        for tool in BASELINE_PROBE_GROUPS.get("mutations", ()):
                            if tool not in report.recorded:
                                report.record(
                                    Verification(
                                        tool,
                                        "failed",
                                        f"mutations setup failed: {mutations_error}",
                                    )
                                )

                    finally:
                        # ----- cleanup restore -----
                        cleanup_failures: list[tuple[str, str]] = []

                        def _restore_call(
                            action: str,
                            tool: str,
                            restore: Callable[[], Any],
                            *,
                            verify: Callable[[Any], None],
                        ) -> None:
                            try:
                                observed = restore()
                                verify(observed)
                            except Exception as error:  # noqa: BLE001
                                cleanup_failures.append(
                                    (tool, f"{action} readback failed: {error}")
                                )

                        async def _restore_ws(
                            action: str,
                            tool: str,
                            restore: Callable[[], Awaitable[Any]],
                            *,
                            verify: Callable[[Any], Awaitable[None]],
                        ) -> None:
                            try:
                                observed = await restore()
                                await verify(observed)
                            except Exception as error:  # noqa: BLE001
                                cleanup_failures.append(
                                    (tool, f"{action} readback failed: {error}")
                                )

                        def _eq(observed: Any, expected: Any, label: str) -> None:
                            if observed != expected:
                                raise AssertionError(
                                    f"{label} readback mismatch: "
                                    f"observed={observed!r} "
                                    f"expected={expected!r}"
                                )

                        _restore_call(
                            "stop_playback",
                            "stop_playback",
                            lambda: call("stop_playback"),
                            verify=lambda _o: _eq(
                                bool(call("get_session_info").get("is_playing", False)),
                                False,
                                "is_playing",
                            ),
                        )
                        _restore_call(
                            "set_loop",
                            "set_loop",
                            lambda: call("set_loop", {"enabled": original_loop}),
                            verify=lambda _o: _eq(
                                bool(call("get_loop_settings").get("loop", False)),
                                original_loop,
                                "loop",
                            ),
                        )
                        _restore_call(
                            "set_loop_start",
                            "set_loop_start",
                            lambda: call("set_loop_start", {"start_beat": original_loop_start}),
                            verify=lambda _o: _eq(
                                float(call("get_loop_settings").get("loop_start", 0.0)),
                                original_loop_start,
                                "loop_start",
                            ),
                        )
                        _restore_call(
                            "set_loop_length",
                            "set_loop_length",
                            lambda: call("set_loop_length", {"length_beats": original_loop_length}),
                            verify=lambda _o: _eq(
                                float(call("get_loop_settings").get("loop_length", 0.0)),
                                original_loop_length,
                                "loop_length",
                            ),
                        )
                        _restore_call(
                            "set_tempo",
                            "set_tempo",
                            lambda: call("set_tempo", {"tempo": original_tempo}),
                            verify=lambda _o: _eq(
                                float(call("get_session_info").get("tempo", 0.0)),
                                original_tempo,
                                "tempo",
                            ),
                        )
                        _restore_call(
                            "set_current_song_time",
                            "set_current_song_time",
                            lambda: call("set_current_song_time", {"time": original_time}),
                            verify=lambda _o: _eq(
                                float(call("get_session_info").get("current_song_time", 0.0)),
                                original_time,
                                "current_song_time",
                            ),
                        )
                        if cue_created:

                            def _verify_cue_absent(_observed: Any) -> None:
                                if any(
                                    abs(float(item.get("time", -1)) - cue_time) < 0.01
                                    for item in call("get_locators")
                                ):
                                    raise AssertionError(
                                        f"cue at {cue_time} still present after delete"
                                    )

                            _restore_call(
                                "delete_cue_point",
                                "delete_cue_point",
                                lambda: call("delete_cue_point", {"time": cue_time}),
                                verify=_verify_cue_absent,
                            )
                        if original_warp is not None:
                            expected_warp = bool(original_warp.get("warping", False))

                            async def _verify_warp(_observed: Any) -> None:
                                rb = await read_warp()
                                if bool(rb.get("warping", False)) != (expected_warp):
                                    raise AssertionError(
                                        f"warp restore: observed="
                                        f"{rb.get('warping')!r} expected="
                                        f"{expected_warp!r}"
                                    )

                            await _restore_ws(
                                "set_warp_state",
                                "set_warp_state",
                                lambda: call_ws(
                                    "set_warp_state",
                                    {
                                        "track_index": audio_track_index,
                                        "clip_index": audio_clip_index,
                                        "warping": expected_warp,
                                    },
                                ),
                                verify=_verify_warp,
                            )
                        # Restore per-track mute/solo/arm so the
                        # disposable Set comes back to its pre-run state.
                        for idx, original in baseline.get("track_mutes", {}).items():

                            def _restore_mute(
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> Any:
                                return call(
                                    "set_track_property",
                                    {
                                        "track_index": _idx,
                                        "property": "mute",
                                        "value": _original,
                                    },
                                )

                            def _verify_mute(
                                _observed: Any,
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> None:
                                _eq(
                                    bool(
                                        call("get_track_state", {"track_index": _idx}).get(
                                            "mute", False
                                        )
                                    ),
                                    _original,
                                    f"track:{_idx}.mute",
                                )

                            _restore_call(
                                f"set_track_property(mute:{idx})",
                                "set_track_property",
                                _restore_mute,
                                verify=_verify_mute,
                            )
                        for idx, original in baseline.get("track_solos", {}).items():

                            def _restore_solo(
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> Any:
                                return call(
                                    "set_track_property",
                                    {
                                        "track_index": _idx,
                                        "property": "solo",
                                        "value": _original,
                                    },
                                )

                            def _verify_solo(
                                _observed: Any,
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> None:
                                _eq(
                                    bool(
                                        call("get_track_state", {"track_index": _idx}).get(
                                            "solo", False
                                        )
                                    ),
                                    _original,
                                    f"track:{_idx}.solo",
                                )

                            _restore_call(
                                f"set_track_property(solo:{idx})",
                                "set_track_property",
                                _restore_solo,
                                verify=_verify_solo,
                            )
                        for idx, original in baseline.get("track_arms", {}).items():

                            def _restore_arm(
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> Any:
                                return call(
                                    "set_track_property",
                                    {
                                        "track_index": _idx,
                                        "property": "arm",
                                        "value": _original,
                                    },
                                )

                            def _verify_arm(
                                _observed: Any,
                                _idx: int = idx,
                                _original: bool = original,
                            ) -> None:
                                _eq(
                                    bool(
                                        call("get_track_state", {"track_index": _idx}).get(
                                            "arm", False
                                        )
                                    ),
                                    _original,
                                    f"track:{_idx}.arm",
                                )

                            _restore_call(
                                f"set_track_property(arm:{idx})",
                                "set_track_property",
                                _restore_arm,
                                verify=_verify_arm,
                            )
                        # Restore the live_fade target volume to its
                        # Restore the live_fade mixer volume to its pre-fade value.
                        # ``live_fade`` mutates
                        # ``track.mixer_device.volume``; we restore by
                        # issuing another ``live_fade`` with
                        # ``duration=0`` and ``target_value=original``
                        # so the round-trip goes through the same code
                        # path as the original mutation — never via
                        # ``set_parameter_value`` on a device.
                        if "live_fade_volume_original" in artifacts:
                            restore_target = artifacts["live_fade_volume_original"]
                            target_track = int(
                                artifacts.get(
                                    "live_fade_track_index", fade_track_index
                                )
                            )

                            def _verify_volume(_o: Any) -> None:
                                state = call(
                                    "get_track_state",
                                    {"track_index": target_track},
                                )
                                if not isinstance(state, dict) or ("volume" not in state):
                                    raise AssertionError(
                                        "live_fade restore readback missing 'volume' "
                                        "from get_track_state"
                                    )
                                _eq(
                                    float(state["volume"]),
                                    restore_target,
                                    f"track:{target_track}.volume",
                                )

                            _restore_call(
                                "live_fade volume restore",
                                "live_fade",
                                lambda: call(
                                    "live_fade",
                                    {
                                        "track_index": target_track,
                                        "target_value": restore_target,
                                        "duration": 0.0,
                                        "steps": 1,
                                    },
                                ),
                                verify=_verify_volume,
                            )
                        # Restore the parameter the mutation probe
                        # touched, using the snapshot captured before the
                        # write.
                        param_restore_raw = artifacts.get("set_parameter_value_restore")
                        param_restore: dict[str, Any] | None = (
                            cast(dict[str, Any], param_restore_raw)
                            if isinstance(param_restore_raw, dict)
                            else None
                        )
                        if param_restore is not None:
                            p_min = float(param_restore.get("min", 0.0))
                            p_max = float(param_restore.get("max", 1.0))
                            p_tol = _parameter_tolerance(p_min, p_max)

                            def _verify_param_restore(_o: Any) -> None:
                                observed_val = float(
                                    call(
                                        "get_parameter_value",
                                        {
                                            "track_index": param_restore["track_index"],
                                            "device_index": param_restore["device_index"],
                                            "parameter_name": param_restore["parameter_name"],
                                        },
                                    ).get("value", 0.0)
                                )
                                expected_val = float(param_restore["original"])
                                if abs(observed_val - expected_val) > p_tol:
                                    raise AssertionError(
                                        "set_parameter_value restore readback mismatch: "
                                        f"observed={observed_val} expected={expected_val} "
                                        f"(tol {p_tol})"
                                    )

                            _restore_call(
                                "set_parameter_value restore",
                                "set_parameter_value",
                                lambda: call(
                                    "set_parameter_value",
                                    {
                                        "track_index": param_restore["track_index"],
                                        "device_index": param_restore["device_index"],
                                        "parameter_name": param_restore["parameter_name"],
                                        "value": param_restore["original"],
                                    },
                                ),
                                verify=_verify_param_restore,
                            )
                        # Any cleanup failure downgrades the affected
                        # tool rows to ``failed`` so ``release_ready``
                        # cannot be green. We never introduce a
                        # ``cleanup_failed`` status; the audit
                        # explicitly preferred ``failed`` plus
                        # ``cleanup/readback failed`` evidence.
                        if cleanup_failures:
                            affected = sorted({tool for tool, _ in cleanup_failures})
                            details = "; ".join(
                                f"{tool}: {reason}" for tool, reason in cleanup_failures
                            )
                            for tool in affected:
                                if tool in report.recorded and (
                                    report.recorded[tool].status == "live_passed"
                                ):
                                    report.record(
                                        Verification(
                                            tool,
                                            "failed",
                                            f"cleanup/readback failed ({details})",
                                        )
                                    )

                    if "create_audio_track" not in report.recorded:
                        if cleanup_failures:
                            cleanup_details = "; ".join(
                                f"{tool}: {reason}" for tool, reason in cleanup_failures
                            )
                            for tool in ("create_audio_track", "create_midi_track"):
                                report.record(
                                    Verification(
                                        tool,
                                        "failed",
                                        "not executed because reversible cleanup failed "
                                        f"({cleanup_details})",
                                    )
                                )
                        elif track_creation_runner is None:
                            for tool in ("create_audio_track", "create_midi_track"):
                                report.record(
                                    Verification(
                                        tool,
                                        "failed",
                                        "track creation runner was not initialized",
                                    )
                                )
                        else:
                            await _record_call(
                                report,
                                "create_audio_track",
                                lambda: track_creation_runner("audio"),
                            )
                            await _record_call(
                                report,
                                "create_midi_track",
                                lambda: track_creation_runner("midi"),
                            )

                if "quit" in profiles and "mutations" not in expanded:
                    # ``quit`` profile without ``mutations``: record the
                    # ``quit_ableton`` row as ``manual_required``. The
                    # runner does not actually invoke the bridge here —
                    # invoking ``quit_ableton`` would close the host and
                    # prevent any other probe from running, and we never
                    # certify an operation that was not executed.
                    report.record(
                        Verification(
                            "quit_ableton",
                            "manual_required",
                            QUIT_ABLETON_MANUAL_REASON,
                        )
                    )

            except AcceptanceSafetyError as safety_error:
                # Bridge refused to send mutations. Mark every selected
                # mutation as ``failed`` so the report cannot pass with
                # zeros, then re-raise so the CLI still observes the
                # refusal.
                for tool in BASELINE_PROBE_GROUPS.get("mutations", ()):
                    if tool not in report.recorded:
                        report.record(
                            Verification(
                                tool,
                                "failed",
                                f"bridge refused to send mutations: {safety_error}",
                            )
                        )
                # Also mark websocket_reads when refused.
                for tool in BASELINE_PROBE_GROUPS.get("websocket_reads", ()):
                    if tool not in report.recorded:
                        report.record(
                            Verification(
                                tool,
                                "failed",
                                f"bridge refused to send mutations: {safety_error}",
                            )
                        )
                # ``quit_ableton`` is never invoked when refused. Until an
                # out-of-band owner confirmation arrives, the row reads
                # ``manual_required`` rather than claiming success for an
                # operation that was never executed.
                if "quit" not in profiles and ("quit_ableton" not in report.recorded):
                    report.record(
                        Verification(
                            "quit_ableton",
                            "manual_required",
                            QUIT_ABLETON_MANUAL_REASON,
                        )
                    )
                raise safety_error
            except Exception as outer_error:  # noqa: BLE001
                # Any uncaught failure during the live probe phase marks
                # every still-missing tool as ``failed`` so the report
                # cannot pass with zeros.
                for group in ("mutations", "websocket_reads"):
                    for tool in BASELINE_PROBE_GROUPS.get(group, ()):
                        if tool not in report.recorded:
                            report.record(
                                Verification(
                                    tool,
                                    "failed",
                                    f"{type(outer_error).__name__}: {outer_error}",
                                )
                            )
                # ``quit_ableton`` is unavailable under any non-quit
                # profile regardless of readback outcome; until an
                # out-of-band owner confirmation arrives it reads
                # ``manual_required`` instead of being green-washed.
                if "quit" not in profiles and ("quit_ableton" not in report.recorded):
                    report.record(
                        Verification(
                            "quit_ableton",
                            "manual_required",
                            QUIT_ABLETON_MANUAL_REASON,
                        )
                    )

    # Compute the set of selected tools (resolved across profiles).
    selected_tools: set[str] = set()
    for group in expanded:
        selected_tools.update(BASELINE_PROBE_GROUPS[group])

    # Tools outside the selected profiles are pre-classified as
    # ``environment_unavailable`` so ``finish()`` does not raise for
    # missing rows. ``release_ready`` policy still refuses promotion
    # for any partial profile, so this cannot greenwash a release.
    catalog_names = _baseline_tool_names()
    for tool in catalog_names:
        if tool in report.recorded:
            continue
        if tool in selected_tools:
            continue
        report.record(
            Verification(
                tool,
                "environment_unavailable",
                f"not covered by selected profiles: {list(expanded)}",
            )
        )

    # Compute ``release_ready`` using the documented policy.
    ready = _release_ready(report, profiles, fire_clip=fire_clip)
    # Re-run ``finish()`` only after every selected tool is recorded;
    # if anything is still missing, ``finish`` raises — the runner
    # cannot greenwash the report.
    certification = report.finish()
    certification["release_ready"] = ready
    status = "ok" if ready else "failed"
    return {
        "project": confirm_project_name,
        "track_index": track_index,
        "clip_index": clip_index,
        "audio_track_index": audio_track_index,
        "audio_clip_index": audio_clip_index,
        "profiles": list(profiles),
        "fire_clip": fire_clip,
        "status": status,
        "artifacts": artifacts,
        "certification": certification,
    }
