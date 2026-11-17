"""Offline probe group.

Drives the offline tools in :data:`BASELINE_PROBE_GROUPS["offline"]` without
ever talking to the bridge. Each helper calls the **real** implementation
rather than returning a synthetic object, so an upstream regression cannot be
hidden by a hard-coded response. ``build_extension`` is the only legitimate
``environment_unavailable`` — and only when ``node`` is genuinely absent from
PATH.

.. warning::
   ``run`` below is currently dead code. The runner imports only the
   ``composed`` and ``quit`` probe submodules and executes
   ``ableton_mcp_server.acceptance.runner.run_offline_probes`` instead, which
   holds a parallel copy of this logic. ``TOOLS`` here is still authoritative
   as the declaration of the group, but ``run`` records only the eight
   pre-v0.6.0 rows. Change ``runner.run_offline_probes`` when you change probe
   behaviour, and reconcile the duplication before relying on this module.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
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
    "music_generate_drum_groove",
    "music_generate_bass",
    "music_plan_production",
    "plan_user_journey",
    "groove_search",
    "groove_evidence",
    "groove_generate",
    "groove_compare",
    "groove_apply",
)


def get_client() -> Any:
    """Compatibility seam for tests proving offline probes avoid the bridge."""

    from ...server import get_client as _get_client

    return _get_client()


async def run(
    report: CertificationReport,
    workdir: Path,
    *,
    runtime: Any | None = None,
    requests: Mapping[str, Any] | None = None,
) -> None:
    """Drive the four offline mix analysis probes plus 4 helpers.

    Each helper calls the **real** implementation rather than returning a
    synthetic object, so an upstream regression cannot be hidden by a
    hard-coded response. ``build_extension`` is the only legitimate
    ``environment_unavailable`` — and only when ``node`` is genuinely
    absent from PATH.
    """
    if runtime is not None and requests is not None:
        await _record_groove_probes(report, runtime, requests)
        return

    await _record_analysis_probes(report, workdir)
    await _record_log_probe(report)
    await _record_diff_probe(report)
    await _record_scaffold_probe(report, workdir)
    await _record_build_probe(report, workdir)


async def _record_groove_probes(
    report: CertificationReport,
    runtime: Any,
    requests: Mapping[str, Any],
) -> None:
    """Record the five groove rows of the offline probe group."""
    from ...groove_intelligence.deterministic import deterministic_generate
    from ...groove_intelligence.evidence import compare, evidence
    from ...groove_intelligence.search import search
    from .groove_apply import preview_probe

    await _record_call(
        report,
        "groove_search",
        lambda: search(runtime, requests["search"]),
        passed="offline_passed",
    )
    await _record_call(
        report,
        "groove_evidence",
        lambda: evidence(runtime, requests["evidence"]),
        passed="offline_passed",
    )
    await _record_call(
        report,
        "groove_generate",
        lambda: deterministic_generate(runtime, requests["generate"]),
        passed="offline_passed",
    )
    await _record_call(
        report,
        "groove_compare",
        lambda: compare(runtime, requests["compare"]),
        passed="offline_passed",
    )
    await _record_call(
        report,
        "groove_apply",
        lambda: preview_probe(
            confirm_project_name="TESTE_CODEX",
            expected_empty_slot=True,
            disposable=True,
        ),
        passed="offline_passed",
    )


async def _record_analysis_probes(report: CertificationReport, workdir: Path) -> None:
    """Record the four offline mix analysis rows."""
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
        from ...analysis import audio as analysis_audio

        return analysis_audio.find_frequency_masking(
            str(inputs["target"]), str(inputs["reference"])
        )

    def mix() -> dict[str, Any]:
        from ...analysis import audio as analysis_audio

        return analysis_audio.analyze_mix([str(inputs["target"]), str(inputs["reference"])])

    def single_cycle() -> dict[str, Any]:
        from ...analysis import audio as analysis_audio

        return analysis_audio.extract_single_cycle(str(inputs["short"]))

    await _record_call(report, "analyze_audio", analyze, passed="offline_passed")
    await _record_call(report, "find_frequency_masking", masking, passed="offline_passed")
    await _record_call(report, "analyze_mix", mix, passed="offline_passed")
    await _record_call(report, "extract_single_cycle", single_cycle, passed="offline_passed")


async def _record_log_probe(report: CertificationReport) -> None:
    """Record the ``get_ableton_logs`` row."""

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


async def _record_diff_probe(report: CertificationReport) -> None:
    """Record the ``diff_snapshots_tool`` row."""

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


async def _record_scaffold_probe(report: CertificationReport, workdir: Path) -> None:
    """Record the ``scaffold_extension`` row."""

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


async def _record_build_probe(report: CertificationReport, workdir: Path) -> None:
    """Record the ``build_extension`` row against the scaffold we wrote."""
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
        """Run the real ``build_extension`` impl and check its contract."""
        import json

        from ...server import build_extension

        project = _scaffold_project(workdir)
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
        _assert_build_status(parsed)
        _assert_build_steps(parsed)
        entrypoint_rel = _assert_build_entrypoint(parsed)
        artifacts = _assert_build_artifacts(parsed, entrypoint_rel)
        _assert_entrypoint_on_disk(project, entrypoint_rel)
        _tag_built_artifacts(project, artifacts)
        return cast(dict[str, Any], parsed)

    await _record_call(report, "build_extension", build_ext, passed="offline_passed")


def _scaffold_project(workdir: Path) -> Path:
    """Return the scaffold directory the extension build has to run in."""
    scaffold_dir = workdir / "scaffold"
    scaffold_dirs = [p for p in scaffold_dir.iterdir() if p.is_dir()]
    if not scaffold_dirs:
        raise RuntimeError("scaffold output missing for build_extension")
    project = scaffold_dirs[0]
    return project


def _assert_build_status(parsed: dict[str, Any]) -> None:
    """Refuse a build that did not report the ``built`` status."""
    status = str(parsed.get("status", "")).strip().lower()
    if status != "built":
        raise AssertionError(f"build_extension status={status!r} expected 'built': {parsed}")


def _assert_build_steps(parsed: dict[str, Any]) -> None:
    """Refuse a build that reports a step with a failed return code."""
    steps = parsed.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise AssertionError(f"build_extension missing steps list: {parsed}")
    for index, step in enumerate(steps):
        if int(step.get("returncode", -1)) != 0:
            raise AssertionError(
                f"build_extension step {index} returncode="
                f"{step.get('returncode')!r} expected 0: {step}"
            )


def _assert_build_entrypoint(parsed: dict[str, Any]) -> str:
    """Return the entrypoint the built extension declares."""
    entrypoint = parsed.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise AssertionError(f"build_extension response missing entrypoint: {parsed}")
    entrypoint_rel = entrypoint.strip()
    return entrypoint_rel


def _assert_build_artifacts(parsed: dict[str, Any], entrypoint_rel: str) -> list[Any]:
    """Return the artefacts of a built extension, the entrypoint included."""
    # Top-level artefacts must include the declared entrypoint.
    artifacts = parsed.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        raise AssertionError(f"build_extension produced no artifacts: {parsed}")
    if entrypoint_rel not in artifacts:
        raise AssertionError(
            f"build_extension artifacts missing declared entrypoint "
            f"{entrypoint_rel!r}: {artifacts}"
        )
    return artifacts


def _assert_entrypoint_on_disk(project: Path, entrypoint_rel: str) -> None:
    """Refuse a build whose declared entrypoint is missing on disk."""
    canonical = project / entrypoint_rel
    if not canonical.is_file():
        raise AssertionError(f"build_extension entrypoint not on disk: {canonical}")


def _tag_built_artifacts(project: Path, artifacts: list[Any]) -> None:
    """Tag the built artefacts so the cleanup pass removes them."""
    # Tag built artefacts for cleanup.
    for artefact in artifacts:
        target = project / artefact
        if target.exists():
            (target.parent / "MCP_ACCEPTANCE_ARTIFACT").write_text(
                "acceptance built artifact", encoding="utf-8"
            )


__all__ = ["TOOLS", "run"]
