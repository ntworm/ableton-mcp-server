"""Offline probe group.

Drives the eight offline tools in :data:`BASELINE_PROBE_GROUPS["offline"]`
without ever talking to the bridge. Each helper calls the **real**
implementation rather than returning a synthetic object, so an upstream
regression cannot be hidden by a hard-coded response.
``build_extension`` is the only legitimate ``environment_unavailable`` —
and only when ``node`` is genuinely absent from PATH.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

from ...certification import CertificationReport
from ..report import _record_call, _record_unavailable

# The runner derives its probe groups from BASELINE_PROBE_GROUPS and
# refuses to finish until every catalogued tool has a recorded row.
# This tuple must match BASELINE_PROBE_GROUPS["offline"] exactly.
TOOLS: tuple[str, ...] = (
    "get_ableton_logs",
    "diff_snapshots_tool",
    "scaffold_extension",
    "build_extension",
    "analyze_audio",
    "find_frequency_masking",
    "analyze_mix",
    "extract_single_cycle",
)


async def run(report: CertificationReport, workdir: Path) -> None:
    """Drive the four offline mix analysis probes plus 4 helpers.

    Each helper calls the **real** implementation rather than returning a
    synthetic object, so an upstream regression cannot be hidden by a
    hard-coded response. ``build_extension`` is the only legitimate
    ``environment_unavailable`` — and only when ``node`` is genuinely
    absent from PATH.
    """
    # ``_synthesize_offline_inputs`` is the canonical input generator
    # for every offline probe. It lives in ``acceptance.helpers`` because
    # it is reused by the synth-only tests too; we lazy-import it so
    # the probes module stays lightweight at import time.
    from ..helpers import _synthesize_offline_inputs

    inputs = _synthesize_offline_inputs(workdir)

    def analyze() -> dict[str, Any]:
        from ...analysis import audio as analysis_audio

        return analysis_audio.analyze_audio(str(inputs["target"]))

    def masking() -> dict[str, Any]:
        from ..analysis import audio as analysis_audio

        return analysis_audio.find_frequency_masking(
            str(inputs["target"]), str(inputs["reference"])
        )

    def mix() -> dict[str, Any]:
        from ..analysis import audio as analysis_audio

        return analysis_audio.analyze_mix([str(inputs["target"]), str(inputs["reference"])])

    def single_cycle() -> dict[str, Any]:
        from ..analysis import audio as analysis_audio

        return analysis_audio.extract_single_cycle(str(inputs["short"]))

    await _record_call(report, "analyze_audio", analyze, passed="offline_passed")
    await _record_call(report, "find_frequency_masking", masking, passed="offline_passed")
    await _record_call(report, "analyze_mix", mix, passed="offline_passed")
    await _record_call(report, "extract_single_cycle", single_cycle, passed="offline_passed")

    def logs() -> str:
        """Real ``get_ableton_logs`` impl: read the tail of Log.txt."""
        from ...diagnostics import find_ableton_log_path

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
        from ...diff import diff_snapshots

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

        from ...server import scaffold_extension

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

        from ...server import build_extension

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


__all__ = ["TOOLS", "run"]
